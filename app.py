"""
app.py — Streamlit 網頁介面 (F-00、F-08 ~ F-12)

啟動方式：streamlit run app.py
畫面分兩個分頁：
- 📁 文件管理：格式提示 → 確認 → 上傳建立索引 → 解析摘要與切片預覽
- 💬 問答：多輪對話、回答附來源、可展開檢視檢索片段
側邊欄：已索引檔案清單、刪除、重建索引、清除對話
"""
import streamlit as st

import config
import ingest
import llm
import retriever
from loaders import CURRENT_RELEASE, supported_extensions, supported_specs, unsupported_specs

st.set_page_config(page_title="輕量 RAG 問答", page_icon="📚", layout="wide")

# ---- 對話紀錄與預覽狀態存在 session_state，重新整理畫面時不會消失 ----
st.session_state.setdefault("messages", [])        # [{"role", "content", "sources", "hits"}]
st.session_state.setdefault("last_results", [])    # 最近一次建立索引的結果
st.session_state.setdefault("preview_n", {})       # 每個檔案目前顯示幾塊切片


def format_notice():
    """F-00：格式提示框，內容由 loaders 的格式註冊表自動產生"""
    ok = "、".join(s.label for s in supported_specs())
    # 注意：粗體記號 ** 要放在冒號前面，「**文字：**內容」在 Markdown 會失效
    lines = [f"**📄 目前版本：{CURRENT_RELEASE}**", "", f"✔ **可上傳**：{ok}"]
    pending = unsupported_specs()
    if pending:
        lines.append("")
        lines.append("✘ **暫不支援**：")
        lines += [f"- {s.label} → 預計 {s.release} 支援" for s in pending]
    lines += ["", "請先將檔案分類，只上傳「可上傳」的檔案。"]
    st.info("\n".join(lines))


def show_results(results: list):
    """F-11a：顯示建立索引的解析摘要"""
    for r in results:
        if r.error:
            st.error(f"❌ {r.source}：解析失敗 — {r.error}")
        else:
            st.success(f"✅ {r.source}（{r.format}）：讀到 {r.units} {r.unit_name}，切成 {r.chunks} 塊")


def show_preview(files: list):
    """F-11b、F-12：每個已索引檔案可展開檢視切片內容，並可匯出"""
    for f in files:
        name = f["source"]
        with st.expander(f"🔍 {name}（{f['chunks']} 塊，建立於 {f['indexed_at']}）"):
            chunks = ingest.get_chunks(name)
            n = st.session_state.preview_n.get(name, 5)  # 預設先顯示前 5 塊
            for text, meta in chunks[:n]:
                st.caption(f"切片 {meta['chunk_index'] + 1}｜{meta['location']}｜{len(text)} 字")
                st.text(text)
            if n < len(chunks) and st.button("再顯示 5 塊", key=f"more_{name}"):
                st.session_state.preview_n[name] = n + 5
                st.rerun()

            # F-12：匯出全部切片
            c1, c2 = st.columns(2)
            stem = name.rsplit(".", 1)[0]
            c1.download_button("匯出 .txt", ingest.export_source(name, "txt"),
                               file_name=f"{stem}_chunks.txt", key=f"txt_{name}")
            c2.download_button("匯出 .jsonl", ingest.export_source(name, "jsonl"),
                               file_name=f"{stem}_chunks.jsonl", key=f"jsonl_{name}")


