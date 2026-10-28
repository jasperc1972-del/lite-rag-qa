"""
docx_loader.py — Word 讀檔模組 (R1)

用 python-docx 依「文件原本的順序」讀出段落與表格，
每個段落（或表格的每一列）輸出一個 Document，並記錄段落編號。
"""
import io

from . import Document, LoaderError


def load(filename: str, data: bytes) -> list:
    """讀取 .docx 位元組內容，回傳每段一個 Document"""
    import docx  # python-docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        word = docx.Document(io.BytesIO(data))
    except Exception as e:
        raise LoaderError(f"「{filename}」無法開啟，請確認是 .docx 格式（舊版 .doc 請先另存新檔）：{e}")

    blocks = []
    # 直接走訪文件主體的子元素，才能讓段落與表格維持原本的前後順序
    for child in word.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = Paragraph(child, word).text.strip()
            if text:
                blocks.append(text)
        elif tag == "tbl":
            # 表格每一列合併成一行，欄位間用「｜」分隔
            for row in Table(child, word).rows:
                cells = [c.text.strip() for c in row.cells]
                # 合併儲存格會重複出現，去掉相鄰重複值
                dedup = [c for i, c in enumerate(cells) if c and (i == 0 or c != cells[i - 1])]
                if dedup:
                    blocks.append("｜".join(dedup))

    return [Document(t, {"source": filename, "format": "docx", "paragraph": i})
            for i, t in enumerate(blocks, start=1)]
