import html
import json
import os
import re
import time
import uuid
from datetime import datetime

import requests
import streamlit as st

API_URL = os.getenv("AFRISEARCH_API_URL", "http://127.0.0.1:8000")
# Where the browser can open the API docs (in Docker, API_URL is an internal address).
API_DOCS_URL = os.getenv("AFRISEARCH_API_DOCS_URL", f"{API_URL}/docs")
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
st.session_state.setdefault("feedback_sent", {})  # result id -> "up" / "down"

st.markdown(
    """
    <style>
    [data-testid="stMainBlockContainer"] { padding-top: 2.5rem; }
    .afs-hero {
        padding: 1.4rem 1.6rem 1.2rem;
        border-radius: 1rem;
        background: linear-gradient(120deg, #9a3412 0%, #c2410c 45%, #b45309 100%);
        color: #fff;
        margin-bottom: 1rem;
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
    .afs-anchor { scroll-margin-top: 4rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- Helpers -------------------------------------------------------------------------

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


def delete_document(source_id: str) -> None:
    try:
        requests.delete(f"{API_URL}/documents/{source_id}", timeout=30).raise_for_status()
    except requests.RequestException as exc:
        st.error(f"Delete failed: {error_detail(exc)}")
    else:
        st.rerun()


def format_pages(source: dict) -> str:
    first, last = source.get("page"), source.get("page_end")
    if not first:
        return ""
    if last and last != first:
        return f"pages {first}-{last}"
    return f"page {first}"


def format_size(size: int | None) -> str:
    if size is None:
        return ""
    if size < 1024 * 1024:
        return f"{max(size / 1024, 0.1):.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


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
    """Answer markdown with each citation such as [S1] or [S1, S2] linking to its source card."""
    text = text.replace("$", "\\$")  # "$" would otherwise start LaTeX math

    def link(match: re.Match[str]) -> str:
        labels = [label.strip() for label in match.group(1).split(",")]
        return " ".join(f"[:orange-background[**{label}**]](#source-{label.lower()})" for label in labels)

    return re.sub(r"\[(S\d+(?:\s*,\s*S\d+)*)\]", link, text)


def short_model_name(model_id: str | None) -> str:
    return (model_id or "").rsplit("/", 1)[-1]


def result_markdown(result: dict) -> str:
    """A finished answer and its sources as a Markdown document."""
    lines = [f"# {result.get('question', '')}", ""]
    meta = [result.get("provider_label") or "", result.get("asked_at", ""), f"{result.get('seconds', '?')} s"]
    lines += [f"_{' · '.join(m for m in meta if m)}_", ""]
    if result.get("error"):
        lines += [f"**Error:** {result['error']}", ""]
    lines += [result.get("answer") or "_Passages only, no generated answer._", "", "## Sources", ""]
    for source in result.get("sources", []):
        pages = format_pages(source)
        lines += [f"### {source['label']} · {source['source_name']}" + (f" · {pages}" if pages else ""),
                  f"Relevance {source['score']:.0%}" + (" · read with OCR" if source.get("ocr") else ""),
                  "", "> " + source["text"].replace("\n", "\n> "), ""]
    if not result.get("sources"):
        lines.append("No passages were similar enough to the question.")
    return "\n".join(lines)


def session_markdown(results: list[dict]) -> str:
    header = f"# AfriSearch session\n\n_Exported {datetime.now():%Y-%m-%d %H:%M}, {len(results)} question(s)_\n\n---\n\n"
    # Each result's title becomes a level-2 heading under the session title.
    return header + "\n\n---\n\n".join("#" + result_markdown(r) for r in results)


def send_feedback(result: dict, rating: str, comment: str) -> None:
    try:
        requests.post(f"{API_URL}/feedback", timeout=10, json={
            "rating": rating,
            "question": result["question"],
            "answer": result.get("answer"),
            "provider": result.get("provider"),
            "comment": comment,
            "sources": list(dict.fromkeys(s["source_name"] for s in result.get("sources", [])))[:8],
        }).raise_for_status()
    except requests.RequestException as exc:
        st.error(f"Could not send feedback: {error_detail(exc)}")
    else:
        st.session_state.feedback_sent[result["id"]] = rating
        st.toast("Thanks for the feedback!", icon=":material/favorite:")


# --- Load backend state --------------------------------------------------------

api_ok = True
providers, default_provider, documents, chunk_count = [], None, [], 0
stale_documents, search_model, reranker_model, version = 0, None, None, None
ocr = {"available": False, "languages": [], "reason": None}
try:
    provider_data = api_get("/providers")
    providers, default_provider = provider_data["providers"], provider_data["default"]
    doc_data = api_get("/documents")
    documents, chunk_count = doc_data["documents"], doc_data["indexed_chunks"]
    stale_documents, search_model = doc_data.get("stale_documents", 0), doc_data.get("embedder")
    reranker_model = doc_data.get("reranker")
    ocr = doc_data.get("ocr") or ocr
    version = api_get("/").get("version")
except requests.RequestException:
    api_ok = False

available = [p for p in providers if p["available"]]
unavailable = [p for p in providers if not p["available"]]
by_id = {p["id"]: p for p in providers}
doc_names = {d["source_id"]: d["source_name"] for d in documents}

# --- Sidebar: adding documents ----------------------------------------------------

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

    with st.expander("Advanced", icon=":material/tune:"):
        if search_model:
            st.caption(f"Search model: `{search_model}`")
        st.caption(f"Reranker: `{reranker_model}`" if reranker_model else "Reranker: off")
        st.caption("Rebuilding re-reads and re-embeds every document. It is only needed after "
                   "changing chunk settings by hand.")
        if st.button("Rebuild full index", icon=":material/refresh:", width="stretch", disabled=not api_ok):
            run_index_safely(full=True)
    if version:
        st.caption(f"AfriSearch v{version} · [API docs]({API_DOCS_URL}) · MIT license")

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

ask_tab, library_tab, insights_tab = st.tabs([
    ":material/search: Ask", f":material/folder_open: Library ({len(documents)})", ":material/insights: Insights",
])

# --- Ask tab ---------------------------------------------------------------------------


def stream_answer(question: str, settings: dict) -> dict | None:
    """Ask /ask/stream, showing the answer as it is written. Returns the finished result."""
    result: dict = {"id": uuid.uuid4().hex, "question": question, "answer": "", "error": None,
                    "asked_at": f"{datetime.now():%Y-%m-%d %H:%M}"}
    started = time.monotonic()
    try:
        with st.spinner("Searching your documents..."):
            response = requests.post(
                f"{API_URL}/ask/stream",
                json={"question": question, "top_k": settings["top_k"], "rerank": settings["rerank"],
                      "generate_answer": settings["generate"], "provider": settings["provider"],
                      "source_ids": settings["source_ids"] or None},
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

    if settings["generate"]:
        with st.container(border=True):
            st.markdown(f"#### {escape_markdown(question)}")
            with st.spinner(f"Writing the answer with {by_id[settings['provider']]['label']}..."):
                try:
                    st.write_stream(pieces())
                except requests.RequestException as exc:
                    result["error"] = f"The connection to the API was lost: {exc}"
        result["provider_label"] = by_id[settings["provider"]]["label"]
    else:
        for _ in pieces():
            pass
        result["provider_label"] = "Passages only"
    result["seconds"] = round(time.monotonic() - started, 1)
    return result


def render_result(payload: dict) -> None:
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

        feedback_col, download_col = st.columns([3, 1], vertical_alignment="bottom")
        with feedback_col:
            if payload.get("answer"):
                sent = st.session_state.feedback_sent.get(payload["id"])
                if sent:
                    st.caption(f":material/check_circle: You rated this answer "
                               f"{'helpful' if sent == 'up' else 'not helpful'}. Thank you!")
                else:
                    with st.popover("Rate this answer", icon=":material/thumbs_up_down:"):
                        comment = st.text_input("What was good or wrong? (optional)", key=f"comment-{payload['id']}",
                                                max_chars=1000)
                        up_col, down_col = st.columns(2)
                        if up_col.button("Helpful", icon=":material/thumb_up:", key=f"up-{payload['id']}",
                                         width="stretch"):
                            send_feedback(payload, "up", comment)
                            st.rerun()
                        if down_col.button("Not helpful", icon=":material/thumb_down:", key=f"down-{payload['id']}",
                                           width="stretch"):
                            send_feedback(payload, "down", comment)
                            st.rerun()
            st.caption(":material/info: Answers can be wrong. Check important claims against the sources below.")
        download_col.download_button(
            "Download", data=result_markdown(payload), file_name="afrisearch-answer.md", mime="text/markdown",
            icon=":material/download:", key=f"download-{payload['id']}", width="stretch",
            help="Save this question, answer and sources as a Markdown file.",
        )

    sources = payload.get("sources", [])
    st.subheader("Sources")
    if not sources:
        st.info("No passages were similar enough to the question, so the model wasn't given any. "
                "Try rephrasing, or search more documents.", icon=":material/search_off:")
    for row_start in range(0, len(sources), 2):
        for column, source in zip(st.columns(2), sources[row_start:row_start + 2]):
            with column.container(border=True, height="stretch"):
                pages = format_pages(source)
                st.markdown(
                    f'<span id="source-{source["label"].lower()}" class="afs-anchor"></span>',
                    unsafe_allow_html=True,
                )
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


with ask_tab:
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

    settings = {"provider": None, "top_k": 4, "rerank": bool(reranker_model), "generate": True, "source_ids": []}
    with st.container(border=True):
        settings_col, scope_col = st.columns([1.2, 3.8], vertical_alignment="bottom")
        with settings_col:
            with st.popover("Settings", icon=":material/tune:", width="stretch"):
                mode = st.segmented_control(
                    "Mode", ["Write an answer", "Find passages only"], default="Write an answer",
                    help="Passages only skips the answer model: instant, and nothing is sent to a cloud API.",
                )
                settings["generate"] = mode != "Find passages only"
                if available:
                    ids = [p["id"] for p in available]
                    settings["provider"] = st.selectbox(
                        "Answer model",
                        ids,
                        index=ids.index(default_provider) if default_provider in ids else 0,
                        format_func=lambda pid: f"{by_id[pid]['label']} · {by_id[pid]['model']}",
                        disabled=not settings["generate"],
                    )
                settings["top_k"] = st.slider("Passages to use", min_value=1, max_value=8, value=4,
                                              help="More passages give the model more context but make "
                                                   "answers slower.")
                settings["rerank"] = st.toggle(
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
        with scope_col:
            settings["source_ids"] = st.multiselect(
                "Search in", list(doc_names), format_func=lambda sid: doc_names[sid],
                placeholder="All documents", disabled=not documents,
            )

        if not settings["generate"]:
            st.markdown(":gray[Finding passages only · no answer model]")
        elif settings["provider"]:
            text, color, icon = where_it_runs(by_id[settings["provider"]])
            st.markdown(f":gray[Answering with] **{by_id[settings['provider']]['label']}** "
                        f":{color}-badge[{icon} {text}]")
        elif api_ok:
            st.warning("No answer model is available. Add an API key or install torch to use a local model, "
                       "or choose **Find passages only** in Settings.")

        with st.form("ask", border=False, enter_to_submit=False):
            question = st.text_area(
                "Your question",
                placeholder="For example: How often should solar panels be cleaned?  ·  "
                            "የፀሐይ ፓነሎች በየስንት ጊዜው መጽዳት አለባቸው?",
                height=100,
                help="Press Ctrl+Enter to ask.",
            )
            can_ask = api_ok and (settings["provider"] or not settings["generate"])
            asked = st.form_submit_button("Ask AfriSearch" if settings["generate"] else "Find passages",
                                          type="primary", icon=":material/search:", disabled=not can_ask)

    if asked:
        if len(question.strip()) < 2:
            st.warning("Type a question first.")
        elif not documents:
            st.warning("Add and index at least one document before asking.")
        else:
            result = stream_answer(question.strip(), settings)
            if result:
                st.session_state.last_result = result
                st.session_state.history = ([result] + st.session_state.history)[:HISTORY_LIMIT]
                st.rerun()  # show the finished answer with linked citations and sources

    payload = st.session_state.last_result
    if payload:
        render_result(payload)

    history = [item for item in st.session_state.history if item is not payload]
    if history:
        title_col, export_col = st.columns([3, 1], vertical_alignment="bottom")
        title_col.subheader("Earlier questions")
        export_col.download_button(
            "Download session", data=session_markdown(st.session_state.history),
            file_name="afrisearch-session.md", mime="text/markdown", icon=":material/download:",
            width="stretch", help="All questions, answers and sources from this session as Markdown.",
        )
        for i, item in enumerate(history):
            q_col, open_col = st.columns([7, 1], vertical_alignment="center")
            q_col.markdown(f"{escape_markdown(item['question'])}  \n"
                           f":gray[{item.get('provider_label', '')} · {item.get('asked_at', '')}]")
            if open_col.button("Show", key=f"history-{i}", type="tertiary", icon=":material/history:"):
                st.session_state.last_result = item
                st.rerun()

# --- Library tab --------------------------------------------------------------------


@st.dialog("Delete document?")
def confirm_delete(source_id: str, name: str) -> None:
    st.write(f"**{escape_markdown(name)}** and its passages will be removed from the server. This can't be undone.")
    cancel_col, delete_col = st.columns(2)
    if cancel_col.button("Cancel", width="stretch"):
        st.rerun()
    if delete_col.button("Delete", type="primary", icon=":material/delete:", width="stretch"):
        delete_document(source_id)


with library_tab:
    if not documents:
        st.info("Your library is empty. Add documents in the sidebar.", icon=":material/folder_open:")
    else:
        query = st.text_input("Filter by name", placeholder="Type part of a file name",
                              label_visibility="collapsed", icon=":material/filter_list:")
        shown = [d for d in documents if query.lower() in d["source_name"].lower()]
        rows = [{
            "Document": d["source_name"],
            "Type": d.get("type", "").upper(),
            "Pages": str(d["pages"]) if d.get("pages") else "–",
            "Passages": d.get("passages"),
            "OCR": d.get("ocr", False),
            "Size": format_size(d.get("bytes")),
            "Added": datetime.fromisoformat(d["uploaded_at"]) if d.get("uploaded_at") else None,
        } for d in shown]
        event = st.dataframe(
            rows, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
            key="library-table",
            column_config={
                "Pages": st.column_config.TextColumn(help="– for text files and images"),
                "Passages": st.column_config.NumberColumn(help="Searchable pieces of about 180 words"),
                "OCR": st.column_config.CheckboxColumn(help="Text was read from a scan or photo"),
                "Added": st.column_config.DatetimeColumn(format="D MMM YYYY, HH:mm"),
            },
        )
        st.caption(f"{len(shown)} of {len(documents)} documents · select a row to read its passages")

        selected = event.selection.rows if event and event.selection else []
        if selected and selected[0] < len(shown):
            doc = shown[selected[0]]
            with st.container(border=True):
                name_col, delete_col = st.columns([4, 1], vertical_alignment="center")
                name_col.markdown(f"#### {file_icon(doc['source_name'])} {escape_markdown(doc['source_name'])}")
                if delete_col.button("Delete", icon=":material/delete:", key=f"lib-delete-{doc['source_id']}",
                                     width="stretch"):
                    confirm_delete(doc["source_id"], doc["source_name"])
                try:
                    passages = api_get(f"/documents/{doc['source_id']}/passages")["passages"]
                except requests.RequestException as exc:
                    st.error(f"Could not load passages: {error_detail(exc)}")
                    passages = []
                for number, passage in enumerate(passages, start=1):
                    pages = format_pages(passage)
                    label = f"Passage {number}" + (f" · {pages}" if pages else "") + (" · OCR" if passage["ocr"] else "")
                    with st.expander(label, expanded=number == 1):
                        st.write(escape_markdown(passage["text"]))

# --- Insights tab ----------------------------------------------------------------------

with insights_tab:
    feedback = {"total": 0, "up": 0, "down": 0, "recent": []}
    if api_ok:
        try:
            feedback = api_get("/feedback?limit=10")
        except requests.RequestException:
            pass

    st.subheader("Library")
    cols = st.columns(4)
    cols[0].metric("Documents", len(documents), border=True)
    cols[1].metric("Passages", chunk_count, border=True)
    cols[2].metric("Read with OCR", sum(bool(d.get("ocr")) for d in documents), border=True)
    cols[3].metric("Total size", format_size(sum(d.get("bytes") or 0 for d in documents)) or "0 KB", border=True)

    st.subheader("This session")
    session = st.session_state.history
    answered = [r for r in session if r.get("answer")]
    cols = st.columns(4)
    cols[0].metric("Questions", len(session), border=True)
    cols[1].metric("Answers written", len(answered), border=True)
    cols[2].metric("Average time", f"{sum(r.get('seconds', 0) for r in session) / len(session):.1f} s"
                   if session else "–", border=True)
    cols[3].metric("No passages found", sum(not r.get("sources") for r in session), border=True,
                   help="Questions where nothing passed the relevance cutoff")

    st.subheader("Answer feedback")
    st.caption("Ratings from everyone using this server, saved in data/feedback.jsonl.")
    cols = st.columns(3)
    cols[0].metric("Ratings", feedback["total"], border=True)
    cols[1].metric("Helpful", f"{feedback['up'] / feedback['total']:.0%}" if feedback["total"] else "–", border=True)
    cols[2].metric("Not helpful", feedback["down"], border=True)
    if feedback["recent"]:
        st.dataframe(
            [{"When": datetime.fromisoformat(r["time"]) if r.get("time") else None,
              "Rating": "👍" if r.get("rating") == "up" else "👎",
              "Question": r.get("question", ""),
              "Comment": r.get("comment", ""),
              "Model": r.get("provider") or ""} for r in feedback["recent"]],
            hide_index=True, width="stretch",
            column_config={"When": st.column_config.DatetimeColumn(format="D MMM, HH:mm")},
        )
    else:
        st.caption("No ratings yet. Use **Rate this answer** under an answer.")
