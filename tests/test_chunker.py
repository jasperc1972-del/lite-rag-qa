"""
test_chunker.py — 文本切片 (F-02) 的單元測試

純邏輯測試：不載入 Embedding 模型、不碰 ChromaDB、不呼叫 Claude API。
"""
import config
from chunker import chunk_documents, split_text
from loaders import Document

# PRD F-02 規格值：測試對照「規格」，不跟著 config.py 走，
# 這樣有人改錯設定時測試才會失敗
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def test_設定值符合PRD規格():
    # 若是刻意調整參數（例如 F-15 實驗後），請同步更新 PRD 與上方規格值
    assert config.CHUNK_SIZE == CHUNK_SIZE
    assert config.CHUNK_OVERLAP == CHUNK_OVERLAP


# ---------- split_text：單段長文字切塊 ----------

def test_短文字不切():
    assert split_text("一段很短的文字。") == ["一段很短的文字。"]


def test_空字串回傳空清單():
    assert split_text("") == []
    assert split_text("   \n  ") == []


def test_沒有分隔符時依字數切並重疊():
    # 1200 個數字字元，沒有任何可切開的符號 → 只能硬切
    text = "".join(str(i % 10) for i in range(1200))
    pieces = split_text(text)

    step = CHUNK_SIZE - CHUNK_OVERLAP
    assert pieces[0] == text[:CHUNK_SIZE]
    assert pieces[1] == text[step:step + CHUNK_SIZE]
    assert pieces[-1] == text[2 * step:]
    # 相鄰兩塊重疊 CHUNK_OVERLAP 個字元
    assert pieces[0][-CHUNK_OVERLAP:] == pieces[1][:CHUNK_OVERLAP]


def test_每塊不超過上限():
    text = "".join(f"這是第{i}句測試內容，用來檢查切片長度。" for i in range(200))
    assert all(len(p) <= CHUNK_SIZE for p in split_text(text))


def test_優先在句號切開():
    text = "".join(f"這是第{i}句測試內容。" for i in range(100))
    pieces = split_text(text)
    assert len(pieces) > 1
    # 除了最後一塊，每塊都應該停在句號，而不是把句子切斷
    assert all(p.endswith("。") for p in pieces[:-1])


def test_切完不漏內容():
    text = "".join(f"第{i}段內容。\n" for i in range(300))
    joined = "".join(split_text(text))
    for i in range(300):
        assert f"第{i}段內容。" in joined


# ---------- chunk_documents：整份檔案切片 ----------

def _paragraphs(texts, source="a.docx"):
    """建立段落型 Document 清單（段落編號從 1 開始）"""
    return [Document(t, {"source": source, "format": "docx", "paragraph": i})
            for i, t in enumerate(texts, start=1)]


def test_短段落合併並標出段落範圍():
    chunks = chunk_documents(_paragraphs(["第一段", "第二段", "第三段"]))
    assert len(chunks) == 1
    assert chunks[0].text == "第一段\n第二段\n第三段"
    assert chunks[0].metadata["location"] == "第 1-3 段"


def test_單一段落標示單段():
    chunks = chunk_documents(_paragraphs(["只有一段"]))
    assert chunks[0].metadata["location"] == "第 1 段"


def test_合併超過上限時另起一塊():
    para = "字" * 300
    chunks = chunk_documents(_paragraphs([para, para, para]))
    # 每段 300 字，兩段合併會超過 500 → 每段各自一塊
    assert [c.metadata["location"] for c in chunks] == ["第 1 段", "第 2 段", "第 3 段"]


def test_過長段落單獨切開():
    chunks = chunk_documents(_paragraphs(["短段落", "長" * 1200, "另一個短段落"]))
    locations = [c.metadata["location"] for c in chunks]
    assert locations[0] == "第 1 段"
    assert locations[-1] == "第 3 段"
    assert locations.count("第 2 段") >= 3   # 1200 字至少切成 3 塊


def test_PDF每頁獨立不跨頁():
    docs = [Document("第一頁內容", {"source": "a.pdf", "format": "pdf", "page": 1}),
            Document("第二頁內容", {"source": "a.pdf", "format": "pdf", "page": 2})]
    chunks = chunk_documents(docs)
    assert [c.text for c in chunks] == ["第一頁內容", "第二頁內容"]
    assert [c.metadata["location"] for c in chunks] == ["p.1", "p.2"]


def test_切片編號連續且保留來源():
    chunks = chunk_documents(_paragraphs(["甲" * 400, "乙" * 400, "丙" * 400], source="規格書.docx"))
    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))
    assert all(c.metadata["source"] == "規格書.docx" for c in chunks)
