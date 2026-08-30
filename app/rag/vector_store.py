"""向量库 DDL、文档入库（分块 + 向量化 + 批量写入）。"""
import json
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.embeddings import get_embeddings

logger = logging.getLogger(__name__)


def vec_to_str(vec: list[float]) -> str:
    """向量 → pgvector 字面量字符串。"""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def ensure_vector_tables(engine) -> None:
    """创建 kb_documents / kb_chunks（含 HNSW 与 trigram 索引），并校验维度。"""
    s = get_settings()
    dim = s.embedding_dimension
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS kb_documents (
                id          BIGSERIAL PRIMARY KEY,
                doc_name    TEXT NOT NULL,
                doc_type    TEXT NOT NULL DEFAULT 'standard',
                source      TEXT,
                chunk_count INT DEFAULT 0,
                created_at  TIMESTAMPTZ DEFAULT now()
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS kb_chunks (
                id          BIGSERIAL PRIMARY KEY,
                document_id BIGINT NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
                chunk_index INT NOT NULL DEFAULT 0,
                content     TEXT NOT NULL,
                metadata    JSONB DEFAULT '{{}}'::jsonb,
                embedding   vector({dim})
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_kb_chunks_embedding "
            "ON kb_chunks USING hnsw (embedding vector_cosine_ops)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_kb_chunks_trgm "
            "ON kb_chunks USING gin (content gin_trgm_ops)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_kb_chunks_doc ON kb_chunks (document_id)"
        ))
    # 校验已有向量列维度与配置一致（防止换模型后维度不匹配）
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'kb_chunks'::regclass AND attname = 'embedding'"
        )).first()
    if row and row[0] != dim:
        raise RuntimeError(
            f"kb_chunks.embedding 维度为 {row[0]}，与配置 EMBEDDING_DIMENSION={dim} 不一致。"
            f"请保持配置一致，或 DROP 向量表后重新入库。"
        )


def _read_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".markdown", ""}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        import docx  # pip install python-docx
        doc = docx.Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    raise ValueError(f"不支持的文件类型: {path.suffix}")


def split_text(content: str, chunk_size: int, overlap: int) -> list[str]:
    """中文友好的递归分块。"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
    )
    return [c for c in splitter.split_text(content) if c.strip()]


class KnowledgeIngestor:
    """文档入库：同名文档自动覆盖（幂等）。"""

    def __init__(self):
        self.settings = get_settings()
        self.embeddings = get_embeddings()

    def ingest_text(self, db: Session, doc_name: str, content: str,
                    doc_type: str = "standard",
                    source: str | None = None) -> int:
        chunks = split_text(content, self.settings.chunk_size, self.settings.chunk_overlap)
        if not chunks:
            logger.warning("文档 %s 无有效内容，跳过", doc_name)
            return 0

        db.execute(text("DELETE FROM kb_documents WHERE doc_name = :n"), {"n": doc_name})
        doc_id = db.execute(
            text("INSERT INTO kb_documents (doc_name, doc_type, source, chunk_count) "
                 "VALUES (:n, :t, :s, :c) RETURNING id"),
            {"n": doc_name, "t": doc_type, "s": source, "c": len(chunks)},
        ).scalar_one()

        vectors = self.embeddings.embed_documents(chunks)
        batch = 100
        for i in range(0, len(chunks), batch):
            rows = []
            for j, (chunk, vec) in enumerate(zip(chunks[i:i + batch], vectors[i:i + batch])):
                rows.append({
                    "document_id": doc_id,
                    "chunk_index": i + j,
                    "content": chunk,
                    "metadata": json.dumps({"doc_name": doc_name}, ensure_ascii=False),
                    "embedding": vec_to_str(vec),
                })
            db.execute(
                text("INSERT INTO kb_chunks (document_id, chunk_index, content, metadata, embedding) "
                     "VALUES (:document_id, :chunk_index, :content, "
                     "CAST(:metadata AS jsonb), CAST(:embedding AS vector))"),
                rows,
            )
        db.commit()
        logger.info("文档入库完成: %s (%d 块, doc_id=%s)", doc_name, len(chunks), doc_id)
        return len(chunks)

    def ingest_file(self, db: Session, path: str | Path,
                    doc_type: str = "standard") -> int:
        path = Path(path)
        return self.ingest_text(
            db, path.name, _read_file(path), doc_type=doc_type, source=str(path)
        )
