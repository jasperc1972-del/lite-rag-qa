"""
config.py — 集中管理所有設定值

從專案根目錄的 .env 讀取 API Key 與模型名稱；
其餘固定參數（切片大小、資料夾路徑）也統一放在這裡，方便日後調整。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 專案根目錄（本檔所在的資料夾）
BASE_DIR = Path(__file__).resolve().parent

# 讀取 .env；override=False 表示系統環境變數優先
load_dotenv(BASE_DIR / ".env", override=False)

# ---- Claude API ----
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

# ---- Embedding 與檢索 ----
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
TOP_K = int(os.getenv("TOP_K", "4"))  # 每次檢索取回的片段數（PRD 建議 3~5）
# 檢索模式：vector＝純語意；hybrid＝語意＋關鍵字 (BM25) 以 RRF 合併
# 評估結果（22 題）：vector 命中 82%、MRR 0.523；hybrid 命中 86%、MRR 0.689
SEARCH_MODE = os.getenv("SEARCH_MODE", "hybrid")
# RRF 常數：越小越重視各排名的前幾名。論文值 60 適合大型搜尋引擎，
# 本專案切片只有數十塊，60 會讓第 1 名與第 18 名差距太小；實驗 5 最佳
RRF_K = int(os.getenv("RRF_K", "5"))

# ---- 切片參數（單位：字元）----
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# ---- 本機資料夾 ----
CHROMA_DIR = BASE_DIR / "chroma_db"   # 向量索引
UPLOAD_DIR = BASE_DIR / "uploads"     # 上傳的原始檔（供「重新建立索引」使用）
LOG_DIR = BASE_DIR / "logs"           # 問答紀錄 (F-14)，含問題與回答內容，不入版控
COLLECTION_NAME = "documents"


def api_key_ready() -> bool:
    """檢查 API Key 是否已填寫（不是空的、也不是範本佔位字）"""
    return bool(ANTHROPIC_API_KEY) and ANTHROPIC_API_KEY != "your_actual_api_key_here"
