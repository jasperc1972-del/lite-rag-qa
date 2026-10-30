"""
retriever.py — 檢索 (F-04)

兩種模式（config.SEARCH_MODE）：
- vector：把問題向量化，到 ChromaDB 找出語意最接近的 Top-K 個切片
- hybrid：語意排名 ＋ 關鍵字 (BM25) 排名，用 RRF 合併後取 Top-K
          補足「重點字詞被整塊切片的語意稀釋」的情況（見 keyword_search.py）
"""
from dataclasses import dataclass

import config
from ingest import get_collection
from keyword_search import BM25, rrf


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


def search(query: str, k: int = config.TOP_K, collection=None, mode: str = None) -> list:
    """回傳與問題最相關的 k 個切片；索引為空時回傳空清單

    collection: 要查詢的 ChromaDB collection；預設為 app 使用的本機索引，
                評估腳本會傳入自己建立的暫存索引 (F-13)
    mode:       "vector" 或 "hybrid"；預設取 config.SEARCH_MODE
    """
    col = collection if collection is not None else get_collection()
    total = col.count()
    if total == 0:
        return []
    if (mode or config.SEARCH_MODE) == "hybrid":
        return _hybrid(col, query, k, total)

    res = col.query(query_texts=[query], n_results=min(k, total),
                    include=["documents", "metadatas", "distances"])
    hits = []
    for text, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        # 餘弦距離 0 代表完全相同，換算成直覺的相似度分數
        hits.append(Hit(text=text, source=meta["source"], location=meta["location"], score=1 - dist))
    return hits


def _hybrid(col, query: str, k: int, total: int) -> list:
    """混合檢索：全部切片各排一次語意名次與關鍵字名次，RRF 合併後取前 k 個

    本專案是單人本機的小型知識庫（數十到數百塊），每次對全部切片評分即可；
    切片上萬時才需要改成先各取候選、再合併。
    """
    # 語意排名，同時保留每塊的相似度（介面顯示的分數仍是語意相似度）
    res = col.query(query_texts=[query], n_results=total,
                    include=["documents", "metadatas", "distances"])
    by_id = {i: Hit(text=t, source=m["source"], location=m["location"], score=1 - d)
             for i, t, m, d in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])}
    vector_rank = res["ids"][0]

    # 關鍵字排名：只排有命中任何詞的切片
    ids = list(by_id)
    scores = BM25([by_id[i].text for i in ids]).scores(query)
    keyword_rank = [i for i, s in sorted(zip(ids, scores), key=lambda x: x[1], reverse=True) if s > 0]

    return [by_id[i] for i in rrf([vector_rank, keyword_rank], k=config.RRF_K)[:k]]
