# app/core/embeddings.py
"""Embedding 工厂：支持 OpenAI 兼容 API 与本地 HuggingFace 模型。"""
from functools import lru_cache

from app.config import get_settings


@lru_cache
def get_embeddings():
    s = get_settings()

    # 本地私有化部署（离线可用）：BAAI/bge-large-zh-v1.5 / bge-m3 等
    if s.embedding_provider == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(
            model_name=s.embedding_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

    # OpenAI 兼容 API（智谱 embedding-3 / OpenAI text-embedding-3-* 等）
    from langchain_openai import OpenAIEmbeddings
    kwargs = dict(
        model=s.embedding_model,
        api_key=s.emb_api_key,
        base_url=s.emb_base_url or None,
        check_embedding_ctx_length=False,  # 兼容非 OpenAI 官方服务必需
    )
    if s.embedding_send_dimensions and s.embedding_dimension > 0:
        kwargs["dimensions"] = s.embedding_dimension
    return OpenAIEmbeddings(**kwargs)
