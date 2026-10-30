"""
llm.py — 呼叫 Claude 產生回答 (F-05、F-06、F-07)

做法：
1. 把檢索到的片段編號成 [1]、[2]…，連同問題一起送給 Claude
2. System Prompt 嚴格限制「只能根據片段回答，找不到就說找不到」(F-06)；內容放在 prompts.py
3. 要求 Claude 在句子後面用 [編號] 標出依據；參考來源清單由程式依編號產生，
   不讓模型自己寫檔名，確保來源一定正確、只列實際引用的片段 (F-07)
"""
import re
from dataclasses import dataclass, field

import anthropic

import config
from prompts import NOT_FOUND, PROMPT_VERSION, SYSTEM_PROMPT  # Prompt 集中管理 (F-15a)

# 多輪對話時，最多帶入幾則先前訊息（讓追問「那它的單價呢？」看得懂上下文）
HISTORY_LIMIT = 6


class LLMError(Exception):
    """Claude 呼叫失敗，訊息會直接顯示在介面上 (F-10)"""


@dataclass
class Answer:
    """一次問答的結果"""
    text: str                                   # Claude 的回答（含 [編號] 標記）
    sources: list = field(default_factory=list)  # 實際引用的來源標註，例如 ["規格書.pdf p.3"]
    hits: list = field(default_factory=list)     # 本次檢索到的全部片段（供 F-08 展開檢視）
    # 以下供問答紀錄 (F-14) 使用；沒有呼叫 API 時維持預設值
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    prompt_version: str = PROMPT_VERSION


def _build_user_message(question: str, hits: list) -> str:
    """把參考片段與問題組成送給 Claude 的訊息"""
    blocks = [f"[{i}] 來源：{h.label}\n{h.text}" for i, h in enumerate(hits, start=1)]
    context = "\n\n".join(blocks) if blocks else "（沒有檢索到任何片段）"
    return f"<參考片段>\n{context}\n</參考片段>\n\n問題：{question}"


def _cited_sources(text: str, hits: list) -> list:
    """從回答中找出 [編號]，換成對應的來源標註（去除重複、保留出現順序）"""
    sources = []
    for n in re.findall(r"\[(\d+)\]", text):
        idx = int(n) - 1
        if 0 <= idx < len(hits) and hits[idx].label not in sources:
            sources.append(hits[idx].label)
    return sources


def _create(client: anthropic.Anthropic, messages: list):
    """送出請求；Sonnet / Opus 開啟伺服器端備援，被安全機制拒答時自動改由其他模型接手"""
    params = dict(
        model=config.CLAUDE_MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=messages,
        output_config={"effort": "medium"},  # 問答屬一般難度，medium 兼顧品質與速度、成本
    )
    if "sonnet" in config.CLAUDE_MODEL or "opus" in config.CLAUDE_MODEL:
        return client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params)
    return client.messages.create(**params)


def answer(question: str, hits: list, history: list = None) -> Answer:
    """根據檢索片段回答問題

    question: 使用者問題
    hits:     retriever.search() 的結果
    history:  先前對話 [{"role": "user"/"assistant", "content": "..."}]
    """
    if not config.api_key_ready():
        raise LLMError("尚未設定 ANTHROPIC_API_KEY，請在專案資料夾的 .env 填入 API Key 後重新啟動。")

    # 沒有任何片段時不呼叫 API，直接回覆找不到，省時也省費用
    if not hits:
        return Answer(text=f"{NOT_FOUND}（目前索引中沒有相關內容，請先上傳文件）。")

    messages = list((history or [])[-HISTORY_LIMIT:])
    messages.append({"role": "user", "content": _build_user_message(question, hits)})

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    try:
        response = _create(client, messages)
    except anthropic.AuthenticationError:
        raise LLMError("API Key 無效，請確認 .env 中的 ANTHROPIC_API_KEY。")
    except anthropic.PermissionDeniedError:
        raise LLMError("此 API Key 沒有使用該模型的權限。")
    except anthropic.NotFoundError:
        raise LLMError(f"找不到模型「{config.CLAUDE_MODEL}」，請確認 .env 中的 CLAUDE_MODEL。")
    except anthropic.RateLimitError:
        raise LLMError("請求太頻繁或額度不足，請稍後再試。")
    except anthropic.BadRequestError as e:
        raise LLMError(f"請求格式錯誤：{e.message}")
    except anthropic.APIStatusError as e:
        raise LLMError(f"Claude 服務錯誤 ({e.status_code})，請稍後再試。")
    except anthropic.APIConnectionError:
        raise LLMError("無法連線到 Claude，請檢查網路。")

    # 實際回應的模型與 token 用量（備援時模型可能和設定不同）
    usage = dict(model=response.model,
                 input_tokens=response.usage.input_tokens,
                 output_tokens=response.usage.output_tokens)

    if response.stop_reason == "refusal":
        return Answer(text="這個問題無法回答（已被安全機制拒絕）。", hits=hits, **usage)

    # 回應可能包含思考、備援等其他區塊，只取文字部分
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if response.stop_reason == "max_tokens":
        text += "\n\n（回答過長被截斷）"

    sources = [] if text.startswith(NOT_FOUND) else _cited_sources(text, hits)
    return Answer(text=text, sources=sources, hits=hits, **usage)
