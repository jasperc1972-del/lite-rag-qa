# lite-rag-qa — 輕量 RAG 檢索問答

把 PDF、Word、Markdown、TXT 放進去，用中文提問；Claude 只根據你的文件回答，並標註出處（檔名＋頁碼／段落），找不到就直接說找不到。

不使用 LangChain / LlamaIndex 等框架，讀檔、切片、檢索、Prompt 組裝與來源標註全部手寫，並以評估集量化每一次改動的效果。

▶️ **示範影片**：https://www.youtube.com/watch?v=KsfMsHeP24w
📖 **操作手冊**：[docs/使用手冊.md](docs/使用手冊.md)
📋 **需求規格（PRD V2.4）**：[docs/PRD_v2.4.docx](docs/PRD_v2.4.docx)
✅ **R1.1 驗收報告**：[docs/R1.1_驗收報告.md](docs/R1.1_驗收報告.md)

## 成果（R1.1 驗收，Claude Sonnet 5.5）

| 指標 | 結果 |
|---|---|
| 檢索命中率 | **91%**（20/22）；混合檢索將命中率由 82% 提升至 86%，題庫校正後驗收為 91% |
| MRR | 0.523 → **0.689**（混合檢索，+32%）；驗收 0.735 |
| 文件外問題拒答 | **5/5**，零編造 |
| 平均回應時間 | 約 2.5 秒 |
| 測試 | 81 項單元測試＋檢索與回答品質回歸測試 |

評估題庫：27 題（文件內 22、文件外 5），單一文件；各指標定義與已知限制見驗收報告。

## 運作方式

```
建立索引：上傳文件 → 讀檔 → 切片（500 字、重疊 50）→ 多語言 Embedding → ChromaDB

問答：問題 ─┬→ 語意檢索（ChromaDB 餘弦相似度）─┐
            └→ 關鍵字檢索（手寫 BM25）────────┴→ RRF 合併取前 4 塊
          → 接地式 System Prompt ＋ 片段 → Claude → 回答＋[編號]
          → 程式依編號對回「檔名＋頁碼／段落」→ 顯示來源
```

## 設計重點

- **混合檢索**：語意檢索遇到「一個切片混了好幾個主題」時，重點字詞會被稀釋；加入手寫 BM25 關鍵字檢索並以 RRF 合併。RRF 常數依知識庫規模由論文值 60 調整為 5——追查發現 BM25 已把答案排第 1 名，但 k=60 把訊號平均掉了。
- **防幻覺**：System Prompt 限定只能根據片段回答、找不到時回覆固定句；部分回答時說「提供的片段中未提及」而非「文件中沒有」（模型看不到整份文件）。來源清單由程式依 [編號] 產生，模型無法編造出處。
- **用數據做決定**：評估題庫以「答案原文」判斷檢索命中，改切片大小後仍適用；網格搜尋比較 9 組切片大小 × Top-K，驗證預設設定。
- **可追溯**：每次問答記錄檢索來源與分數、Prompt 版本、token 與耗時，答錯時可判斷是檢索還是生成的問題。
- **本機優先**：文件、索引、Embedding 都在本機，只有「問題＋檢索片段」送到 Claude API。

## 快速開始（Windows，建議 Python 3.13）

```
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # 再用記事本填入 ANTHROPIC_API_KEY
```

之後雙擊 **啟動.bat**，瀏覽器會開啟 http://localhost:8501 。第一次啟動會下載 Embedding 模型（約 470 MB）。

## 測試與評估

```
.venv\Scripts\python.exe -m pytest              單元測試（不載入模型、不呼叫 API，約 3 秒）
.venv\Scripts\python.exe -m pytest -m eval      回歸：檢索命中率不可低於基準（免費，約 15 秒）
.venv\Scripts\python.exe -m pytest -m llm       回歸：文件外全部拒答、有答案時不誤拒答（會產生 API 費用）

.venv\Scripts\python.exe eval\eval.py           評估檢索（免費）
.venv\Scripts\python.exe eval\eval.py --llm     連同 Claude 回答一起評估（會產生 API 費用）
.venv\Scripts\python.exe eval\grid.py           參數網格搜尋（免費）
```

每次評估的參數與指標都會追加到 `eval/results.csv`。

## 技術

Python｜Claude API（Sonnet 5.5）｜ChromaDB｜sentence-transformers（paraphrase-multilingual-MiniLM-L12-v2）｜PyMuPDF｜python-docx｜Streamlit｜pytest

## 檔案說明

| 檔案 | 用途 |
|---|---|
| `app.py` | Streamlit 介面 |
| `config.py` | 設定值（讀取 .env） |
| `loaders/` | 讀檔模組與格式註冊表（改 `CURRENT_RELEASE` 切換版本） |
| `chunker.py` | 文本切片 |
| `ingest.py` | 建立／刪除／重建索引、預覽、匯出 |
| `retriever.py` | 檢索：語意＋關鍵字混合（`SEARCH_MODE`） |
| `keyword_search.py` | 關鍵字檢索：手寫 BM25 與 RRF 排名融合 |
| `llm.py` | Claude 呼叫、來源標註 |
| `prompts.py` | 防幻覺 System Prompt 與版本號（改 Prompt 時遞增版本） |
| `qa_log.py` | 問答紀錄：每次問答寫入 `logs/qa_YYYYMM.jsonl`（不入版控） |
| `啟動.bat` | 雙擊啟動程式 |
| `tests/` | 單元測試與回歸測試 |
| `eval/` | 評估：`questions.jsonl` 題庫、`eval.py` 評估、`grid.py` 網格搜尋、`results.csv` 歷次結果 |

## 版本規劃

| 版本 | 內容 | 狀態 |
|---|---|---|
| R1 | PDF（文字層）、.docx、.md、.txt 問答與來源標註 | ✔ 完成 |
| R1.1 | 品質補強：單元測試、評估集、問答紀錄、參數實驗、Prompt 版本管理、混合檢索 | ✔ 完成 |
| R2 | ＋ Excel .xlsx、.csv | 規劃中 |
| R3 | ＋ 圖片、掃描型 PDF（本機 OCR） | 規劃中 |
