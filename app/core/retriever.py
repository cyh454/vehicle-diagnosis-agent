"""混合检索：向量(语义) + trigram(关键词) + RRF 融合。"""
import logging
import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.embeddings import get_embeddings
from app.rag.vector_store import vec_to_str

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: int
    content: str
    doc_name: str
    doc_type: str
    score: float


class HybridRetriever:
    """向量召回 + 关键词召回，RRF(Reciprocal Rank Fusion) 融合排序。
    解决纯向量检索对故障码(P0562)、专有名词召回差的问题。"""

    def __init__(self):
        self.settings = get_settings()
        self.embeddings = get_embeddings()

    # ── 对外接口 ──
    def search(self, db: Session, query: str, doc_type: str | None = None,
               top_k: int | None = None) -> list[RetrievedChunk]:
        top_k = top_k or self.settings.retrieval_top_k
        expand = max(top_k * 4, 16)
        vec_ranking = self._vector_search(db, query, doc_type, expand)
        kw_ranking = self._keyword_search(db, query, doc_type, expand)
        fused = self._rrf([vec_ranking, kw_ranking])
        if not fused:
            return []
        chunks = self._load_chunks(db, list(fused.keys()))
        for c in chunks:
            c.score = round(fused.get(c.chunk_id, 0.0), 6)
        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks[:top_k]

    # ── 向量检索（HNSW 余弦距离） ──
    def _vector_search(self, db: Session, query: str,
                       doc_type: str | None, k: int) -> list[int]:
        qvec = vec_to_str(self.embeddings.embed_query(query))
        sql = text("""
            SELECT c.id
            FROM kb_chunks c
            JOIN kb_documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
              AND (CAST(:doc_type AS text) IS NULL OR d.doc_type = :doc_type)
            ORDER BY c.embedding <=> CAST(:qvec AS vector)
            LIMIT :k
        """)
        rows = db.execute(sql, {"qvec": qvec, "doc_type": doc_type, "k": k}).all()
        return [r[0] for r in rows]

    # ── 关键词检索（pg_trgm，对中文子串友好） ──
    def _keyword_search(self, db: Session, query: str,
                        doc_type: str | None, k: int) -> list[int]:
        terms = [t for t in re.split(r"[\s,，、;；/]+", query) if len(t) >= 2][:8]
        if not terms:
            return []
        pats = [f"%{t}%" for t in terms]
        sql = text("""
            SELECT c.id
            FROM kb_chunks c
            JOIN kb_documents d ON d.id = c.document_id
            WHERE c.content ILIKE ANY (:pats)
              AND (CAST(:doc_type AS text) IS NULL OR d.doc_type = :doc_type)
            ORDER BY similarity(c.content, :q) DESC
            LIMIT :k
        """)
        rows = db.execute(sql, {"pats": pats, "q": query,
                                "doc_type": doc_type, "k": k}).all()
        return [r[0] for r in rows]

    # ── RRF 融合 ──
    def _rrf(self, rankings: list[list[int]]) -> dict[int, float]:
        k = self.settings.rrf_k
        scores: dict[int, float] = {}
        for ranking in rankings:
            for rank, chunk_id in enumerate(ranking):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
        return scores

    def _load_chunks(self, db: Session, chunk_ids: list[int]) -> list[RetrievedChunk]:
        sql = text("""
            SELECT c.id, c.content, d.doc_name, d.doc_type
            FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id
            WHERE c.id = ANY (:ids)
        """)
        rows = db.execute(sql, {"ids": chunk_ids}).all()
        return [RetrievedChunk(r[0], r[1], r[2], r[3], 0.0) for r in rows]

    # ── 格式化为 Agent 可读文本 ──
    @staticmethod
    def format(chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return "知识库中未检索到相关内容。"
        parts = []
        for i, c in enumerate(chunks, 1):
            parts.append(f"[{i}] 来源: {c.doc_name} ({c.doc_type})\n{c.content}")
        return "\n\n".join(parts)
