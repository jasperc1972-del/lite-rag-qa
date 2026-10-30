"""
test_eval.py — 評估腳本 (F-13) 計分邏輯的單元測試

評估腳本算錯，所有參數比較都會跟著錯，所以計分規則本身也要測。
不建索引、不載入模型、不呼叫 API。
"""
import importlib.util
import json
from pathlib import Path

import pytest

from llm import Answer
from prompts import NOT_FOUND
from retriever import Hit

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"

# eval/eval.py 和內建函式 eval 同名，用檔案路徑載入
_spec = importlib.util.spec_from_file_location("eval_script", EVAL_DIR / "eval.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)


def _hit(text, label="a.docx 第 1 段"):
    source, location = label.split(" ", 1)
    return Hit(text=text, source=source, location=location, score=0.5)


def test_比對忽略空白與換行():
    hits = [_hit("無關內容"), _hit("單塊上限 500\n字元、重疊 50 字元")]
    assert ev.first_hit_rank(hits, ["單塊上限 500 字元、重疊 50 字元"]) == 2


def test_多個答案出處任一命中即可():
    hits = [_hit("寫入 ChromaDB")]
    assert ev.first_hit_rank(hits, ["寫入本機 ChromaDB", "寫入 ChromaDB"]) == 1


def test_沒找到回傳0():
    assert ev.first_hit_rank([_hit("無關內容")], ["答案"]) == 0


def test_文件外問題正確拒答():
    q = {"type": "out_of_doc"}
    assert ev.judge_answer(q, [], Answer(text=f"{NOT_FOUND}。"))["refuse_ok"] is True
    assert ev.judge_answer(q, [], Answer(text="營收目標是一億"))["refuse_ok"] is False


def test_來源與關鍵字判斷():
    q = {"type": "in_doc", "evidence": ["Top-K 預設 4"], "expect": ["4", "片段"]}
    hits = [_hit("Top-K 預設 4", "a.docx 第 1 段"), _hit("無關", "a.docx 第 2 段")]

    good = ev.judge_answer(q, hits, Answer(text="預設取 4 個片段 [1]", sources=["a.docx 第 1 段"]))
    assert good["source_ok"] and good["keyword_ok"] and not good["refused"]

    # 引用了不含答案的片段 → 來源錯；少了「片段」→ 關鍵字缺
    bad = ev.judge_answer(q, hits, Answer(text="預設取 4 個 [2]", sources=["a.docx 第 2 段"]))
    assert not bad["source_ok"]
    assert bad["missing"] == ["片段"]


def test_關鍵字可寫多種說法():
    q = {"type": "in_doc", "evidence": ["x"], "expect": ["重疊50|50字元"]}
    assert ev.judge_answer(q, [], Answer(text="切片 500 字元，重疊 50 字元"))["keyword_ok"]
    assert ev.judge_answer(q, [], Answer(text="每塊 50 字元"))["keyword_ok"]
    # 只有 500、沒有 50 → 不可被「500 裡面含 50」誤判通過
    assert not ev.judge_answer(q, [], Answer(text="切片 500 字元"))["keyword_ok"]


def test_文件內問題卻拒答算誤拒答():
    q = {"type": "in_doc", "evidence": ["答案"], "expect": []}
    r = ev.judge_answer(q, [], Answer(text=NOT_FOUND))
    assert r["refused"] and not r["refuse_ok"]


@pytest.mark.parametrize("line", (EVAL_DIR / "questions.jsonl").read_text(encoding="utf-8").splitlines())
def test_題庫格式正確(line):
    q = json.loads(line)
    assert q["type"] in ("in_doc", "out_of_doc") and q["q"]
    if q["type"] == "in_doc":
        assert q["evidence"], f"{q['id']} 缺少答案原文"
