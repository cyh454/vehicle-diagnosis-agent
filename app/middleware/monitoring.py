"""请求级监控：request_id、耗时日志、访问指标、全局异常兜底。"""
import logging
import time
import uuid
from collections import Counter, deque

from fastapi import Request
from fastapi.responses import JSONResponse

from app.logging_config import request_id_var

logger = logging.getLogger(__name__)


class Metrics:
    """轻量进程内指标（如需 Prometheus 可替换为 prometheus_client）。"""

    def __init__(self):
        self.started_at = time.time()
        self.requests_total: Counter = Counter()
        self.status_codes: Counter = Counter()
        self.tool_calls: Counter = Counter()
        self.latencies: deque = deque(maxlen=1000)

    def observe(self, path: str, status: int, latency: float) -> None:
        self.requests_total[path] += 1
        self.status_codes[status] += 1
        self.latencies.append(latency)

    @staticmethod
    def _pct(sorted_vals: list, p: float) -> float:
        if not sorted_vals:
            return 0.0
        idx = min(len(sorted_vals) - 1, int(p / 100 * len(sorted_vals)))
        return round(sorted_vals[idx] * 1000, 1)

    def snapshot(self) -> dict:
        vals = sorted(self.latencies)
        return {
            "uptime_seconds": round(time.time() - self.started_at, 1),
            "requests_total": dict(self.requests_total),
            "status_codes": dict(self.status_codes),
            "tool_calls": dict(self.tool_calls),
            "latency_ms": {
                "p50": self._pct(vals, 50),
                "p95": self._pct(vals, 95),
                "p99": self._pct(vals, 99),
            },
        }


METRICS = Metrics()


async def monitoring_middleware(request: Request, call_next):
    """request_id 注入 → 计时 → 异常兜底 → 指标与访问日志。"""
    rid = uuid.uuid4().hex[:8]
    token = request_id_var.set(rid)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("未捕获异常 %s %s", request.method, request.url.path)
        response = JSONResponse(
            status_code=500,
            content={"code": 500, "message": "服务内部错误", "request_id": rid},
        )
    finally:
        latency = time.perf_counter() - start
        request_id_var.reset(token)

    METRICS.observe(request.url.path, response.status_code, latency)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Process-Time-ms"] = str(int(latency * 1000))
    logger.info("%s %s -> %d (%.0fms)", request.method, request.url.path,
                response.status_code, latency * 1000)
    return response
