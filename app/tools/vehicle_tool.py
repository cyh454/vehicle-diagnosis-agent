# app/tools/vehicle_tool.py
"""工具：车辆档案与故障历史（记忆系统入口）。"""
import json

from langchain_core.tools import BaseTool, tool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DiagnosisSession, Vehicle, VehicleFaultHistory


def make_vehicle_tool(db: Session, session_id: str) -> BaseTool:
    @tool("get_vehicle_info")
    def get_vehicle_info() -> str:
        """获取当前会话绑定的车辆档案(品牌/车型/年款/动力类型/电池类型)与该车历史故障记录。
        开始诊断前调用，用于结合车辆个性特征与历史故障提高诊断准确率。无参数。"""
        try:
            sess = db.get(DiagnosisSession, session_id)
            if sess is None or sess.vehicle_id is None:
                return "当前会话尚未绑定车辆，请向工程师询问车型/VIN。"
            v = db.get(Vehicle, sess.vehicle_id)
            history = db.execute(
                select(VehicleFaultHistory)
                .where(VehicleFaultHistory.vehicle_id == v.id)
                .order_by(VehicleFaultHistory.created_at.desc())
                .limit(5)
            ).scalars().all()
            info = {
                "vehicle": {
                    "vin": v.vin, "brand": v.brand, "model": v.model,
                    "year": v.year, "power_type": v.power_type,
                    "battery_type": v.battery_type, "system_version": v.system_version,
                },
                "fault_history": [
                    {
                        "date": h.created_at.strftime("%Y-%m-%d") if h.created_at else None,
                        "fault": h.fault_summary, "root_cause": h.root_cause,
                        "solution": h.solution,
                    } for h in history
                ],
            }
            return json.dumps(info, ensure_ascii=False)
        except Exception as e:
            return f"工具执行失败: {e}"

    return get_vehicle_info
