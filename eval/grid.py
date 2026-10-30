"""
grid.py — 參數實驗：網格搜尋 (F-15、PRD 6.1a Step 4)

比較 CHUNK_SIZE × TOP_K 的所有組合，只評估檢索（不呼叫 Claude，免費）。
每種切片大小建一次暫存索引，再用不同 TOP_K 查詢；不碰 app 的 chroma_db/。

輸出：
- 3×3 命中率矩陣、MRR 矩陣、平均送給 Claude 的字數（成本參考）
- 原本漏掉的題目在各組合是否被救回
- 每個組合追加一列到 results.csv（mode = grid）

執行（在專案資料夾）：
    .venv\\Scripts\\python.exe eval\\grid.py
"""
import importlib.util
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("eval_script", EVAL_DIR / "eval.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)   # 共用 eval.py 的建索引與計分邏輯（同時完成 sys.path 與編碼設定）

import config                  # noqa: E402
from retriever import search   # noqa: E402

CHUNK_SIZES = [300, 500, 800]
TOP_KS = [3, 4, 5]
WATCH = ["Q11", "Q12", "Q13", "Q17"]   # 目前設定 (500 / 4) 漏掉的題目


def main():
    questions = [q for q in ev.load_questions() if q["type"] == "in_doc"]
    print(f"題庫：文件內 {len(questions)} 題；重疊固定 {config.CHUNK_OVERLAP} 字元；"
          f"檢索模式 {config.SEARCH_MODE}；只評估檢索（免費）\n")

    results = {}   # (size, k) -> {"ranks": {id: rank}, "chars": 平均送出字數, "n_chunks": 切片數}
    for size in CHUNK_SIZES:
        col, n_chunks, _ = ev.build_index(chunk_size=size)
        docs = col.get(include=["documents"])["documents"]

        # 公平性檢查：答案原文必須完整存在於某個切片，否則這題在此切法下不可能命中
        broken = [q["id"] for q in questions
                  if not any(ev.norm(e) in ev.norm(d) for e in q["evidence"] for d in docs)]
        note = f"，答案被切斷 {broken}" if broken else "，答案原文皆完整"
        print(f"切片 {size}：共 {n_chunks} 塊，平均 {sum(map(len, docs)) / len(docs):.0f} 字{note}")

        for k in TOP_KS:
            ranks, chars = {}, 0
            for q in questions:
                hits = search(q["q"], k=k, collection=col)
                ranks[q["id"]] = ev.first_hit_rank(hits, q["evidence"])
                chars += sum(len(h.text) for h in hits)
            results[(size, k)] = {"ranks": ranks, "chars": chars / len(questions), "n_chunks": n_chunks}

    n = len(questions)

    def hit_rate(r):
        return sum(1 for v in r["ranks"].values() if v) / n

    def mrr(r):
        return sum(1 / v for v in r["ranks"].values() if v) / n

    def matrix(title, fmt):
        print(f"\n{title}")
        print("切片＼TOP_K " + "".join(f"{k:>10}" for k in TOP_KS))
        for size in CHUNK_SIZES:
            cells = []
            for k in TOP_KS:
                cell = fmt(results[(size, k)])
                if (size, k) == (config.CHUNK_SIZE, config.TOP_K):
                    cell = "★" + cell        # ★ = 目前的設定
                cells.append(f"{cell:>10}")
            print(f"{size:>8}    " + "".join(cells))

    matrix("① 檢索命中率（越高越好）", lambda r: f"{hit_rate(r):.0%}")
    matrix("② MRR（答案排越前面越高）", lambda r: f"{mrr(r):.3f}")
    matrix("③ 平均送給 Claude 的字數（越少越省錢）", lambda r: f"{r['chars']:.0f}")

    # 原本漏掉的題目：各組合是否救回（數字 = 答案排第幾名，✘ = 沒找到）
    print("\n④ 原本漏掉的題目（數字＝答案排第幾名；✘＝沒找到）")
    combos = [(s, k) for s in CHUNK_SIZES for k in TOP_KS]
    print("題目  " + "".join(f"{f'{s}/{k}':>8}" for s, k in combos))
    for qid in WATCH:
        cells = [results[c]["ranks"][qid] for c in combos]
        print(f"{qid}  " + "".join(f"{(str(v) if v else '✘'):>8}" for v in cells))

    # 新出現的漏題：目前設定找得到、其他組合卻漏掉
    base = results[(config.CHUNK_SIZE, config.TOP_K)]["ranks"]
    for c in combos:
        lost = [qid for qid, v in results[c]["ranks"].items() if base[qid] and not v]
        if lost and c != (config.CHUNK_SIZE, config.TOP_K):
            print(f"  ⚠ {c[0]}/{c[1]} 反而漏掉目前找得到的：{lost}")

    # 最佳組合：命中率最高 → MRR 最高 → 送出字數最少（省錢）
    best = max(combos, key=lambda c: (hit_rate(results[c]), mrr(results[c]), -results[c]["chars"]))
    b = results[best]
    print(f"\n最佳組合：切片 {best[0]}、TOP_K {best[1]}  →  命中率 {hit_rate(b):.0%}、MRR {mrr(b):.3f}、"
          f"平均送出 {b['chars']:.0f} 字")
    cur = results[(config.CHUNK_SIZE, config.TOP_K)]
    print(f"目前設定：切片 {config.CHUNK_SIZE}、TOP_K {config.TOP_K}  →  命中率 {hit_rate(cur):.0%}、"
          f"MRR {mrr(cur):.3f}、平均送出 {cur['chars']:.0f} 字")

    # 每個組合追加到 results.csv，之後可用 Excel 比較
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    for (size, k), r in results.items():
        summary = {"time": now, "mode": "grid", "chunk_size": size, "chunk_overlap": config.CHUNK_OVERLAP,
                   "top_k": k, "embedding_model": config.EMBEDDING_MODEL, "n_chunks": r["n_chunks"],
                   "n_in_doc": n, "hit_rate": round(hit_rate(r), 4), "mrr": round(mrr(r), 4),
                   "note": f"網格搜尋（{config.SEARCH_MODE}）；平均送出 {r['chars']:.0f} 字"}
        ev.append_result(summary)
    print(f"\n9 組結果已追加到 {ev.RESULTS.name}")


if __name__ == "__main__":
    main()
