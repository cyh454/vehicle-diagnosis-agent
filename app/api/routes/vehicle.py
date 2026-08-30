# app/api/routes/vehicle.py
"""车辆档案 API。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Vehicle, VehicleFaultHistory

router = APIRouter(prefix="/vehicles", tags=["车辆档案"])


@router.get("/{vin}")
def get_vehicle(vin: str, db: Session = Depends(get_db)):
    """按 VIN 查询车辆档案与历史故障（长期记忆）。"""
    v = db.execute(select(Vehicle).where(Vehicle.vin == vin.upper())).scalar_one_or_none()
    if v is None:
        raise HTTPException(404, "车辆不存在")
    history = db.execute(
        select(VehicleFaultHistory)
        .where(VehicleFaultHistory.vehicle_id == v.id)
        .order_by(VehicleFaultHistory.created_at.desc()).limit(20)
    ).scalars().all()
    return {
        "vin": v.vin, "brand": v.brand, "model": v.model, "year": v.year,
        "power_type": v.power_type, "battery_type": v.battery_type,
        "system_version": v.system_version,
        "fault_history": [
            {"fault_summary": h.fault_summary, "root_cause": h.root_cause,
             "solution": h.solution,
             "created_at": h.created_at.isoformat() if h.created_at else None}
            for h in history
        ],
    }
