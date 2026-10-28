"""
pdf_loader.py — PDF 讀檔模組 (R1)

用 PyMuPDF 逐頁擷取文字，每頁輸出一個 Document 並記錄頁碼。
整份 PDF 都抓不到文字時，判定為掃描檔並拒收 (F-00c)。
"""
from . import Document, LoaderError, ScannedPdfError


def load(filename: str, data: bytes) -> list:
    """讀取 PDF 位元組內容，回傳每頁一個 Document（空白頁略過）"""
    import pymupdf  # PyMuPDF；放在函式內匯入，沒裝套件時其他模組仍可運作

    try:
        pdf = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:
        raise LoaderError(f"「{filename}」無法開啟，可能已損毀或有密碼保護：{e}")

    docs = []
    with pdf:
        for page_no, page in enumerate(pdf, start=1):  # 頁碼從 1 開始，與閱讀器一致
            text = page.get_text("text").strip()
            if text:
                docs.append(Document(text, {"source": filename, "format": "pdf", "page": page_no}))

    # 沒有任何一頁有文字 → 掃描型 PDF
    if not docs:
        raise ScannedPdfError(f"「{filename}」為掃描型 PDF（沒有文字層），請改於 R3 版本使用。")
    return docs
