import os
import re
import time

import requests
import streamlit as st

API_URL = os.getenv("AFRISEARCH_API_URL", "http://127.0.0.1:8000")
HISTORY_LIMIT = 10

st.set_page_config(page_title="AfriSearch AI", page_icon="🔎", layout="wide")

# Values that must survive Streamlit reruns (any widget interaction reruns the script).
st.session_state.setdefault("uploader_key", 0)
st.session_state.setdefault("index_report", None)
st.session_state.setdefault("last_result", None)
st.session_state.setdefault("history", [])


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
    with st.spinner("Extracting text and creating embeddings..."):
        response = requests.post(
            f"{API_URL}/documents/index", params={"full": full}, timeout=900
        )
        response.raise_for_status()
        payload = response.json()
    report["messages"].append(("success", payload.get("message", "Index updated.")))
    report["failed"] = payload.get("failed", [])
    st.session_state.index_report = report


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


def render_answer_text(text: str) -> str:
    # "$" would otherwise start LaTeX math in Streamlit markdown.
    text = text.replace("$", "\\$")
    # Highlight citation labels such as [S1] or [S1, S2].
    return re.sub(r"\[(S\d+(?:\s*,\s*S\d+)*)\]", r":blue-background[**\1**]", text)


# --- Load backend state --------------------------------------------------------

api_ok = True
providers, default_provider, documents, chunk_count = [], None, [], 0
try:
    provider_data = api_get("/providers")
    providers, default_provider = provider_data["providers"], provider_data["default"]
    doc_data = api_get("/documents")
    documents, chunk_count = doc_data["documents"], doc_data["indexed_chunks"]
except requests.RequestException:
    api_ok = False

# --- Sidebar: knowledge base ---------------------------------------------------

with st.sidebar:
    st.header("📚 Knowledge base")
    if not api_ok:
        st.error(f"Cannot reach the API at {API_URL}. Start the FastAPI backend first.")

    docs_col, chunks_col = st.columns(2)
    docs_col.metric("Documents", len(documents))
    chunks_col.metric("Chunks", chunk_count)

    uploads = st.file_uploader(
        "Add PDF or TXT files",
        type=["pdf", "txt"],
        accept_multiple_files=True,
        key=f"uploader-{st.session_state.uploader_key}",
        help="Use documents you have permission to process. Files are stored on the machine running the API.",
    )
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
        st.subheader("Indexed documents")
        for doc in documents:
            name_col, delete_col = st.columns([5, 1], vertical_alignment="center")
            name_col.markdown(f":material/description: {doc['source_name']}")
            if delete_col.button("", key=f"delete-{doc['source_id']}", icon=":material/delete:",
                                 help=f"Delete {doc['source_name']}"):
                try:
                    requests.delete(f"{API_URL}/documents/{doc['source_id']}", timeout=30).raise_for_status()
                except requests.RequestException as exc:
                    st.error(f"Delete failed: {error_detail(exc)}")
                else:
                    st.rerun()
    elif api_ok:
        st.info("No documents indexed yet. Add files above to get started.")

    with st.expander("Advanced"):
        st.caption("Re-extract and re-embed every document, e.g. after changing the search model.")
        if st.button("Rebuild full index", icon=":material/refresh:", width="stretch", disabled=not api_ok):
            st.session_state.index_report = None
            try:
                run_index(full=True)
            except requests.RequestException as exc:
                st.session_state.index_report = {
                    "messages": [("error", f"Indexing failed: {error_detail(exc)}")],
                    "failed": [],
                }
            st.rerun()

# --- Main: ask ------------------------------------------------------------------

st.title("🔎 AfriSearch AI")
st.caption("Ask questions about your documents. Every answer cites the passages it is based on.")

available = [p for p in providers if p["available"]]
unavailable = [p for p in providers if not p["available"]]
by_id = {p["id"]: p for p in providers}

