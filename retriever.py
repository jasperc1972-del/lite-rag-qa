"""
retriever.py — 語意檢索 (F-04)

把使用者的問題向量化，到 ChromaDB 找出語意最接近的 Top-K 個切片。
"""
from dataclasses import dataclass

import config
from ingest import get_collection


@dataclass
class Hit:
    """一筆檢索結果"""
    text: str
    source: str      # 檔名
    location: str    # 「p.3」或「第 2-4 段」
    score: float     # 相似度 0~1，越大越相關

    @property
    def label(self) -> str:
        """來源標註文字，例如「規格書.pdf p.3」"""
        return f"{self.source} {self.location}"


def search(query: str, k: int = config.TOP_K, collection=None) -> list:
    """回傳與問題最相關的 k 個切片；索引為空時回傳空清單

    collection: 要查詢的 ChromaDB collection；預設為 app 使用的本機索引，
                評估腳本會傳入自己建立的暫存索引 (F-13)
    """
    col = collection if collection is not None else get_collection()
    total = col.count()
    if total == 0:
        return []

    res = col.query(query_texts=[query], n_results=min(k, total),
                    include=["documents", "metadatas", "distances"])
    hits = []
    for text, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        # 餘弦距離 0 代表完全相同，換算成直覺的相似度分數
        hits.append(Hit(text=text, source=meta["source"], location=meta["location"], score=1 - dist))
    return hits
