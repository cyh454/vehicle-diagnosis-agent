"""ORM 模型：业务表（车辆/故障码/案例/配件/会话/消息/故障历史）。"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class Vehicle(Base):
    """车辆档案：记忆系统的核心实体。"""
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vin: Mapped[str | None] = mapped_column(String(17), unique=True, index=True)
    brand: Mapped[str] = mapped_column(String(64), index=True)           # 品牌
    model: Mapped[str] = mapped_column(String(64), index=True)           # 车型
    year: Mapped[int | None] = mapped_column(Integer)                    # 年款
    power_type: Mapped[str] = mapped_column(String(16), default="纯电")   # 纯电/插混/燃油
    battery_type: Mapped[str | None] = mapped_column(String(64))         # 电池类型
    system_version: Mapped[str | None] = mapped_column(String(64))       # 整车软件版本
    owner_name: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    fault_history: Mapped[list["VehicleFaultHistory"]] = relationship(
        back_populates="vehicle", cascade="all, delete-orphan"
    )


class FaultCode(Base):
    """OBD 故障码字典。"""
    __tablename__ = "fault_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)   # 如 P0562
    system: Mapped[str] = mapped_column(String(32))                          # 所属系统
    severity: Mapped[str] = mapped_column(String(16), default="中")           # 高/中/低
    description: Mapped[str] = mapped_column(Text)
    possible_causes: Mapped[list] = mapped_column(JSONB, default=list)
    diagnostic_steps: Mapped[list] = mapped_column(JSONB, default=list)
    related_parts: Mapped[list] = mapped_column(JSONB, default=list)


class FaultCase(Base):
    """历史维修案例库。"""
    __tablename__ = "fault_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    vehicle_brand: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_model: Mapped[str] = mapped_column(String(64), index=True)
    power_type: Mapped[str] = mapped_column(String(16), default="纯电")
    mileage_km: Mapped[int | None] = mapped_column(Integer)
    symptoms: Mapped[str] = mapped_column(Text)
    fault_codes: Mapped[list] = mapped_column(JSONB, default=list)
    root_cause: Mapped[str] = mapped_column(Text)
    solution: Mapped[str] = mapped_column(Text)
    repair_steps: Mapped[list] = mapped_column(JSONB, default=list)
    parts_replaced: Mapped[list] = mapped_column(JSONB, default=list)
    repair_time_hours: Mapped[float | None] = mapped_column(Float)
    verified: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Part(Base):
    """配件信息。"""
    __tablename__ = "parts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(32))
    applicable_models: Mapped[list] = mapped_column(JSONB, default=list)
    price: Mapped[float | None] = mapped_column(Float)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    supplier: Mapped[str | None] = mapped_column(String(64))
    spec: Mapped[str | None] = mapped_column(Text)


class DiagnosisSession(Base):
    """诊断会话。"""
    __tablename__ = "diagnosis_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), default="anonymous", index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="open")
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    vehicle: Mapped[Vehicle | None] = relationship()
    messages: Mapped[list["DiagnosisMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan",
        order_by="DiagnosisMessage.id",
    )


class DiagnosisMessage(Base):
    """会话消息（含工具调用轨迹）。"""
    __tablename__ = "diagnosis_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("diagnosis_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))          # user / assistant
    content: Mapped[str] = mapped_column(Text)
    tool_calls: Mapped[list | None] = mapped_column(JSONB)  # [{tool, input, output}]
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[DiagnosisSession] = relationship(back_populates="messages")


class VehicleFaultHistory(Base):
    """车辆历史故障（长期记忆，跨会话）。"""
    __tablename__ = "vehicle_fault_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[int] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str | None] = mapped_column(String(32), index=True)
    fault_summary: Mapped[str] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    solution: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vehicle: Mapped[Vehicle] = relationship(back_populates="fault_history")
