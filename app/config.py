"""全局配置：通过环境变量 / .env 覆盖默认值。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ───────── 应用 ─────────
    app_name: str = "车载故障诊断 Agent 系统"
    app_version: str = "1.0.0"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # ───────── 数据库 ─────────
    database_url: str = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/vehicle_diagnosis"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800

    # ───────── LLM（OpenAI 兼容协议：GLM / DeepSeek / GPT 均可）─────────
    llm_model: str = "glm-4-plus"
    llm_api_key: str = ""
    llm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096
    llm_timeout: int = 120

    # ───────── Embedding ─────────
    embedding_provider: str = "openai_compatible"  # openai_compatible | huggingface
    embedding_model: str = "embedding-3"
    embedding_api_key: str = ""          # 缺省复用 llm_api_key
    embedding_base_url: str = ""         # 缺省复用 llm_base_url
    embedding_dimension: int = 1024      # pgvector HNSW 索引上限 2000 维，embedding-3 需降维使用
    embedding_send_dimensions: bool = True

    # ───────── RAG ─────────
    chunk_size: int = 500
    chunk_overlap: int = 80
    retrieval_top_k: int = 5
    rrf_k: int = 60

    # ───────── Agent ─────────
    agent_max_iterations: int = 8
    agent_verbose: bool = False
    history_window: int = 10   # 注入对话历史的消息条数

    # ───────── 其他 ─────────
    upload_dir: str = "data/uploads"

    @property
    def emb_api_key(self) -> str:
        return self.embedding_api_key or self.llm_api_key

    @property
    def emb_base_url(self) -> str:
        return self.embedding_base_url or self.llm_base_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
