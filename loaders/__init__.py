"""
loaders — 讀檔模組與格式註冊表

每種檔案格式一個讀檔模組，只負責把檔案轉成統一的 Document 清單；
之後的切片、向量化、檢索全部共用，新增格式不需改動共用流程。

FORMATS 是「格式註冊表」：介面上的格式提示框 (F-00) 由它自動產生，
發布新版本時只要把 CURRENT_RELEASE 往後調、補上對應 loader 即可。
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

# 目前發布的產品版本；改成 "R2" / "R3" 後，提示框與上傳限制會自動更新
CURRENT_RELEASE = "R1"
RELEASE_ORDER = ["R1", "R2", "R3"]


@dataclass
class Document:
    """讀檔模組的統一輸出格式

    text:     解析出來的文字
    metadata: 來源資訊，至少包含 source（檔名）；
              PDF 另有 page（頁碼），文字類檔案另有 paragraph（段落編號）
    """
    text: str
    metadata: dict = field(default_factory=dict)


class LoaderError(Exception):
    """讀檔失敗時拋出，訊息會直接顯示在介面上"""


class UnsupportedFormatError(LoaderError):
    """本版不支援的格式"""


class ScannedPdfError(LoaderError):
    """PDF 沒有文字層（掃描檔），需等 R3 的 OCR 支援"""


@dataclass
class FormatSpec:
    """單一格式類別的註冊資料"""
    category: str                 # 類別名稱（A/B/C 三類）
    extensions: list              # 副檔名（小寫、含點）
    label: str                    # 介面上顯示的格式說明
    release: str                  # 從哪一版開始支援
    loader: Optional[Callable] = None  # 讀檔函式；尚未實作的版本為 None


def _build_formats() -> list:
    """建立格式註冊表；loader 延後匯入，避免沒裝套件時整個模組無法載入"""
    from . import docx_loader, pdf_loader, text_loader

    return [
        FormatSpec("A 文字型文件", [".pdf"], "PDF（含文字層，可選取複製文字者）", "R1", pdf_loader.load),
        FormatSpec("A 文字型文件", [".docx"], "Word (.docx)", "R1", docx_loader.load),
        FormatSpec("A 文字型文件", [".md", ".txt"], "Markdown (.md)、文字檔 (.txt)", "R1", text_loader.load),
        FormatSpec("B 表格型文件", [".xlsx", ".csv"], "Excel (.xlsx)、CSV (.csv)", "R2"),
        FormatSpec("C 圖片 / 掃描型文件", [".png", ".jpg", ".jpeg"], "圖片 (.png / .jpg)、掃描型 PDF", "R3"),
    ]


FORMATS = _build_formats()


def _is_released(spec: FormatSpec) -> bool:
    """該格式在目前版本是否已開放（版本已到、且讀檔模組已實作）"""
    return (RELEASE_ORDER.index(spec.release) <= RELEASE_ORDER.index(CURRENT_RELEASE)
            and spec.loader is not None)


def supported_specs() -> list:
    """目前版本可上傳的格式"""
    return [s for s in FORMATS if _is_released(s)]


def unsupported_specs() -> list:
    """目前版本暫不支援的格式（附預計支援版本）"""
    return [s for s in FORMATS if not _is_released(s)]


def supported_extensions() -> list:
    """目前可上傳的副檔名，例如 ['.pdf', '.docx', '.md', '.txt']"""
    return [ext for s in supported_specs() for ext in s.extensions]


def get_loader(filename: str) -> Callable:
    """依副檔名找出讀檔函式；不支援時拋出 UnsupportedFormatError (F-00b)"""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    for spec in FORMATS:
        if ext in spec.extensions:
            if _is_released(spec):
                return spec.loader
            raise UnsupportedFormatError(f"「{filename}」的格式 ({ext}) 將於 {spec.release} 支援，目前版本無法上傳。")
    raise UnsupportedFormatError(f"「{filename}」的格式 ({ext or '無副檔名'}) 不在支援清單內。")
