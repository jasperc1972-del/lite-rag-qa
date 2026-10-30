"""
qa_log.py — 問答紀錄 (F-14)

每次問答在 logs/qa_YYYYMM.jsonl 追加一行 JSON，答錯時可以回頭追查：
是檢索沒找到對的片段（看 hits 的來源與分數），還是 Claude 回答有問題（看 answer）。
同時記錄 token 用量與耗時，方便估算成本與效能。

紀錄只存本機；logs/ 已列入 .gitignore。
寫入失敗（例如磁碟權限）不影響問答本身，只在終端機印出警告。
"""
import json
from datetime import datetime

import config


def build_record(question: str, hits: list, result=None, error: str = "", elapsed: float = 0.0) -> dict:
    """組出一筆紀錄

    question: 使用者問題
    hits:     retriever.search() 的結果
    result:   llm.answer() 回傳的 Answer；呼叫失敗時為 None
    error:    錯誤訊息；成功時為空字串
    elapsed:  從檢索到回答完成的秒數
    """
    from prompts import PROMPT_VERSION

    return {
        "time": datetime.now().isoformat(timespec="seconds"),
        "question": question,
        # 只記來源與分數，不記片段全文，避免紀錄檔過大
        "hits": [{"source": h.source, "location": h.location, "score": round(h.score, 4)} for h in hits],
        "answer": result.text if result else "",
        "cited": result.sources if result else [],
        "model": (result.model if result else "") or config.CLAUDE_MODEL,
        "prompt_version": result.prompt_version if result else PROMPT_VERSION,
        "top_k": config.TOP_K,
        "input_tokens": result.input_tokens if result else 0,
        "output_tokens": result.output_tokens if result else 0,
        "elapsed_sec": round(elapsed, 2),
        "error": error,
    }


def write(record: dict):
    """把紀錄追加到當月的 jsonl 檔"""
    try:
        config.LOG_DIR.mkdir(exist_ok=True)
        path = config.LOG_DIR / f"qa_{datetime.now():%Y%m}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"[qa_log] 問答紀錄寫入失敗：{e}")


def log_qa(question: str, hits: list, result=None, error: str = "", elapsed: float = 0.0):
    """組出紀錄並寫入；給 app.py 呼叫的單一入口"""
    write(build_record(question, hits, result, error, elapsed))
