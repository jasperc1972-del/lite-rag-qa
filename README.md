# lite-rag-qa — 輕量 RAG 檢索問答（R1）

把 PDF、Word、Markdown、TXT 放進去，用中文提問；Claude 只根據你的文件回答，並標註出處（檔名＋頁碼／段落），找不到就直接說找不到。

▶️ **示範影片**：https://www.youtube.com/watch?v=KsfMsHeP24w
📖 **操作手冊**：[docs/使用手冊.md](docs/使用手冊.md)
📋 **需求規格（PRD V2.3）**：[docs/PRD_v2.3.docx](docs/PRD_v2.3.docx)

## 快速開始（Windows，建議 Python 3.13）
```
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # 再用記事本填入 ANTHROPIC_API_KEY
```
之後雙擊 **啟動.bat**，瀏覽器會開啟 http://localhost:8501 。第一次啟動會下載 Embedding 模型（約 470 MB）。

## 技術
Python｜Claude API（Sonnet 5.5）｜ChromaDB｜sentence-transformers（多語言模型）｜PyMuPDF｜python-docx｜Streamlit

## 實作原則
不使用 LangChain / LlamaIndex 等編排框架；切片、檢索、Prompt 組裝與來源標註皆為專案內手寫程式，直接呼叫 anthropic SDK 與基礎函式庫。

## 檔案說明
| 檔案 | 用途 |
|---|---|
| `app.py` | Streamlit 介面 |
| `config.py` | 設定值（讀取 .env） |
| `loaders/` | 讀檔模組與格式註冊表（改 `CURRENT_RELEASE` 切換版本） |
| `chunker.py` | 文本切片 |
| `ingest.py` | 建立／刪除／重建索引、預覽、匯出 |
| `retriever.py` | 語意檢索 |
| `llm.py` | Claude 呼叫、來源標註 |
| `prompts.py` | 防幻覺 System Prompt 與版本號（改 Prompt 時遞增版本） |
| `qa_log.py` | 問答紀錄：每次問答寫入 `logs/qa_YYYYMM.jsonl`（不入版控） |
| `啟動.bat` | 雙擊啟動程式 |
| `tests/` | 單元測試（切片、讀檔、格式註冊表、Prompt、紀錄、評估計分） |
| `eval/` | 評估：`questions.jsonl` 題庫、`eval.py` 評估腳本、`results.csv` 歷次結果 |

## 執行測試
```
.venv\Scripts\python.exe -m pytest tests
```
測試不載入模型、不呼叫 API，約 3 秒完成。

回歸測試（平常不執行，需要時手動指定）：
```
.venv\Scripts\python.exe -m pytest -m eval    發版前：檢索命中率不可低於基準（免費，約 15 秒）
.venv\Scripts\python.exe -m pytest -m llm     驗收時：文件外問題全部拒答、有答案時不誤拒答（會產生 API 費用）
```

## 評估（題庫打分數）
```
.venv\Scripts\python.exe eval\eval.py          只評估檢索，免費
.venv\Scripts\python.exe eval\eval.py --llm    連同 Claude 回答一起評估（會產生 API 費用）
```

## 版本規劃
| 版本 | 支援格式 |
|---|---|
| **R1（目前）** | PDF（文字層）、.docx、.md、.txt |
| R1.1（規劃中） | 品質補強：評估集、問答紀錄、參數實驗、Prompt 版本管理（格式不變） |
| R2 | ＋ Excel .xlsx、.csv |
| R3 | ＋ 圖片、掃描型 PDF（本機 OCR） |
