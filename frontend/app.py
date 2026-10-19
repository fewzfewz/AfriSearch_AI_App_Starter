import html
import json
import os
import re
import time

import requests
import streamlit as st

API_URL = os.getenv("AFRISEARCH_API_URL", "http://127.0.0.1:8000")
HISTORY_LIMIT = 10
TEXT_TYPES = ["pdf", "txt"]
IMAGE_TYPES = ["png", "jpg", "jpeg", "tif", "tiff", "webp", "bmp"]
PREVIEW_CHARS = 320

st.set_page_config(page_title="AfriSearch AI", page_icon="🌍", layout="wide")

# Values that must survive Streamlit reruns (any widget interaction reruns the script).
st.session_state.setdefault("uploader_key", 0)
st.session_state.setdefault("index_report", None)
st.session_state.setdefault("last_result", None)
st.session_state.setdefault("history", [])

st.markdown(
    """
    <style>
    [data-testid="stMainBlockContainer"] { padding-top: 2.5rem; }
    .afs-hero {
        padding: 1.4rem 1.6rem 1.2rem;
        border-radius: 1rem;
        background: linear-gradient(120deg, #9a3412 0%, #c2410c 45%, #b45309 100%);
        color: #fff;
        margin-bottom: 1.2rem;
    }
    .afs-hero h1 { color: #fff; font-size: 2rem; margin: 0; padding: 0; line-height: 1.2; }
    .afs-hero p { color: rgba(255, 255, 255, 0.92); margin: 0.35rem 0 0.9rem; font-size: 1.02rem; }
    .afs-chips { display: flex; flex-wrap: wrap; gap: 0.45rem; }
    .afs-chip {
        background: rgba(255, 255, 255, 0.16);
        border: 1px solid rgba(255, 255, 255, 0.28);
        border-radius: 999px;
        padding: 0.18rem 0.7rem;
        font-size: 0.82rem;
        white-space: nowrap;
    }
    .afs-step-number {
        display: inline-flex; align-items: center; justify-content: center;
        width: 1.8rem; height: 1.8rem; border-radius: 50%;
        background: #c2410c; color: #fff; font-weight: 700; margin-bottom: 0.4rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def error_detail(exc: requests.RequestException) -> str:
    try:
        return exc.response.json().get("detail", "") or str(exc)
    except Exception:
        return str(exc)


def api_get(path: str, timeout: float = 10):
    response = requests.get(f"{API_URL}{path}", timeout=timeout)
    response.raise_for_status()
    return response.json()


def run_index(full: bool = False) -> None:
    """Call the index endpoint and keep its report for display after the rerun."""
    report = st.session_state.index_report or {"messages": [], "failed": []}
    with st.spinner("Reading documents and building the search index..."):
        response = requests.post(
            f"{API_URL}/documents/index", params={"full": full}, timeout=1800
        )
        response.raise_for_status()
        payload = response.json()
    report["messages"].append(("success", payload.get("message", "Index updated.")))
    report["failed"] = payload.get("failed", [])
    st.session_state.index_report = report


def run_index_safely(full: bool = False) -> None:
    st.session_state.index_report = None
    try:
        run_index(full=full)
    except requests.RequestException as exc:
        st.session_state.index_report = {
            "messages": [("error", f"Indexing failed: {error_detail(exc)}")], "failed": [],
        }
    st.rerun()


def format_pages(source: dict) -> str:
    first, last = source.get("page"), source.get("page_end")
    if not first:
        return ""
    if last and last != first:
        return f"pages {first}-{last}"
    return f"page {first}"


def where_it_runs(provider: dict) -> tuple[str, str, str]:
    """(text, color, icon) for the badge that says where a model runs."""
    if provider["kind"] == "api":
        return "Cloud API", "blue", ":material/cloud:"
    if "CPU" in provider["label"]:
        return "Local · CPU", "green", ":material/laptop:"
    return "Local · GPU", "violet", ":material/memory:"


def file_icon(name: str) -> str:
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix == "pdf":
        return ":material/picture_as_pdf:"
    if suffix in IMAGE_TYPES:
        return ":material/image:"
    return ":material/description:"


def escape_markdown(text: str) -> str:
    # "$" would otherwise start LaTeX math; brackets and asterisks are markdown syntax.
    return re.sub(r"([\\`*_{}\[\]<>#|$~])", r"\\\1", text)


def render_answer_text(text: str) -> str:
    # "$" would otherwise start LaTeX math in Streamlit markdown.
    text = text.replace("$", "\\$")
    # Highlight citation labels such as [S1] or [S1, S2].
    return re.sub(r"\[(S\d+(?:\s*,\s*S\d+)*)\]", r":orange-background[**\1**]", text)


def short_model_name(model_id: str | None) -> str:
    return (model_id or "").rsplit("/", 1)[-1]


# --- Load backend state --------------------------------------------------------

api_ok = True
providers, default_provider, documents, chunk_count = [], None, [], 0
stale_documents, search_model, reranker_model = 0, None, None
ocr = {"available": False, "languages": [], "reason": None}
try:
    provider_data = api_get("/providers")
    providers, default_provider = provider_data["providers"], provider_data["default"]
    doc_data = api_get("/documents")
    documents, chunk_count = doc_data["documents"], doc_data["indexed_chunks"]
    stale_documents, search_model = doc_data.get("stale_documents", 0), doc_data.get("embedder")
    reranker_model = doc_data.get("reranker")
    ocr = doc_data.get("ocr") or ocr
except requests.RequestException:
    api_ok = False

available = [p for p in providers if p["available"]]
unavailable = [p for p in providers if not p["available"]]
by_id = {p["id"]: p for p in providers}

# --- Sidebar: knowledge base ---------------------------------------------------

with st.sidebar:
    st.header(":material/library_books: Knowledge base")
    if not api_ok:
        st.error(f"Cannot reach the API at {API_URL}. Start the FastAPI backend first.",
                 icon=":material/cloud_off:")

    docs_col, chunks_col = st.columns(2)
    docs_col.metric("Documents", len(documents), border=True)
    chunks_col.metric("Passages", chunk_count, border=True,
                      help="Documents are split into passages of about 180 words for searching.")

    if stale_documents:
        st.warning(
            f"{stale_documents} document(s) were indexed with a different search model or settings "
            "and are left out of search until they are re-indexed.",
            icon=":material/sync_problem:",
        )
        if st.button("Re-index now", icon=":material/refresh:", width="stretch"):
            run_index_safely()

    uploads = st.file_uploader(
        "Add documents",
        type=TEXT_TYPES + IMAGE_TYPES,
        accept_multiple_files=True,
        key=f"uploader-{st.session_state.uploader_key}",
        help="PDF, TXT, or photos/scans of documents. Use documents you have permission to process; "
             "files are stored on the machine running the API.",
    )
    if ocr.get("available"):
        st.caption(f":material/document_scanner: Scanned PDFs and photos are read with OCR "
                   f"({', '.join(ocr['languages'])}).")
    else:
        st.caption(f":material/document_scanner: OCR is off, so scanned PDFs and photos can't be read. "
                   f"{ocr.get('reason') or ''}")
    if st.button("Upload and index", type="primary", icon=":material/upload:", width="stretch",
                 disabled=not api_ok):
        report = {"messages": [], "failed": []}
        st.session_state.index_report = report
        try:
            if uploads:
                multipart = [
                    ("files", (file.name, file.getvalue(), "application/octet-stream"))
                    for file in uploads
                ]
                response = requests.post(f"{API_URL}/documents/upload", files=multipart, timeout=120)
                response.raise_for_status()
                payload = response.json()
                report["messages"].append(("success", f"Uploaded {len(payload.get('saved', []))} file(s)."))
                for error in payload.get("errors", []):
                    report["messages"].append(("warning", f"{error['filename']}: {error['error']}"))
            run_index()
            # A new key empties the uploader so the same files aren't sent again.
            st.session_state.uploader_key += 1
        except requests.RequestException as exc:
            report["messages"].append(("error", f"Upload or indexing failed: {error_detail(exc)}"))
        st.rerun()

    report = st.session_state.index_report
    if report:
        for level, message in report["messages"]:
            getattr(st, level)(message)
        for failed in report["failed"]:
            st.warning(f"Not indexed: {failed['filename']} — {failed['error']}")
            if st.button("Remove this file", key=f"remove-failed-{failed['source_id']}",
                         icon=":material/delete:"):
                try:
                    requests.delete(f"{API_URL}/documents/{failed['source_id']}", timeout=30).raise_for_status()
                    report["failed"] = [f for f in report["failed"] if f["source_id"] != failed["source_id"]]
                except requests.RequestException as exc:
                    report["messages"].append(("error", f"Delete failed: {error_detail(exc)}"))
                st.rerun()

    if documents:
        st.subheader("Your documents")
        for doc in documents:
            name_col, delete_col = st.columns([6, 1], vertical_alignment="center")
            ocr_tag = " :gray-badge[OCR]" if doc.get("ocr") else ""
            name_col.markdown(f"{file_icon(doc['source_name'])} {escape_markdown(doc['source_name'])}{ocr_tag}")
            if delete_col.button("", key=f"delete-{doc['source_id']}", icon=":material/delete:",
                                 help=f"Delete {doc['source_name']}", type="tertiary"):
                try:
                    requests.delete(f"{API_URL}/documents/{doc['source_id']}", timeout=30).raise_for_status()
                except requests.RequestException as exc:
                    st.error(f"Delete failed: {error_detail(exc)}")
                else:
                    st.rerun()

    with st.expander("Advanced", icon=":material/tune:"):
        if search_model:
            st.caption(f"Search model: `{search_model}`")
        st.caption(f"Reranker: `{reranker_model}`" if reranker_model else "Reranker: off")
        st.caption("Rebuilding re-reads and re-embeds every document. It is only needed after "
                   "changing chunk settings by hand.")
        if st.button("Rebuild full index", icon=":material/refresh:", width="stretch", disabled=not api_ok):
            run_index_safely(full=True)

# --- Header ----------------------------------------------------------------------

chips = [f"📄 {len(documents)} document{'' if len(documents) == 1 else 's'}"]
if search_model:
    chips.append(f"🔎 {short_model_name(search_model)}")
if reranker_model:
    chips.append("↕️ reranking")
chips.append("👁️ OCR on" if ocr.get("available") else "👁️ OCR off")
if not api_ok:
    chips = ["⚠️ API offline"]
st.markdown(
    f"""
    <div class="afs-hero">
      <h1>🌍 AfriSearch</h1>
      <p>Ask questions about your documents in English, Amharic, Swahili and 90+ other languages.
         Every answer cites the passages it is based on.</p>
      <div class="afs-chips">{''.join(f'<span class="afs-chip">{html.escape(c)}</span>' for c in chips)}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- Empty state ------------------------------------------------------------------

if api_ok and not documents:
    steps = [
        ("Add documents", "Use **Add documents** in the sidebar: PDFs, text files, or photos of pages."),
        ("Index them", "Click **Upload and index**. AfriSearch reads each file and builds a search index."),
        ("Ask", "Ask in any language. You get an answer with numbered citations to the exact passages."),
    ]
    for column, (number, (title, text)) in zip(st.columns(3), enumerate(steps, start=1)):
        with column.container(border=True, height="stretch"):
            st.markdown(f'<span class="afs-step-number">{number}</span>', unsafe_allow_html=True)
            st.markdown(f"**{title}**")
            st.caption(text)

# --- Ask ----------------------------------------------------------------------------

provider = None
with st.container(border=True):
    settings_col, model_col = st.columns([1.3, 5], vertical_alignment="center")
    with settings_col:
        with st.popover("Settings", icon=":material/tune:", width="stretch"):
            if available:
                ids = [p["id"] for p in available]
                provider = st.selectbox(
                    "Answer model",
                    ids,
                    index=ids.index(default_provider) if default_provider in ids else 0,
                    format_func=lambda pid: f"{by_id[pid]['label']} · {by_id[pid]['model']}",
                )
            top_k = st.slider("Passages to use", min_value=1, max_value=8, value=4,
                              help="More passages give the model more context but make answers slower.")
            rerank = st.toggle(
                "Rerank passages", value=bool(reranker_model), disabled=not reranker_model,
                help="A second model rereads the best matches and puts the most relevant first. "
                     "More accurate; adds about half a second."
                     if reranker_model else "No reranker is configured (AFRISEARCH_RERANKER is off).",
            )
            if unavailable:
                st.divider()
                st.caption("Other models")
                for p in unavailable:
                    st.caption(f"**{p['label']}**: {p['reason']}")
    with model_col:
        if provider:
            text, color, icon = where_it_runs(by_id[provider])
            st.markdown(f":gray[Answering with] **{by_id[provider]['label']}** :{color}-badge[{icon} {text}]")
        elif api_ok:
            st.warning("No answer model is available. Add an API key or install torch to use a local model.")

    with st.form("ask", border=False, enter_to_submit=False):
        question = st.text_area(
            "Your question",
            placeholder="For example: How often should solar panels be cleaned?  ·  "
                        "የፀሐይ ፓነሎች በየስንት ጊዜው መጽዳት አለባቸው?",
            height=100,
            help="Press Ctrl+Enter to ask.",
        )
        asked = st.form_submit_button("Ask AfriSearch", type="primary", icon=":material/search:",
                                      disabled=not (api_ok and provider))


def stream_answer(question: str) -> dict | None:
    """Ask /ask/stream, showing the answer as it is written. Returns the finished result."""
    result: dict = {"question": question, "answer": "", "error": None}
    started = time.monotonic()
    try:
        with st.spinner("Searching your documents..."):
            response = requests.post(
                f"{API_URL}/ask/stream",
                json={"question": question, "top_k": top_k, "generate_answer": True,
                      "provider": provider, "rerank": rerank},
                stream=True,
                timeout=900,
            )
            response.raise_for_status()
    except requests.HTTPError as exc:
        st.error(f"Request failed: {error_detail(exc)}", icon=":material/error:")
        return None
    except requests.RequestException as exc:
        st.error(f"Could not reach the AfriSearch API: {exc}", icon=":material/cloud_off:")
        return None

    def pieces():
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            event = json.loads(line)
            if event["type"] == "sources":
                result.update({k: v for k, v in event.items() if k != "type"})
            elif event["type"] == "token":
                yield event["text"]
            elif event["type"] == "done":
                result.update(answer=event["answer"], removed_citations=event["removed_citations"])
            elif event["type"] == "error":
                result["error"] = event["detail"]

    with st.container(border=True):
        st.markdown(f"#### {escape_markdown(question)}")
        with st.spinner(f"Writing the answer with {by_id[provider]['label']}..."):
            try:
                st.write_stream(pieces())
            except requests.RequestException as exc:
                result["error"] = f"The connection to the API was lost: {exc}"
    result["seconds"] = round(time.monotonic() - started, 1)
    result["provider_label"] = by_id[provider]["label"]
    return result


if asked:
    if len(question.strip()) < 2:
        st.warning("Type a question first.")
    elif not documents:
        st.warning("Add and index at least one document before asking.")
    else:
        result = stream_answer(question.strip())
        if result:
            st.session_state.last_result = result
            st.session_state.history = ([result] + st.session_state.history)[:HISTORY_LIMIT]
            st.rerun()  # show the finished answer with highlighted citations and sources

# --- Answer and sources (rendered from session state so they survive reruns) -------

payload = st.session_state.last_result
if payload:
    with st.container(border=True):
        st.markdown(f"#### {escape_markdown(payload.get('question', ''))}")
        source_count = len(payload.get("sources", []))
        badges = []
        if payload.get("provider_label"):
            label = payload["provider_label"].replace("[", "(").replace("]", ")")  # brackets end a badge
            badges.append(f":orange-badge[:material/smart_toy: {label}]")
        badges.append(f":gray-badge[:material/timer: {payload.get('seconds', '?')} s]")
        badges.append(f":gray-badge[:material/menu_book: {source_count} source{'' if source_count == 1 else 's'}]")
        if payload.get("reranked"):
            badges.append(":gray-badge[:material/sort: reranked]")
        st.markdown(" ".join(badges))
        if payload.get("error"):
            st.error(payload["error"], icon=":material/error:")
        if payload.get("answer"):
            st.markdown(render_answer_text(payload["answer"]))
        if payload.get("removed_citations"):
            st.caption(
                ":material/warning: Removed citations that did not match any retrieved source: "
                + ", ".join(payload["removed_citations"])
            )
        st.caption(":material/info: Answers can be wrong. Check important claims against the sources below.")

    sources = payload.get("sources", [])
    st.subheader("Sources")
    if not sources:
        st.info("No passages were similar enough to the question, so the model wasn't given any.",
                icon=":material/search_off:")
    for row_start in range(0, len(sources), 2):
        for column, source in zip(st.columns(2), sources[row_start:row_start + 2]):
            with column.container(border=True, height="stretch"):
                pages = format_pages(source)
                st.markdown(
                    f":orange-badge[**{source['label']}**] {file_icon(source['source_name'])} "
                    f"**{escape_markdown(source['source_name'])}**" + (f" :gray[· {pages}]" if pages else "")
                )
                tags = [f":gray-badge[relevance {source['score']:.0%}]"]
                if source.get("rerank_score") is not None:
                    tags.append(f":gray-badge[reranker {source['rerank_score']:.1f}]")
                if source.get("ocr"):
                    tags.append(":gray-badge[:material/document_scanner: read with OCR]")
                st.markdown(" ".join(tags))
                text = source["text"]
                if len(text) <= PREVIEW_CHARS:
                    st.caption(escape_markdown(text))
                else:
                    st.caption(escape_markdown(text[:PREVIEW_CHARS].rsplit(" ", 1)[0]) + " …")
                    with st.expander("Full passage"):
                        st.write(escape_markdown(text))

history = [item for item in st.session_state.history if item is not payload]
if history:
    st.subheader("Earlier questions")
    for i, item in enumerate(history):
        q_col, open_col = st.columns([7, 1], vertical_alignment="center")
        q_col.markdown(f"{escape_markdown(item['question'])}  \n:gray[{item.get('provider_label', '')}]")
        if open_col.button("Show", key=f"history-{i}", type="tertiary", icon=":material/history:"):
            st.session_state.last_result = item
            st.rerun()
