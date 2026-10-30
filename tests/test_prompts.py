"""
test_prompts.py — System Prompt 與版本管理 (F-06、F-15a) 的單元測試
"""
import llm
import prompts


def test_有版本號():
    assert prompts.PROMPT_VERSION.startswith("v")


def test_找不到時的固定回覆寫在規則裡():
    # 評估腳本靠這句判斷是否正確拒答，Prompt 與常數必須一致
    assert f"「{prompts.NOT_FOUND}」" in prompts.SYSTEM_PROMPT


def test_部分回答時說片段中未提及():
    # v2 修正：模型只看得到片段，不能替整份文件下「沒有提到」的結論
    assert "提供的片段中未提及" in prompts.SYSTEM_PROMPT
    assert "不是整份文件" in prompts.SYSTEM_PROMPT


def test_llm使用同一份Prompt():
    # llm.py 不可另外寫一份 Prompt，避免改了一邊忘了另一邊
    assert llm.SYSTEM_PROMPT is prompts.SYSTEM_PROMPT
    assert llm.Answer(text="").prompt_version == prompts.PROMPT_VERSION