def sidebar(files: list):
    """F-09、F-11c：側邊欄的檔案清單與操作按鈕"""
    with st.sidebar:
        st.header("📚 已索引檔案")
        if not files:
            st.caption("尚未建立任何索引")
        for f in files:
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{f['source']}**  \n{f['chunks']} 塊｜{f['indexed_at']}")
            if c2.button("🗑", key=f"del_{f['source']}", help="刪除此檔案的索引"):
                ingest.delete_source(f["source"])
                st.rerun()

        st.divider()
        if st.button("🔄 重新建立索引", use_container_width=True,
                     help="清空索引，並用已上傳的原始檔重新解析"):
            with st.spinner("重新建立索引中…"):
                st.session_state.last_results = ingest.rebuild_all()
            st.rerun()
        if st.button("🧹 清除對話紀錄", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

        st.divider()
        st.caption(f"模型：{config.CLAUDE_MODEL}  \nEmbedding：{config.EMBEDDING_MODEL}  \nTop-K：{config.TOP_K}")
        if not config.api_key_ready():
            st.warning("尚未設定 API Key，問答功能無法使用。請編輯 .env 後重新啟動。")


def tab_documents(files: list):
    """📁 文件管理分頁"""
    format_notice()

    # F-00a：勾選確認後才開放上傳
    confirmed = st.checkbox("我已確認要上傳的檔案皆為可上傳格式")

    # F-00b：上傳元件只接受本版支援的副檔名（Streamlit 需要不含點的副檔名）
    uploads = st.file_uploader("上傳文件（可多選）", accept_multiple_files=True,
                               type=[e.lstrip(".") for e in supported_extensions()],
                               disabled=not confirmed)

    if uploads and st.button("📥 建立索引", type="primary"):
        results = []
        progress = st.progress(0.0, text="準備中…")
        for i, up in enumerate(uploads, start=1):
            progress.progress((i - 1) / len(uploads), text=f"處理 {up.name}（{i}/{len(uploads)}）…")
            results.append(ingest.index_file(up.name, up.getvalue()))
        progress.progress(1.0, text="完成")
        st.session_state.last_results = results
        st.rerun()

    if st.session_state.last_results:
        st.subheader("解析結果")
        show_results(st.session_state.last_results)

    if files:
        st.subheader("索引內容預覽")
        show_preview(files)


def tab_chat():
    """💬 問答分頁"""
    # 先建立對話區容器、再放輸入框，讓輸入框固定在對話下方
    box = st.container()
    question = st.chat_input("輸入你的問題…")

    # 顯示歷史對話
    with box:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                render_message(msg)
    if not question:
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with box, st.chat_message("user"):
        st.markdown(question)

    with box, st.chat_message("assistant"):
        with st.spinner("檢索文件並產生回答中…"):
            # 只帶純文字的先前對話給 Claude（不含本次問題）
            history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
            try:
                hits = retriever.search(question)
                result = llm.answer(question, hits, history)
                msg = {"role": "assistant", "content": result.text,
                       "sources": result.sources, "hits": result.hits}
            except llm.LLMError as e:
                msg = {"role": "assistant", "content": f"⚠️ {e}", "sources": [], "hits": []}
        render_message(msg)
    st.session_state.messages.append(msg)


def render_message(msg: dict):
    """顯示一則訊息；助理訊息附來源清單 (F-07) 與可展開的檢索片段 (F-08)"""
    st.markdown(msg["content"])
    if msg.get("sources"):
        st.markdown("**📎 參考來源**\n" + "\n".join(f"- {s}" for s in msg["sources"]))
    if msg.get("hits"):
        with st.expander(f"檢視本次檢索到的 {len(msg['hits'])} 個片段"):
            for i, h in enumerate(msg["hits"], start=1):
                st.caption(f"[{i}] {h.label}｜相似度 {h.score:.2f}")
                st.text(h.text)


# ---- 主畫面 ----
st.title("📚 輕量 RAG 檢索問答")
try:
    # 第一次執行會下載並載入 Embedding 模型，需要一點時間
    with st.spinner("載入向量資料庫與 Embedding 模型…"):
        indexed_files = ingest.list_indexed()
except Exception as e:
    st.error(f"向量資料庫或 Embedding 模型載入失敗：{e}")
    st.stop()

sidebar(indexed_files)
tab1, tab2 = st.tabs(["📁 文件管理", "💬 問答"])
with tab1:
    tab_documents(indexed_files)
with tab2:
    tab_chat()
