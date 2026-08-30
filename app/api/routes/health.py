# app/api/routes/health.py
"""健康检查与运行指标。"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.middleware.monitoring import METRICS

router = APIRouter(tags=["运维"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """存活探针：检查数据库与 pgvector。"""
    checks = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
    try:
        row = db.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).first()
        checks["pgvector"] = "ok" if row else "missing"
    except Exception as e:
        checks["pgvector"] = f"error: {e}"
    healthy = all(v == "ok" for v in checks.values())
    return {"status": "healthy" if healthy else "degraded", "checks": checks}


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    """运行指标：请求量、耗时分位、工具调用、业务统计。"""
    business = {}
    try:
        business["sessions"] = db.execute(text("SELECT count(*) FROM diagnosis_sessions")).scalar()
        business["messages"] = db.execute(text("SELECT count(*) FROM diagnosis_messages")).scalar()
        business["kb_documents"] = db.execute(text("SELECT count(*) FROM kb_documents")).scalar()
        business["kb_chunks"] = db.execute(text("SELECT count(*) FROM kb_chunks")).scalar()
    except Exception:
        pass
    return {**METRICS.snapshot(), "business": business}
