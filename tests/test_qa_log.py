"""
test_qa_log.py — 問答紀錄 (F-14) 的單元測試

紀錄寫到 pytest 提供的暫存資料夾，不會動到專案的 logs/。
"""
import json

import pytest

import config
import qa_log
from llm import Answer
from retriever import Hit

HITS = [Hit(text="片段一", source="規格書.pdf", location="p.3", score=0.81234),
        Hit(text="片段二", source="手冊.docx", location="第 2-4 段", score=0.6)]


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    """把紀錄資料夾換成暫存資料夾"""
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "logs")
    return tmp_path / "logs"


def _read_all(log_dir):
    files = list(log_dir.glob("qa_*.jsonl"))
    assert len(files) == 1                      # 同一個月只會有一個檔
    lines = files[0].read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_成功問答的紀錄內容(log_dir):
    result = Answer(text="扭力為 25 N·m [1]", sources=["規格書.pdf p.3"], hits=HITS,
                    model="claude-sonnet-5-5", input_tokens=1200, output_tokens=80)
    qa_log.log_qa("扭力多少？", HITS, result, elapsed=2.345)

    rec = _read_all(log_dir)[0]
    assert rec["question"] == "扭力多少？"
    assert rec["answer"] == "扭力為 25 N·m [1]"
    assert rec["cited"] == ["規格書.pdf p.3"]
    assert rec["hits"][0] == {"source": "規格書.pdf", "location": "p.3", "score": 0.8123}
    assert (rec["input_tokens"], rec["output_tokens"]) == (1200, 80)
    assert rec["model"] == "claude-sonnet-5-5"
    assert rec["prompt_version"] == result.prompt_version
    assert rec["elapsed_sec"] == 2.35
    assert rec["error"] == ""


def test_紀錄不含片段全文(log_dir):
    qa_log.log_qa("問題", HITS, Answer(text="回答"))
    assert "片段一" not in json.dumps(_read_all(log_dir)[0], ensure_ascii=False)


def test_失敗也要留紀錄(log_dir):
    qa_log.log_qa("問題", HITS, error="API Key 無效")
    rec = _read_all(log_dir)[0]
    assert rec["error"] == "API Key 無效"
    assert rec["answer"] == ""
    assert len(rec["hits"]) == 2               # 檢索結果仍保留，方便判斷問題出在哪


def test_多筆紀錄依序追加且中文不轉碼(log_dir):
    qa_log.log_qa("第一題", [], Answer(text="甲"))
    qa_log.log_qa("第二題", [], Answer(text="乙"))
    assert [r["question"] for r in _read_all(log_dir)] == ["第一題", "第二題"]
    raw = next(log_dir.glob("qa_*.jsonl")).read_text(encoding="utf-8")
    assert "第一題" in raw                     # 直接寫中文，記事本打開就看得懂


def test_寫入失敗不影響問答(monkeypatch, tmp_path, capsys):
    # 把紀錄位置指到一個「檔案」而不是資料夾，讓寫入必定失敗
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x")
    monkeypatch.setattr(config, "LOG_DIR", blocker)
    qa_log.log_qa("問題", [], Answer(text="回答"))   # 不應拋出例外
    assert "寫入失敗" in capsys.readouterr().out
