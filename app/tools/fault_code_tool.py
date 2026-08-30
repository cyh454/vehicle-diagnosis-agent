# app/tools/fault_code_tool.py
"""工具：OBD 故障码字典查询。"""
import json
import logging

from langchain_core.tools import BaseTool, tool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FaultCode

logger = logging.getLogger(__name__)


def make_fault_code_tool(db: Session) -> BaseTool:
    @tool("query_fault_code")
    def query_fault_code(code: str) -> str:
        """查询OBD故障码的标准定义、所属系统、严重等级、可能原因与诊断步骤。
        当用户或诊断仪提到故障码(如P0562、U0111、B1244)时必须调用本工具。
        参数code: 故障码字符串，如 'P0562'。"""
        try:
            key = code.strip().upper().replace(" ", "")
            row = db.execute(
                select(FaultCode).where(FaultCode.code == key)
            ).scalar_one_or_none()
            if row is None:
                family = db.execute(
                    select(FaultCode).where(FaultCode.code.like(f"{key[:1]}%")).limit(10)
                ).scalars().all()
                if family:
                    names = "、".join(f"{f.code}({f.description[:20]})" for f in family)
                    return f"未精确找到 {key}，同族故障码有：{names}。请确认故障码是否正确。"
                return f"故障码字典中未找到 {key}，请检查输入，或参考标准文档做通用排查。"
            return json.dumps({
                "code": row.code, "system": row.system, "severity": row.severity,
                "description": row.description, "possible_causes": row.possible_causes,
                "diagnostic_steps": row.diagnostic_steps, "related_parts": row.related_parts,
            }, ensure_ascii=False)
        except Exception as e:
            logger.exception("query_fault_code 失败")
            return f"工具执行失败: {e}"

    return query_fault_code