with st.container(border=True):
    model_col, passages_col = st.columns([3, 2])
    provider = None
    with model_col:
        if available:
            ids = [p["id"] for p in available]
            provider = st.selectbox(
                "Answer model",
                ids,
                index=ids.index(default_provider) if default_provider in ids else 0,
                format_func=lambda pid: f"{by_id[pid]['label']} · {by_id[pid]['model']}",
            )
            text, color, icon = where_it_runs(by_id[provider])
            st.badge(text, color=color, icon=icon)
        elif api_ok:
            st.warning("No answer model is available. Add an API key or install torch to use a local model.")
    with passages_col:
        top_k = st.slider("Passages to retrieve", min_value=1, max_value=8, value=4,
                          help="More passages give the model more context but make answers slower.")
    if unavailable:
        with st.expander(f"Other models ({len(unavailable)} unavailable)"):
            for p in unavailable:
                text, color, icon = where_it_runs(p)
                st.markdown(f"**{p['label']}** · `{p['model']}`  \n:{color}[{icon} {text}] — {p['reason']}")

with st.form("ask", border=False):
    question = st.text_area(
        "Question",
        placeholder="For example: What do the documents recommend about maintaining solar systems?",
        height=110,
        help="Press Ctrl+Enter to ask.",
    )
    asked = st.form_submit_button("Ask AfriSearch", type="primary", icon=":material/search:",
                                  disabled=not (api_ok and provider))

if asked:
    if len(question.strip()) < 2:
        st.warning("Enter a question first.")
    elif not documents:
        st.warning("Index at least one document before asking.")
    else:
        try:
            started = time.monotonic()
            with st.spinner(f"Retrieving evidence and asking {by_id[provider]['label']}..."):
                response = requests.post(
                    f"{API_URL}/ask",
                    json={
                        "question": question.strip(),
                        "top_k": top_k,
                        "generate_answer": True,
                        "provider": provider,
                    },
                    timeout=900,
                )
                response.raise_for_status()
            result = response.json()
            result["seconds"] = round(time.monotonic() - started, 1)
            result["provider_label"] = by_id[provider]["label"]
            st.session_state.last_result = result
            st.session_state.history = ([result] + st.session_state.history)[:HISTORY_LIMIT]
        except requests.HTTPError as exc:
            st.error(f"Request failed: {error_detail(exc)}")
        except requests.RequestException as exc:
            st.error(f"Could not reach AfriSearch API: {exc}")

# --- Main: answer (rendered from session state so it survives reruns) ---------

payload = st.session_state.last_result
if payload:
    with st.container(border=True):
        st.subheader("Answer")
        st.caption(payload.get("question", ""))
        source_count = len(payload.get("sources", []))
        badges = [
            f":gray-badge[:material/timer: {payload.get('seconds', '?')} s]",
            f":gray-badge[:material/menu_book: {source_count} source{'' if source_count == 1 else 's'}]",
        ]
        if payload.get("model"):
            label = payload.get("provider_label", payload["provider"]).replace("[", "(").replace("]", ")")
            badges.insert(0, f":blue-badge[:material/smart_toy: {label}]")
        st.markdown(" ".join(badges))
        st.markdown(render_answer_text(payload.get("answer") or "No generated answer."))
        if payload.get("removed_citations"):
            st.caption(
                ":material/warning: Removed citations that did not match any retrieved source: "
                + ", ".join(payload["removed_citations"])
            )

    st.subheader("Sources")
    if not payload.get("sources"):
        st.info("No passages were similar enough to the question.")
    for source in payload.get("sources", []):
        pages = format_pages(source)
        title = f"**{source['label']}** · {source['source_name']}" + (f" · {pages}" if pages else "")
        with st.expander(f"{title} · relevance {source['score']:.0%}"):
            st.progress(min(max(source["score"], 0.0), 1.0))
            st.write(source["text"])

history = [item for item in st.session_state.history if item is not payload]
if history:
    with st.expander(f"Earlier answers ({len(history)})"):
        for i, item in enumerate(history):
            q_col, open_col = st.columns([6, 1], vertical_alignment="center")
            q_col.markdown(f"{item['question']}  \n:gray[{item.get('provider_label', item.get('provider'))}]")
            if open_col.button("Show", key=f"history-{i}"):
                st.session_state.last_result = item
                st.rerun()

st.divider()
st.caption("Prototype warning: generated answers and citations can be wrong. Verify important claims against the source passages.")
