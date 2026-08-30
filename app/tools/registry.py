# app/tools/registry.py
"""工具注册表：按会话上下文构建 Agent 工具集。"""
from sqlalchemy.orm import Session

from app.core.retriever import HybridRetriever
from app.tools.case_tool import make_case_tool
from app.tools.fault_code_tool import make_fault_code_tool
from app.tools.kb_tool import make_kb_tool
from app.tools.parts_tool import make_parts_tool
from app.tools.record_tool import make_record_tool
from app.tools.vehicle_tool import make_vehicle_tool


def build_tools(db: Session, session_id: str, retriever: HybridRetriever) -> list:
    return [
        make_vehicle_tool(db, session_id),
        make_fault_code_tool(db),
        make_case_tool(db),
        make_kb_tool(db, retriever),
        make_parts_tool(db),
        make_record_tool(db, session_id),
    ]
