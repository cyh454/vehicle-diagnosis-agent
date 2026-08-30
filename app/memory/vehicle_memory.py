"""车辆记忆系统：车型识别（VIN / LLM 抽取 / 模糊匹配）与会话绑定。"""
import logging
import re
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DiagnosisSession, Vehicle

logger = logging.getLogger(__name__)

VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")   # 标准VIN不含 I/O/Q
SWITCH_HINTS = ("换一辆", "换车", "另一台", "另外一台", "不是这辆", "新车")

BRAND_ALIAS = {
    "byd": "比亚迪", "比亚迪": "比亚迪",
    "tesla": "特斯拉", "特斯拉": "特斯拉",
    "nio": "蔚来", "蔚来": "蔚来",
    "小鹏": "小鹏", "理想": "理想",
    "吉利": "吉利", "极氪": "极氪",
    "埃安": "广汽埃安", "广汽埃安": "广汽埃安",
    "荣威": "荣威", "上汽": "上汽",
}


class ExtractedVehicle(BaseModel):
    """LLM 从用户消息中抽取的车辆信息。"""
    found: bool = Field(default=False, description="文本中是否包含车辆信息")
    vin: Optional[str] = Field(default=None, description="车架号VIN(17位)")
    brand: Optional[str] = Field(default=None, description="品牌, 如 比亚迪")
    model: Optional[str] = Field(default=None, description="车型, 如 汉EV")
    year: Optional[int] = Field(default=None, description="年款, 如 2022")
    power_type: Optional[str] = Field(default=None, description="纯电/插混/增程/燃油")


EXTRACT_PROMPT = (
    "从用户消息中抽取车辆信息，只依据文本内容、不要猜测。"
    "品牌、车型（含不带品牌的车型简称，如 汉EV、唐DM-i、Model 3、AION S、001）"
    "或VIN任一出现即算提及；若均未出现，则 found=false。\n用户消息：{text}"
)


class VehicleMemoryManager:
    """短期记忆（会话绑定车辆）+ 长期记忆（车辆故障历史）的管理入口。"""

    def __init__(self, llm):
        self.llm = llm
        try:
            # GLM 等模型在 json_mode 下会把 JSON 包进 ```json 代码块导致解析失败，
            # 改走 function calling 通道（OpenAI 兼容端点均支持）
            self._extractor = llm.with_structured_output(
                ExtractedVehicle, method="function_calling"
            )
        except Exception:
            logger.warning("structured output 初始化失败，车辆识别降级为规则模式")
            self._extractor = None

    # ── 主入口：识别/更新会话绑定的车辆 ──
    def resolve(self, db: Session, session: DiagnosisSession,
                user_text: str) -> Optional[Vehicle]:
        # 1) VIN 精确识别（零成本，优先）
        vin_match = VIN_RE.search(user_text.upper())
        if vin_match:
            vehicle = self._by_vin(db, vin_match.group(0), user_text)
            if vehicle:
                self._bind(db, session, vehicle)
                return vehicle

        # 2) 已绑定且无"换车"信号 → 直接复用（避免每轮都调 LLM）
        current = db.get(Vehicle, session.vehicle_id) if session.vehicle_id else None
        if current and not any(h in user_text for h in SWITCH_HINTS):
            return current

        # 3) 未绑定（或出现切换信号）→ LLM 抽取品牌/车型
        info = self._extract(user_text)
        if info and info.found and (info.brand or info.model or info.vin):
            if info.vin:
                vehicle = self._by_vin(db, info.vin.upper(), user_text)
                if vehicle:
                    self._bind(db, session, vehicle)
                    return vehicle
            vehicle = self._match_or_create(db, info)
            if vehicle:
                self._bind(db, session, vehicle)
                return vehicle
        return current

    # ── 内部方法 ──
    def _extract(self, text: str) -> Optional[ExtractedVehicle]:
        if self._extractor is None:
            return None
        try:
            return self._extractor.invoke(EXTRACT_PROMPT.format(text=text))
        except Exception:
            logger.warning("车辆信息抽取失败", exc_info=True)
            return None

    def _by_vin(self, db: Session, vin: str, user_text: str) -> Optional[Vehicle]:
        vehicle = db.execute(
            select(Vehicle).where(Vehicle.vin == vin)
        ).scalar_one_or_none()
        if vehicle:
            return vehicle
        # 档案库无此 VIN：结合抽取信息建档
        info = self._extract(user_text)
        v = Vehicle(
            vin=vin,
            brand=(info.brand if info and info.brand else "未知品牌"),
            model=(info.model if info and info.model else "未知车型"),
            year=info.year if info else None,
            power_type=(info.power_type if info and info.power_type else "纯电"),
        )
        db.add(v)
        db.commit()
        logger.info("按VIN新建车辆档案: %s", vin)
        return v

    def _match_or_create(self, db: Session, info: ExtractedVehicle) -> Optional[Vehicle]:
        brand = (info.brand or "").strip()
        model = (info.model or "").strip()
        if not brand and not model:
            return None
        brand = BRAND_ALIAS.get(brand.lower(), brand)
        q = select(Vehicle)
        if brand:
            q = q.where(Vehicle.brand.ilike(f"%{brand}%"))
        if model:
            q = q.where(Vehicle.model.ilike(f"%{model}%"))
        rows = db.execute(q).scalars().all()
        if not rows and brand and model:
            # LLM 可能把"唐DM-i"拆成 品牌=唐/车型=DM-i，拼合全名对车型字段再匹配
            rows = db.execute(
                select(Vehicle).where(Vehicle.model.ilike(f"%{brand}{model}%"))
            ).scalars().all()
        if rows:
            rows.sort(key=lambda v: (v.year == info.year), reverse=True)  # 优先年款一致
            return rows[0]
        if brand and model:
            v = Vehicle(vin=None, brand=brand, model=model, year=info.year,
                        power_type=info.power_type or "纯电")
            db.add(v)
            db.commit()
            logger.info("新建车辆档案: %s %s", brand, model)
            return v
        return None

    @staticmethod
    def _bind(db: Session, session: DiagnosisSession, vehicle: Vehicle) -> None:
        if session.vehicle_id != vehicle.id:
            session.vehicle_id = vehicle.id
            db.commit()
            logger.info("会话 %s 绑定车辆: %s %s (%s)",
                        session.id, vehicle.brand, vehicle.model, vehicle.vin)
