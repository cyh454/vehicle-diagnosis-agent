# app/tools/kb_tool.py
"""工具：知识库 RAG 检索（混合检索）。"""
from langchain_core.tools import BaseTool, tool
from sqlalchemy.orm import Session

from app.core.retriever import HybridRetriever


def make_kb_tool(db: Session, retriever: HybridRetriever) -> BaseTool:
    @tool("search_knowledge_base")
    def search_knowledge_base(query: str, doc_type: str = "") -> str:
        """检索车载电源标准文档知识库(GB/T国标、企业诊断手册、技术通报)。
        需要引用标准条款、规范参数、原理说明或深度排查指引时调用。
        参数query: 检索问题(如"DC-DC输出电压范围要求")；
        参数doc_type: 文档类型过滤(standard/manual/case/spec，可空)。"""
        try:
            chunks = retriever.search(db, query, doc_type=doc_type or None)
            return HybridRetriever.format(chunks)
        except Exception as e:
            return f"工具执行失败: {e}"

    return search_knowledge_base
