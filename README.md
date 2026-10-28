# lite-rag-qa — 輕量 RAG 檢索問答（R1）

規格見 `C:\Rag\PRD_v2.2.docx`。

## 安裝（使用 Python 3.13）
```
cd C:\Rag\lite-rag-qa
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 設定
編輯 `.env`，把 `ANTHROPIC_API_KEY` 換成你的 API Key。

## 啟動
```
streamlit run app.py
```
瀏覽器會自動開啟 http://localhost:8501 。第一次啟動會下載 Embedding 模型（約 470 MB）。

## 檔案說明
| 檔案 | 用途 |
|---|---|
| `app.py` | Streamlit 介面 |
| `config.py` | 設定值（讀取 .env） |
| `loaders/` | 讀檔模組與格式註冊表（改 `CURRENT_RELEASE` 切換版本） |
| `chunker.py` | 文本切片 |
| `ingest.py` | 建立 / 刪除 / 重建索引、預覽、匯出 |
| `retriever.py` | 語意檢索 |
| `llm.py` | Claude 呼叫、防幻覺 Prompt、來源標註 |
