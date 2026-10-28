"""
text_loader.py — Markdown / TXT 讀檔模組 (R1)

先用 UTF-8 解碼，失敗再改用 Big5（台灣舊系統常見的編碼）；
以空行分段，每段輸出一個 Document 並記錄段落編號。
"""
import re

from . import Document, LoaderError

# 依序嘗試的編碼；utf-8-sig 可自動去掉記事本存檔時加的 BOM，cp950 是 Windows 的 Big5
ENCODINGS = ["utf-8-sig", "cp950"]


def _decode(filename: str, data: bytes) -> str:
    """嘗試多種編碼把位元組轉成文字"""
    for enc in ENCODINGS:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise LoaderError(f"「{filename}」編碼無法辨識，請另存為 UTF-8 後再上傳。")


def load(filename: str, data: bytes) -> list:
    """讀取 .md / .txt 位元組內容，回傳每段一個 Document"""
    text = _decode(filename, data).replace("\r\n", "\n")
    fmt = filename.rsplit(".", 1)[-1].lower()

    # 一個以上的空行視為段落分隔
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return [Document(p, {"source": filename, "format": fmt, "paragraph": i})
            for i, p in enumerate(paragraphs, start=1)]
