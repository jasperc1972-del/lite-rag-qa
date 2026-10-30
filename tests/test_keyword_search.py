"""
test_keyword_search.py — 關鍵字檢索與混合檢索的單元測試

不載入 Embedding 模型：混合檢索用假的 collection 模擬語意排名。
"""
import config
from keyword_search import BM25, rrf, tokenize
from retriever import search


# ---------- 斷詞 ----------

def test_中文每相鄰兩字一組():
    assert tokenize("重複上傳") == ["重複", "複上", "上傳"]


def test_英文與程式名稱保持完整且不分大小寫():
    tokens = tokenize("用 PDF_Loader 讀取 .env 與 Top-K")
    assert {"pdf_loader", ".env", "top-k"} <= set(tokens)


def test_單一中文字也保留():
    assert "檔" in tokenize("檔")


# ---------- BM25 ----------

def test_罕見詞的權重高於到處都有的詞():
    docs = ["上傳文件", "上傳圖片", "上傳表格", "重複上傳時覆蓋舊索引"]
    scores = BM25(docs).scores("重複上傳")
    assert scores.index(max(scores)) == 3       # 只有這份有「重複」，應該排第一


def test_完全沒有相同詞的文件得零分():
    assert BM25(["蘋果香蕉", "螺絲扭力"]).scores("蘋果")[1] == 0


# ---------- RRF ----------

def test_兩邊都排前面的勝出():
    assert rrf([["a", "b", "c"], ["b", "a", "c"]])[-1] == "c"


def test_k越小越重視第一名():
    # T：關鍵字第 1 名、語意第 10 名；M：兩邊都第 3 名
    vector = ["v1", "v2", "M", "v4", "v5", "v6", "v7", "v8", "v9", "T"]
    keyword = ["T", "k2", "M"]
    order = lambda k: rrf([vector, keyword], k=k)
    assert order(60).index("M") < order(60).index("T")   # k 大：兩邊都不錯的 M 勝
    assert order(1).index("T") < order(1).index("M")     # k 小：有一邊第一名的 T 勝


# ---------- 混合檢索 ----------

class FakeCollection:
    """模擬 ChromaDB：語意排名固定照 docs 的順序（第一筆最像）"""

    def __init__(self, docs):
        self.docs = docs

    def count(self):
        return len(self.docs)

    def query(self, query_texts, n_results, include):
        n = min(n_results, len(self.docs))
        return {"ids": [[f"id{i}" for i in range(n)]],
                "documents": [self.docs[:n]],
                "metadatas": [[{"source": "a.docx", "location": f"第 {i + 1} 段"} for i in range(n)]],
                "distances": [[0.1 * i for i in range(n)]]}


DOCS = ["格式提示與上傳確認", "上傳元件與副檔名", "解析結果摘要", "切片數量與預覽",
        "向量化與儲存：同檔重複上傳時覆蓋舊索引"]   # 語意排最後，但含「重複上傳」


def test_純語意找不到關鍵字被稀釋的片段():
    hits = search("同一個檔案重複上傳會怎樣", k=3, collection=FakeCollection(DOCS), mode="vector")
    assert "覆蓋舊索引" not in "".join(h.text for h in hits)


def test_混合檢索靠關鍵字救回(monkeypatch):
    monkeypatch.setattr(config, "RRF_K", 5)
    hits = search("同一個檔案重複上傳會怎樣", k=3, collection=FakeCollection(DOCS), mode="hybrid")
    assert any("覆蓋舊索引" in h.text for h in hits)
    assert all(0 <= h.score <= 1 for h in hits)   # 顯示的仍是語意相似度
