"""
chunker.py — 文本切片 (F-02)

把讀檔模組輸出的 Document 切成適合檢索的小塊：
- 段落型（Word / MD / TXT）：相鄰的短段落合併，直到接近 500 字元，來源標成「第 3-5 段」
- 頁面型（PDF）：每頁各自切，不跨頁，來源標成「p.頁碼」
- 單段過長時，優先在換行、句號等位置切開，相鄰兩塊重疊 50 字元以保留上下文
"""
from config import CHUNK_OVERLAP, CHUNK_SIZE
from loaders import Document

# 切開位置的優先順序：段落 > 換行 > 中英文句尾 > 空白
SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", ". ", "! ", "? ", " "]


def split_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list:
    """把一段長文字切成多塊，每塊不超過 size 字元，相鄰兩塊重疊 overlap 字元"""
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []

    pieces, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # 在這一塊的後半段找最後一個適合切開的位置，避免把句子切斷
            window = text[start + size // 2:end]
            for sep in SEPARATORS:
                pos = window.rfind(sep)
                if pos != -1:
                    end = start + size // 2 + pos + len(sep)
                    break
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)  # 往回退 overlap 字元作為下一塊開頭
    return pieces


def _location(meta: dict) -> str:
    """把 metadata 轉成來源標註文字，例如「p.3」或「第 2-4 段」"""
    if "page" in meta:
        return f"p.{meta['page']}"
    first, last = meta["paragraph"], meta.get("paragraph_end", meta["paragraph"])
    return f"第 {first} 段" if first == last else f"第 {first}-{last} 段"


def chunk_documents(docs: list, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list:
    """把整份檔案的 Document 清單轉成切片清單；每塊 metadata 會加上 location 與 chunk_index

    size / overlap 預設取 config；參數實驗 (F-15) 會傳入其他值比較效果
    """
    chunks = []

    def emit(text: str, meta: dict):
        meta = {**meta, "location": _location(meta), "chunk_index": len(chunks)}
        chunks.append(Document(text, meta))

    # 段落合併用的暫存區
    buf, buf_meta = [], None

    def flush():
        nonlocal buf, buf_meta
        if buf:
            emit("\n".join(buf), buf_meta)
        buf, buf_meta = [], None

    for doc in docs:
        meta = doc.metadata
        if "page" in meta:
            # PDF：每頁獨立切片
            for piece in split_text(doc.text, size, overlap):
                emit(piece, meta)
            continue

        # 段落型：過長的段落單獨切開
        if len(doc.text) > size:
            flush()
            for piece in split_text(doc.text, size, overlap):
                emit(piece, meta)
            continue

        # 加上這段會超過上限 → 先把暫存區輸出
        current_len = sum(len(b) + 1 for b in buf)
        if buf and current_len + len(doc.text) > size:
            flush()
        if not buf:
            buf_meta = dict(meta)
        buf.append(doc.text)
        buf_meta["paragraph_end"] = meta["paragraph"]

    flush()
    return chunks
