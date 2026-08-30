# app/tools/parts_tool.py
"""工具：配件信息查询。"""
import json

from langchain_core.tools import BaseTool, tool
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Part


def make_parts_tool(db: Session) -> BaseTool:
    @tool("query_parts_info")
    def query_parts_info(part_name: str) -> str:
        """查询配件信息：编号、规格、价格、库存、供应商与适用车型。
        当诊断结论涉及更换配件、工程师询问配件价格/库存时调用。
        参数part_name: 配件名称或编号(如"DC-DC转换器"或"PDU-DCDC-2201")。"""
        try:
            key = part_name.strip()
            like = f"%{key}%"
            rows = db.execute(
                select(Part).where(or_(
                    Part.name.ilike(like), Part.part_no.ilike(like),
                    Part.category.ilike(like),
                )).limit(10)
            ).scalars().all()
            if not rows:
                return f"配件库中未找到「{key}」，请尝试更准确的配件名称。"
            return "\n".join(json.dumps({
                "part_no": p.part_no, "name": p.name, "category": p.category,
                "price": p.price, "stock": p.stock, "supplier": p.supplier,
                "spec": p.spec, "applicable_models": p.applicable_models,
            }, ensure_ascii=False) for p in rows)
        except Exception as e:
            return f"工具执行失败: {e}"

    return query_parts_info
