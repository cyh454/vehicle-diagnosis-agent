# app/api/routes/diagnosis.py
"""诊断对话 API。"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_agent_dep
from app.core.agent import DiagnosisAgent
from app.db.database import get_db
from app.db.models import DiagnosisMessage, DiagnosisSession, Vehicle
from app.schemas.diagnosis import (
    ChatRequest, ChatResponse, MessageItem, SessionBrief, SessionDetail,
    VehicleBrief,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/diagnosis", tags=["诊断对话"])


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db),
         agent: DiagnosisAgent = Depends(get_agent_dep)):
    """车载故障诊断对话入口：自动维护会话、车辆记忆与工具调用轨迹。"""
    try:
        result = agent.run(db, req.session_id, req.message, req.user_id)
    except Exception as e:
        logger.exception("chat 处理失败")
        raise HTTPException(status_code=500, detail=f"诊断服务异常: {e}")

    vehicle_brief = None
    if result.vehicle:
        vehicle_brief = VehicleBrief(
            vin=result.vehicle.vin, brand=result.vehicle.brand,
            model=result.vehicle.model, year=result.vehicle.year,
            power_type=result.vehicle.power_type,
        )
    return ChatResponse(
        session_id=result.session_id, reply=result.reply, vehicle=vehicle_brief,
        tool_calls=result.tool_calls, latency_ms=result.latency_ms,
        created=result.created,
    )


@router.get("/sessions", response_model=list[SessionBrief])
def list_sessions(user_id: str | None = None, limit: int = 50,
                  db: Session = Depends(get_db)):
    """会话列表（按最近更新排序），供前端侧边栏展示。"""
    q = select(DiagnosisSession).order_by(DiagnosisSession.updated_at.desc()).limit(limit)
    if user_id:
        q = q.where(DiagnosisSession.user_id == user_id)
    rows = db.execute(q).scalars().all()
    items = []
    for s in rows:
        vehicle = db.get(Vehicle, s.vehicle_id) if s.vehicle_id else None
        items.append(SessionBrief(
            session_id=s.id, title=s.title, message_count=s.message_count or 0,
            vehicle=VehicleBrief(
                vin=vehicle.vin, brand=vehicle.brand, model=vehicle.model,
                year=vehicle.year, power_type=vehicle.power_type,
            ) if vehicle else None,
            updated_at=s.updated_at.isoformat() if s.updated_at else None,
        ))
    return items


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: str, db: Session = Depends(get_db)):
    """查询会话详情：对话历史 + 绑定车辆 + 工具调用轨迹。"""
    sess = db.get(DiagnosisSession, session_id)
    if sess is None:
        raise HTTPException(404, "会话不存在")
    vehicle = db.get(Vehicle, sess.vehicle_id) if sess.vehicle_id else None
    messages = db.execute(
        select(DiagnosisMessage)
        .where(DiagnosisMessage.session_id == session_id)
        .order_by(DiagnosisMessage.id)
    ).scalars().all()
    return SessionDetail(
        session_id=sess.id, user_id=sess.user_id,
        vehicle=VehicleBrief(
            vin=vehicle.vin, brand=vehicle.brand, model=vehicle.model,
            year=vehicle.year, power_type=vehicle.power_type,
        ) if vehicle else None,
        title=sess.title, message_count=sess.message_count,
        messages=[MessageItem(
            role=m.role, content=m.content, tool_calls=m.tool_calls,
            latency_ms=m.latency_ms,
            created_at=m.created_at.isoformat() if m.created_at else None,
        ) for m in messages],
    )
