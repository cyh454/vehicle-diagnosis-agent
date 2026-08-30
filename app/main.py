"""应用入口：装配日志、数据库、路由与中间件。"""
import sys
from pathlib import Path

# 兼容 VS Code「运行 Python 文件」等直接执行方式：此时 sys.path 指向 app/ 目录，
# 需把项目根目录加入模块搜索路径，`from app...` 导入才能生效
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import diagnosis, health, knowledge, vehicle
from app.config import get_settings
from app.db import models  # noqa: F401  确保模型注册到 Base
from app.db.database import Base, engine, ensure_extensions
from app.logging_config import setup_logging
from app.middleware.monitoring import monitoring_middleware
from app.rag.vector_store import ensure_vector_tables

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.debug)
    if not settings.llm_api_key:
        logger.warning("⚠️ 未配置 LLM_API_KEY，诊断接口(/chat)将不可用")
    logger.info("初始化数据库（业务表 + 向量表）...")
    ensure_extensions()
    Base.metadata.create_all(engine)
    ensure_vector_tables(engine)
    logger.info("%s v%s 启动完成，接口文档: /docs",
                settings.app_name, settings.app_version)
    yield
    logger.info("应用关闭")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="面向售后工程师的车载电源故障诊断 Agent（RAG + 多工具编排 + 车辆记忆）",
    lifespan=lifespan,
)

# 中间件：先加监控（内层），再加 CORS（外层），保证异常响应也带 CORS 头
app.middleware("http")(monitoring_middleware)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# 业务路由挂在 /api/v1 下
for r in (diagnosis.router, knowledge.router, vehicle.router):
    app.include_router(r, prefix=settings.api_prefix)
# 运维路由挂根路径，便于探针
app.include_router(health.router)

# Web 聊天界面：挂静态资源（须在所有 API 路由之后，避免遮蔽 /docs、/api/*）
_web_dir = Path(__file__).resolve().parent / "web"
if (_web_dir / "index.html").exists():
    app.mount("/", StaticFiles(directory=_web_dir, html=True), name="web")
else:
    @app.get("/")
    def root():
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "health": "/health",
        }


if __name__ == "__main__":
    # 直接运行本文件时启动开发服务器（等价于 uvicorn app.main:app --reload）
    import uvicorn
    uvicorn.run("app.main:app", port=8000, reload=True)
