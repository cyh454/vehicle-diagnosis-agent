# app/api/routes/knowledge.py
"""知识库管理 API：上传入库、检索调试、文档管理。"""
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.retriever import HybridRetriever
from app.db.database import get_db
from app.rag.vector_store import KnowledgeIngestor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["知识库"])

ALLOWED_SUFFIX = {".txt", ".md", ".pdf", ".docx"}


@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form("standard"),
    db: Session = Depends(get_db),
):
    """上传文档并入库（自动分块、向量化）。支持 txt/md/pdf/docx。"""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIX:
        raise HTTPException(400, f"不支持的文件类型 {suffix}，支持: {sorted(ALLOWED_SUFFIX)}")
    save_dir = Path(get_settings().upload_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / (file.filename or "upload.txt")
    with save_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        ingestor = KnowledgeIngestor()
        n = ingestor.ingest_file(db, save_path, doc_type=doc_type)
    except Exception as e:
        logger.exception("入库失败")
        raise HTTPException(500, f"入库失败: {e}")
    return {"doc_name": file.filename, "chunks": n, "doc_type": doc_type}


@router.post("/search")
def search_knowledge(query: str, doc_type: str = "", top_k: int = 5,
                     db: Session = Depends(get_db)):
    """RAG 检索调试接口（向量+关键词混合检索）。"""
    retriever = HybridRetriever()
    chunks = retriever.search(db, query, doc_type=doc_type or None, top_k=top_k)
    return {
        "query": query,
        "results": [
            {"doc_name": c.doc_name, "doc_type": c.doc_type,
             "score": c.score, "content": c.content}
            for c in chunks
        ],
    }


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    rows = db.execute(text(
        "SELECT id, doc_name, doc_type, source, chunk_count, created_at "
        "FROM kb_documents ORDER BY id DESC LIMIT 200"
    )).all()
    return {"total": len(rows), "documents": [
        {"id": r[0], "doc_name": r[1], "doc_type": r[2], "source": r[3],
         "chunks": r[4], "created_at": r[5].isoformat() if r[5] else None}
        for r in rows
    ]}


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    res = db.execute(text("DELETE FROM kb_documents WHERE id = :id"), {"id": doc_id})
    db.commit()
    if res.rowcount == 0:
        raise HTTPException(404, "文档不存在")
    return {"deleted": doc_id}
