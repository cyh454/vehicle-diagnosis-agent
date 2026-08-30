"""诊断 Agent：LangChain 工具调用编排 + 会话/车辆记忆 + 消息持久化。"""
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.llm import get_chat_llm
from app.core.prompts import SYSTEM_PROMPT
from app.core.retriever import HybridRetriever
from app.db.models import DiagnosisMessage, DiagnosisSession, Vehicle
from app.memory.vehicle_memory import VehicleMemoryManager
from app.middleware.monitoring import METRICS
from app.tools.registry import build_tools

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    session_id: str
    reply: str
    vehicle: Optional[Vehicle]
    tool_calls: list = field(default_factory=list)
    latency_ms: int = 0
    created: bool = False


class DiagnosisAgent:
    """每轮对话：车辆记忆 → 构建工具 → 加载历史 → Agent 推理 → 持久化。"""

    def __init__(self):
        self.settings = get_settings()
        self.llm = get_chat_llm()
        self.retriever = HybridRetriever()
        self.vehicle_memory = VehicleMemoryManager(self.llm)

    def run(self, db: Session, session_id: Optional[str], user_input: str,
            user_id: str = "anonymous") -> AgentResult:
        t0 = time.perf_counter()

        # ── 1. 会话管理 ──
        created = False
        session = db.get(DiagnosisSession, session_id) if session_id else None
        if session is None:
            session = DiagnosisSession(id=uuid.uuid4().hex, user_id=user_id)
            db.add(session)
            db.commit()
            created = True
        if not session.title:
            session.title = user_input[:50]

        # ── 2. 车辆记忆（车型识别 / 会话绑定）──
        try:
            vehicle = self.vehicle_memory.resolve(db, session, user_input)
        except Exception:
            logger.exception("车辆识别异常，降级继续")
            vehicle = db.get(Vehicle, session.vehicle_id) if session.vehicle_id else None

        # ── 3. 构建工具（携带会话上下文）+ 加载对话历史 ──
        tools = build_tools(db, session.id, self.retriever)
        history = self._load_history(db, session)

        # ── 4. Agent 推理 ──
        executor = self._build_executor(tools)
        try:
            outcome = executor.invoke({"input": user_input, "chat_history": history})
            reply = (outcome.get("output") or "").strip() or "未能生成有效回复，请补充故障信息后重试。"
            tool_calls = self._extract_tool_calls(outcome)
        except Exception as e:
            logger.exception("Agent 执行失败")
            reply = f"诊断服务暂时不可用（{e}），请稍后重试或联系管理员。"
            tool_calls = []

        latency_ms = int((time.perf_counter() - t0) * 1000)

        # ── 5. 消息持久化 ──
        try:
            db.add(DiagnosisMessage(session_id=session.id, role="user", content=user_input))
            db.add(DiagnosisMessage(session_id=session.id, role="assistant", content=reply,
                                    tool_calls=tool_calls, latency_ms=latency_ms))
            session.message_count = (session.message_count or 0) + 2
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("消息持久化失败")

        logger.info("会话 %s 完成 | 车辆=%s | 工具调用=%d 次 | 耗时 %dms",
                    session.id,
                    f"{vehicle.brand} {vehicle.model}" if vehicle else "未识别",
                    len(tool_calls), latency_ms)
        return AgentResult(session.id, reply, vehicle, tool_calls, latency_ms, created)

    # ───────────────────────── 辅助方法 ─────────────────────────

    def _build_executor(self, tools) -> AgentExecutor:
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])
        agent = create_tool_calling_agent(self.llm, tools, prompt)
        return AgentExecutor(
            agent=agent,
            tools=tools,
            max_iterations=self.settings.agent_max_iterations,
            max_execution_time=self.settings.llm_timeout,
            handle_parsing_errors=True,
            verbose=self.settings.agent_verbose,
            return_intermediate_steps=True,
        )

    def _load_history(self, db: Session, session: DiagnosisSession) -> list:
        rows = db.execute(
            select(DiagnosisMessage)
            .where(DiagnosisMessage.session_id == session.id)
            .order_by(DiagnosisMessage.id.desc())
            .limit(self.settings.history_window)
        ).scalars().all()
        rows = list(rows)[::-1]
        return [
            HumanMessage(content=m.content) if m.role == "user"
            else AIMessage(content=m.content)
            for m in rows
        ]

    @staticmethod
    def _extract_tool_calls(outcome: dict) -> list:
        calls = []
        for action, observation in outcome.get("intermediate_steps", []):
            tool = getattr(action, "tool", "unknown")
            tool_input = getattr(action, "tool_input", {})
            output = observation if isinstance(observation, str) else str(observation)
            calls.append({
                "tool": tool,
                "input": tool_input if isinstance(tool_input, dict) else str(tool_input),
                "output": output[:800],
            })
            METRICS.tool_calls[tool] += 1
            logger.info("🔧 %s(%s) -> %s", tool, tool_input,
                        output[:150].replace("\n", " "))
        return calls


_agent: Optional[DiagnosisAgent] = None


def get_agent() -> DiagnosisAgent:
    """单例：LLM / Embedding / Retriever 全局复用。"""
    global _agent
    if _agent is None:
        _agent = DiagnosisAgent()
    return _agent
