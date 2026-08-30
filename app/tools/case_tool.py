# app/tools/case_tool.py
"""工具：历史维修案例检索。"""
import json
import re

from langchain_core.tools import BaseTool, tool
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import FaultCase


def make_case_tool(db: Session) -> BaseTool:
    @tool("search_similar_cases")
    def search_similar_cases(symptoms: str, vehicle_model: str = "", top_k: int = 3) -> str:
        """检索历史维修案例库，返回同车型或相似故障症状的处理经验（根因与解决方案）。
        当需要参考既往维修经验、验证诊断假设时调用。
        参数symptoms: 故障症状关键词(如"充电中断 高压报警")；
        参数vehicle_model: 车型名称(可空)；参数top_k: 返回条数(默认3)。"""
        try:
            terms = [t for t in re.split(r"[\s,，、;；/]+", symptoms) if len(t) >= 2][:8]
            if not terms:
                return "请提供有效的故障症状关键词。"
            conds = []
            for t in terms:
                like = f"%{t}%"
                conds.append(or_(
                    FaultCase.symptoms.ilike(like),
                    FaultCase.root_cause.ilike(like),
                    FaultCase.solution.ilike(like),
                ))
            rows = db.execute(select(FaultCase).where(or_(*conds))).scalars().all()
            if not rows:
                return f"案例库中未检索到与「{symptoms}」相关的案例。"

            def score(c: FaultCase) -> float:
                text_all = f"{c.symptoms} {c.root_cause} {c.solution}"
                s = sum(1 for t in terms if t in text_all)
                if vehicle_model and vehicle_model in f"{c.vehicle_brand} {c.vehicle_model}":
                    s += 2
                if c.verified:
                    s += 0.5
                return s

            rows.sort(key=score, reverse=True)
            out = []
            for c in rows[: max(1, min(top_k, 5))]:
                out.append(json.dumps({
                    "case_no": c.case_no,
                    "vehicle": f"{c.vehicle_brand} {c.vehicle_model}({c.power_type})",
                    "mileage_km": c.mileage_km,
                    "symptoms": c.symptoms,
                    "fault_codes": c.fault_codes,
                    "root_cause": c.root_cause,
                    "solution": c.solution,
                    "parts_replaced": c.parts_replaced,
                }, ensure_ascii=False))
            return "\n".join(out)
        except Exception as e:
            return f"工具执行失败: {e}"

    return search_similar_cases
