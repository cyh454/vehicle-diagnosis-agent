# app/tools/record_tool.py
"""工具：诊断结论归档（写入车辆长期记忆）。"""
from langchain_core.tools import BaseTool, tool
from sqlalchemy.orm import Session

from app.db.models import DiagnosisSession, VehicleFaultHistory


def make_record_tool(db: Session, session_id: str) -> BaseTool:
    @tool("record_diagnosis_result")
    def record_diagnosis_result(fault_summary: str, root_cause: str, solution: str) -> str:
        """将本次诊断结论写入车辆故障历史(长期记忆)，供该车后续诊断参考。
        仅在诊断结论明确(置信度中/高)时调用一次。
        参数fault_summary: 故障概述；root_cause: 根本原因；solution: 解决方案。"""
        try:
            sess = db.get(DiagnosisSession, session_id)
            if sess is None or sess.vehicle_id is None:
                return "当前会话未绑定车辆，无法记录。请先确认车型。"
            db.add(VehicleFaultHistory(
                vehicle_id=sess.vehicle_id, session_id=session_id,
                fault_summary=fault_summary, root_cause=root_cause, solution=solution,
            ))
            db.commit()
            return "已记录到车辆故障历史。"
        except Exception as e:
            db.rollback()
            return f"记录失败: {e}"

    return record_diagnosis_result
