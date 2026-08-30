# app/core/llm.py
"""LLM 工厂：任何 OpenAI 兼容服务（GLM / DeepSeek / GPT）均可接入。"""
from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import get_settings


@lru_cache
def get_chat_llm() -> ChatOpenAI:
    s = get_settings()
    if not s.llm_api_key:
        raise RuntimeError("未配置 LLM_API_KEY，请在 .env 中设置")
    return ChatOpenAI(
        model=s.llm_model,
        api_key=s.llm_api_key,
        base_url=s.llm_base_url or None,
        temperature=s.llm_temperature,
        max_tokens=s.llm_max_tokens,
        timeout=s.llm_timeout,
        max_retries=2,
    )
