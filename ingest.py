"""
ingest.py — 建立與管理本機向量索引 (F-03、F-09、F-11、F-12)

流程：讀檔模組 → 切片 → 多語言 Embedding → 寫入 ChromaDB。
ChromaDB 每筆同時保存「向量＋切片文字＋metadata」，所以預覽與匯出都直接從資料庫讀。
上傳的原始檔另存在 uploads/，供「重新建立索引」使用。
"""
import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import config
from chunker import chunk_documents
from loaders import LoaderError, get_loader


@dataclass
class IndexResult:
    """單一檔案建立索引的結果，供介面顯示解析摘要 (F-11a)"""
    source: str
    format: str = ""
    units: int = 0          # PDF 為有文字的頁數，其他為段落數
    unit_name: str = ""     # 「頁」或「段」
    chunks: int = 0
    error: str = ""         # 失敗原因；成功時為空字串


@lru_cache(maxsize=1)
def get_collection():
    """取得 ChromaDB collection（整個程式只建立一次，模型載入較慢）"""
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    embed_fn = SentenceTransformerEmbeddingFunction(model_name=config.EMBEDDING_MODEL)
    # 用餘弦距離比較語意相似度
    return client.get_or_create_collection(
        name=config.COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )


def index_file(filename: str, data: bytes, save_upload: bool = True) -> IndexResult:
    """解析單一檔案並寫入索引；同名檔案會先刪除舊索引再寫入，避免重複 (F-03)"""
    result = IndexResult(source=filename)
    try:
        loader = get_loader(filename)      # 不支援的格式在這裡就會被擋下
        docs = loader(filename, data)
    except LoaderError as e:
        result.error = str(e)
        return result

    if not docs:
        result.error = "檔案中沒有讀到任何文字（可能是空白檔）。"
        return result

    chunks = chunk_documents(docs)
    meta0 = docs[0].metadata
    result.format = meta0["format"]
    result.unit_name = "頁" if "page" in meta0 else "段"
    result.units = len(docs)
    result.chunks = len(chunks)

    col = get_collection()
    col.delete(where={"source": filename})  # 覆蓋舊索引

    indexed_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    col.add(
        ids=[f"{filename}::{c.metadata['chunk_index']}" for c in chunks],
        documents=[c.text for c in chunks],
        metadatas=[{**c.metadata, "indexed_at": indexed_at} for c in chunks],
    )

    if save_upload:
        config.UPLOAD_DIR.mkdir(exist_ok=True)
        (config.UPLOAD_DIR / Path(filename).name).write_bytes(data)  # 只取檔名，避免路徑跳脫
    return result


def list_indexed() -> list:
    """列出已建立索引的檔案：檔名、格式、切片數、建立時間 (F-11c)"""
    col = get_collection()
    if col.count() == 0:
        return []
    files = {}
    for m in col.get(include=["metadatas"])["metadatas"]:
        f = files.setdefault(m["source"], {"source": m["source"], "format": m.get("format", ""),
                                           "chunks": 0, "indexed_at": m.get("indexed_at", "")})
        f["chunks"] += 1
    return sorted(files.values(), key=lambda f: f["source"])


def get_chunks(source: str) -> list:
    """取出某檔案的全部切片（依切片順序），回傳 [(文字, metadata), ...] (F-11b)"""
    res = get_collection().get(where={"source": source}, include=["documents", "metadatas"])
    pairs = list(zip(res["documents"], res["metadatas"]))
    return sorted(pairs, key=lambda p: p[1]["chunk_index"])


def delete_source(source: str):
    """刪除單一檔案的索引與上傳的原始檔 (F-11c)"""
    get_collection().delete(where={"source": source})
    (config.UPLOAD_DIR / Path(source).name).unlink(missing_ok=True)


def rebuild_all() -> list:
    """清空索引，再把 uploads/ 裡的所有原始檔重新建立索引 (F-09)"""
    col = get_collection()
    existing = col.get(include=[])["ids"]
    if existing:
        col.delete(ids=existing)
    if not config.UPLOAD_DIR.exists():
        return []
    return [index_file(p.name, p.read_bytes(), save_upload=False)
            for p in sorted(config.UPLOAD_DIR.iterdir()) if p.is_file()]


def export_source(source: str, fmt: str) -> str:
    """把某檔案的全部切片匯出成 txt 或 jsonl 文字 (F-12)"""
    chunks = get_chunks(source)
    if fmt == "jsonl":
        return "\n".join(json.dumps({"text": t, "metadata": m}, ensure_ascii=False) for t, m in chunks)
    return "\n\n".join(f"===== 切片 {m['chunk_index'] + 1}｜{m['location']} =====\n{t}" for t, m in chunks)
