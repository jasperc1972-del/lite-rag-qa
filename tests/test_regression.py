"""
test_regression.py — 用評估題庫做回歸測試 (F-13)

這些測試平常不會執行（pytest.ini 預設排除），需要時手動指定：
    pytest -m eval   發版前：檢索命中率不可低於基準（免費，需載入 Embedding 模型，約 30 秒）
    pytest -m llm    驗收時：拒答與回答品質（會呼叫 Claude API，產生費用）

計分邏輯直接共用 eval/eval.py 的 evaluate()，不另寫一份，避免兩邊算法不一致。
用「比例門檻」而不是「每題必過」：已知檢索不到的題目不會讓測試一開始就失敗，
只有分數比基準差（也就是改壞了）才會失敗。
"""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "eval_script", Path(__file__).resolve().parent.parent / "eval" / "eval.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)

# 檢索命中率基準：混合檢索（hybrid、RRF k=5、切片 500 / 重疊 50 / TOP_K 4）19/22
# 歷史：純語意檢索 18/22 = 0.8182（R1.1 步驟 3）
# 參數實驗 (F-15) 找到更好的設定後，請把基準更新為新的分數
BASELINE_HIT_RATE = 0.8636


@pytest.mark.eval
def test_檢索命中率不低於基準():
    _, summary = ev.evaluate(use_llm=False, verbose=False)
    assert summary["hit_rate"] >= BASELINE_HIT_RATE, (
        f"命中率 {summary['hit_rate']:.0%} 低於基準 {BASELINE_HIT_RATE:.0%}，請檢查最近的修改")


@pytest.fixture(scope="module")
def llm_run():
    """整份題庫只呼叫 Claude 一輪，下面幾項測試共用結果，避免重複花費"""
    return ev.evaluate(use_llm=True, verbose=False)


@pytest.mark.llm
def test_文件外問題全部拒答(llm_run):
    # PRD 7.1a：文件外問題的拒答正確率必須 100%
    rows, _ = llm_run
    failed = [r["id"] for r in rows if r["type"] == "out_of_doc" and not r["refuse_ok"]]
    assert not failed, f"這些文件外問題沒有拒答（可能在編造答案）：{failed}"


@pytest.mark.llm
def test_找得到答案時不可拒答(llm_run):
    # 檢索已經取回含答案的片段，Claude 卻說找不到 → Prompt 或模型有問題
    rows, _ = llm_run
    failed = [r["id"] for r in rows if r["type"] == "in_doc" and r["rank"] and r["refused"]]
    assert not failed, f"這些題目片段中有答案，Claude 卻拒答：{failed}"
