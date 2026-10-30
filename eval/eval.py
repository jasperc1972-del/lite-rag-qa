"""
eval.py — 評估腳本 (F-13、F-15)

用固定題庫 (questions.jsonl) 替整個 RAG 流程打分數。

做法：
1. 把 uploads/ 裡的原始檔用「和 app 相同的讀檔、切片、Embedding 流程」建一份暫存索引
   （放在記憶體，不碰 app 的 chroma_db/，app 開著也能跑）
2. 每題檢索 Top-K，檢查題目的「答案原文 (evidence)」有沒有出現在取回的片段中
   —— 用原文判斷而不是段落編號，改了切片大小後同一份題庫仍然適用
3. 加上 --llm 時再呼叫 Claude，檢查拒答、來源標註與答案關鍵字（會產生 API 費用）
4. 本次參數與指標附加一列到 results.csv；逐題明細寫到 last_run.jsonl

執行（在專案資料夾）：
    .venv\\Scripts\\python.exe eval\\eval.py          只評估檢索，免費
    .venv\\Scripts\\python.exe eval\\eval.py --llm    連同 Claude 回答一起評估
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")          # Embedding 模型已下載，不連網
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")  # 關閉 ChromaDB 遙測
sys.stdout.reconfigure(encoding="utf-8")

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parent))   # 讓腳本找得到專案模組

import config                              # noqa: E402
from chunker import chunk_documents        # noqa: E402
from loaders import LoaderError, get_loader  # noqa: E402
from prompts import NOT_FOUND, PROMPT_VERSION  # noqa: E402
from retriever import search               # noqa: E402

QUESTIONS = EVAL_DIR / "questions.jsonl"
RESULTS = EVAL_DIR / "results.csv"
LAST_RUN = EVAL_DIR / "last_run.jsonl"


def norm(text: str) -> str:
    """去掉所有空白再比對，避免換行、空格差異造成誤判"""
    return re.sub(r"\s+", "", text).lower()


def load_questions() -> list:
    with open(QUESTIONS, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@lru_cache(maxsize=1)
def _embedding_function():
    """Embedding 模型只載入一次；參數實驗要重建多次索引時可省下載入時間"""
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    return SentenceTransformerEmbeddingFunction(model_name=config.EMBEDDING_MODEL)


def build_index(chunk_size: int = None, overlap: int = None):
    """用 uploads/ 的原始檔建一份記憶體中的暫存索引，回傳 (collection, 切片數, 檔名清單)

    chunk_size / overlap 不指定時用 config 的值；參數實驗 (grid.py) 會傳入其他值
    """
    import chromadb

    size = chunk_size or config.CHUNK_SIZE
    ovl = config.CHUNK_OVERLAP if overlap is None else overlap
    client = chromadb.EphemeralClient()
    name = "eval"
    if name in [c.name for c in client.list_collections()]:
        client.delete_collection(name)
    col = client.create_collection(
        name=name,
        embedding_function=_embedding_function(),
        metadata={"hnsw:space": "cosine"},   # 和 app 一樣用餘弦距離
    )

    files = sorted(p for p in config.UPLOAD_DIR.iterdir() if p.is_file()) if config.UPLOAD_DIR.exists() else []
    total = 0
    for path in files:
        try:
            chunks = chunk_documents(get_loader(path.name)(path.name, path.read_bytes()), size, ovl)
        except LoaderError as e:
            print(f"  略過 {path.name}：{e}")
            continue
        col.add(ids=[f"{path.name}::{c.metadata['chunk_index']}" for c in chunks],
                documents=[c.text for c in chunks],
                metadatas=[c.metadata for c in chunks])
        total += len(chunks)
    return col, total, [p.name for p in files]


def first_hit_rank(hits: list, evidence: list) -> int:
    """回傳第一個包含答案原文的片段名次（1 起算）；都沒有則回傳 0"""
    keys = [norm(e) for e in evidence]
    for rank, h in enumerate(hits, start=1):
        if any(k in norm(h.text) for k in keys):
            return rank
    return 0


def judge_answer(q: dict, hits: list, result) -> dict:
    """檢查 Claude 的回答：是否拒答、來源是否正確、關鍵字是否齊全"""
    refused = result.text.strip().startswith(NOT_FOUND)
    if q["type"] == "out_of_doc":
        return {"refused": refused, "refuse_ok": refused}

    # 被引用的片段中，至少一個含答案原文 → 來源標註正確
    keys = [norm(e) for e in q["evidence"]]
    cited_hits = [h for h in hits if h.label in result.sources]
    source_ok = any(any(k in norm(h.text) for k in keys) for h in cited_hits)
    # 關鍵字可寫成「A|B|C」，回答出現任一種寫法即算有提到
    answer = norm(result.text)
    missing = [kw for kw in q.get("expect", [])
               if not any(norm(alt) in answer for alt in kw.split("|"))]
    return {"refused": refused, "refuse_ok": not refused, "source_ok": source_ok,
            "keyword_ok": not missing, "missing": missing}


def pct(n: int, d: int) -> str:
    return f"{n}/{d} = {n / d:.0%}" if d else "—"


def evaluate(use_llm: bool = False, verbose: bool = True):
    """跑完整份題庫並計分，回傳 (逐題結果 rows, 統計 summary)

    eval.py 指令列與 pytest 回歸測試 (tests/test_regression.py) 共用這個函式，
    確保兩邊的計分方式完全一致。
    """
    say = print if verbose else (lambda *a, **k: None)
    if use_llm:
        import llm
        if not config.api_key_ready():
            raise RuntimeError("尚未設定 ANTHROPIC_API_KEY，無法評估 Claude 回答。")

    questions = load_questions()
    in_doc = [q for q in questions if q["type"] == "in_doc"]
    out_doc = [q for q in questions if q["type"] == "out_of_doc"]
    say(f"題庫：{len(questions)} 題（文件內 {len(in_doc)}、文件外 {len(out_doc)}）")
    say(f"參數：CHUNK_SIZE={config.CHUNK_SIZE}  OVERLAP={config.CHUNK_OVERLAP}  TOP_K={config.TOP_K}"
        f"  Prompt={PROMPT_VERSION}")
    say("建立暫存索引中（載入 Embedding 模型）...")
    col, n_chunks, files = build_index()
    if n_chunks == 0:
        raise RuntimeError("uploads/ 沒有可用的文件，請先在 app 上傳文件。")
    say(f"索引：{', '.join(files)}，共 {n_chunks} 塊\n")

    rows = []
    for q in questions:
        start = time.perf_counter()
        hits = search(q["q"], collection=col)
        row = {"id": q["id"], "type": q["type"], "q": q["q"],
               "hits": [{"label": h.label, "score": round(h.score, 4)} for h in hits],
               "top_score": round(hits[0].score, 4) if hits else 0.0}
        if q["type"] == "in_doc":
            row["rank"] = first_hit_rank(hits, q["evidence"])
        if use_llm:
            result = llm.answer(q["q"], hits)
            row.update(judge_answer(q, hits, result))
            row.update(answer=result.text, cited=result.sources,
                       input_tokens=result.input_tokens, output_tokens=result.output_tokens)
        row["sec"] = round(time.perf_counter() - start, 2)
        rows.append(row)

        # 逐題顯示：✔ 命中（第幾名）/ ✘ 沒找到；文件外題目顯示最高分供參考
        if q["type"] == "in_doc":
            mark = f"✔ 第{row['rank']}名" if row["rank"] else "✘ 未命中"
        else:
            mark = f"（文件外，最高分 {row['top_score']:.2f}）"
        extra = ""
        if use_llm:
            if q["type"] == "out_of_doc":
                extra = "  拒答✔" if row["refuse_ok"] else "  ✘沒有拒答"
            else:
                extra = ("  ✘誤拒答" if row["refused"] else
                         f"  來源{'✔' if row['source_ok'] else '✘'} 關鍵字{'✔' if row['keyword_ok'] else '✘缺' + '、'.join(row['missing'])}")
        say(f"{q['id']} {mark:<16}{extra}  {q['q']}")

    # ---- 統計 ----
    ranked = [r for r in rows if r["type"] == "in_doc"]
    hit = sum(1 for r in ranked if r["rank"])
    mrr = sum(1 / r["rank"] for r in ranked if r["rank"]) / len(ranked)
    summary = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "mode": "llm" if use_llm else "retrieval",
        "chunk_size": config.CHUNK_SIZE, "chunk_overlap": config.CHUNK_OVERLAP, "top_k": config.TOP_K,
        "embedding_model": config.EMBEDDING_MODEL, "claude_model": config.CLAUDE_MODEL if use_llm else "",
        "prompt_version": PROMPT_VERSION if use_llm else "",
        "n_chunks": n_chunks, "n_in_doc": len(ranked), "n_out_of_doc": len(out_doc),
        "hit_rate": round(hit / len(ranked), 4), "mrr": round(mrr, 4),
    }
    say("\n========== 結果 ==========")
    say(f"檢索命中率：{pct(hit, len(ranked))}（答案原文出現在前 {config.TOP_K} 個片段中）")
    say(f"MRR：{mrr:.3f}（答案排越前面越接近 1）")

    if use_llm:
        refuse_ok = sum(1 for r in rows if r["type"] == "out_of_doc" and r["refuse_ok"])
        src_ok = sum(1 for r in ranked if r["source_ok"])
        kw_ok = sum(1 for r in ranked if r["keyword_ok"])
        wrong_refuse = sum(1 for r in ranked if r["refused"])
        summary.update(
            refuse_acc=round(refuse_ok / len(out_doc), 4) if out_doc else "",
            source_acc=round(src_ok / len(ranked), 4), keyword_acc=round(kw_ok / len(ranked), 4),
            wrong_refuse=wrong_refuse,
            avg_sec=round(sum(r["sec"] for r in rows) / len(rows), 2),
            avg_input_tokens=round(sum(r["input_tokens"] for r in rows) / len(rows)),
            avg_output_tokens=round(sum(r["output_tokens"] for r in rows) / len(rows)))
        say(f"拒答正確率：{pct(refuse_ok, len(out_doc))}（文件外問題正確回答找不到）")
        say(f"來源正確率：{pct(src_ok, len(ranked))}（引用的片段含答案原文）")
        say(f"關鍵字齊全：{pct(kw_ok, len(ranked))}（回答包含預期關鍵字）")
        say(f"文件內誤拒答：{wrong_refuse} 題")
        say(f"平均耗時 {summary['avg_sec']} 秒；平均 token 輸入 {summary['avg_input_tokens']}、"
            f"輸出 {summary['avg_output_tokens']}")
    return rows, summary


RESULT_FIELDS = ["time", "mode", "chunk_size", "chunk_overlap", "top_k", "embedding_model", "claude_model",
                 "prompt_version", "n_chunks", "n_in_doc", "n_out_of_doc", "hit_rate", "mrr", "refuse_acc",
                 "source_acc", "keyword_acc", "wrong_refuse", "avg_sec", "avg_input_tokens",
                 "avg_output_tokens", "note"]


def append_result(summary: dict):
    """results.csv 追加一列 (F-15)；eval.py 與 grid.py 共用"""
    new_file = not RESULTS.exists()
    with open(RESULTS, "a", encoding="utf-8-sig", newline="") as f:   # utf-8-sig：Excel 開啟中文不亂碼
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow({k: summary.get(k, "") for k in RESULT_FIELDS})


def save(rows: list, summary: dict):
    """results.csv 追加一列；last_run.jsonl 覆寫逐題明細"""
    append_result(summary)
    with open(LAST_RUN, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="lite-rag-qa 評估腳本")
    parser.add_argument("--llm", action="store_true", help="同時呼叫 Claude 評估回答（會產生 API 費用）")
    parser.add_argument("--note", default="", help="寫進 results.csv 的備註，例如「Prompt v2 基準」")
    args = parser.parse_args()
    try:
        rows, summary = evaluate(use_llm=args.llm)
    except RuntimeError as e:
        sys.exit(str(e))
    summary["note"] = args.note
    save(rows, summary)
    print(f"\n已記錄到 {RESULTS.name}；逐題明細在 {LAST_RUN.name}")


if __name__ == "__main__":
    main()
