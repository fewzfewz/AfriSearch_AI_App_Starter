"""The AfriSearch HTTP API (under /api) and the built web app (everything else)."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import APIRouter, Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from backend import __version__, answers, config, db, extract, jobs, limits, llm, mailer, models, store
from backend.auth import User, current_user
from backend.text import clean_citations

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("afrisearch")

if config.SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        release=f"afrisearch@{__version__}",
        environment=config.ENVIRONMENT,
        send_default_pii=False,  # no IPs, cookies or request bodies (questions stay private)
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0")),
    )

DEFAULT_WORKSPACE_NAME = "My documents"


def preload_models() -> None:
    """Load the search model and reranker now, so the first question doesn't wait for them."""
    try:
        models.get_embedder()
        if models.RERANKER_ID:
            models.get_reranker()
        logger.info("Search models loaded")
    except Exception:
        logger.exception("Couldn't preload the search models; they'll load on first use")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.fail_interrupted_jobs()
    if os.getenv("AFRISEARCH_PRELOAD_MODELS", "1") != "0":
        threading.Thread(target=preload_models, name="preload", daemon=True).start()  # don't delay startup
    yield


app = FastAPI(
    title="AfriSearch AI API",
    description="Multilingual document search and cited answers.",
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
api = APIRouter(prefix="/api")


# --- request bodies ------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1500)
    top_k: int = Field(default=4, ge=1, le=8)
    generate_answer: bool = True
    # One of llm.PROVIDERS; defaults to AFRISEARCH_DEFAULT_PROVIDER or the first available.
    provider: str | None = None
    # Reorder passages with the reranker; defaults to on when one is configured.
    rerank: bool | None = None
    # Only search these documents (source ids from GET /api/documents); all when empty.
    source_ids: list[str] | None = Field(default=None, max_length=200)
    # Continue this chat (earlier turns help with follow-up questions) and save the turn.
    chat_id: str | None = None
    # Save the question and answer in a new chat when no chat_id is given.
    save: bool = False


class FeedbackRequest(BaseModel):
    rating: Literal["up", "down"]
    question: str = Field(min_length=1, max_length=1500)
    answer: str | None = Field(default=None, max_length=20000)
    provider: str | None = Field(default=None, max_length=100)
    comment: str = Field(default="", max_length=1000)
    sources: list[str] = Field(default_factory=list, max_length=8)  # cited document names
    message_id: str | None = None


class DeleteAccountRequest(BaseModel):
    confirm: str = Field(max_length=254)  # the user's email, or DELETE when there is none


class NameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class TitleRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ChatUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    shared: bool | None = None  # share read-only with everyone in the workspace


class MemberRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


# --- workspaces ----------------------------------------------------------------------

@dataclass(frozen=True)
class Workspace:
    id: str
    name: str
    role: str
    user: User

    @property
    def store(self) -> store.DocumentStore:
        return store.get_store(self.id)


def import_legacy_data(workspace_id: str) -> None:
    """Move documents from the pre-workspace layout (data/uploads, data/index.json...) in."""
    target = store.workspace_dir(workspace_id)
    legacy = {name: config.DATA_DIR / name for name in ("uploads", "index.json", "embeddings.npy", "manifest.json")}
    if not legacy["uploads"].is_dir() or not any(not p.name.startswith(".") for p in legacy["uploads"].iterdir()):
        return
    (target / "uploads").mkdir(parents=True, exist_ok=True)
    for item in legacy.pop("uploads").iterdir():
        if not item.name.startswith("."):  # leave .gitkeep and other hidden files
            shutil.move(str(item), target / "uploads" / item.name)
    for name, path in legacy.items():
        if path.exists() and not (target / name).exists():
            shutil.move(str(path), target / name)
    feedback = config.DATA_DIR / "feedback.jsonl"
    if feedback.exists():
        for line in feedback.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
                db.add_feedback(workspace_id, "local", record)
            except (ValueError, KeyError):
                continue
        feedback.rename(feedback.with_suffix(".jsonl.imported"))
    store.forget_store(workspace_id)
    logger.info("Moved documents from %s into workspace %s", config.DATA_DIR, workspace_id)


_first_workspace_lock = threading.Lock()


def user_workspaces(user: User) -> list[dict[str, Any]]:
    """The user's workspaces; a first one is created for new users."""
    workspaces = db.list_workspaces(user.id)
    if not workspaces:
        with _first_workspace_lock:  # two first requests at once must not create two
            workspaces = db.list_workspaces(user.id)
            if not workspaces:
                workspace = db.create_workspace(DEFAULT_WORKSPACE_NAME, user.id)
                if user.id == "local":
                    import_legacy_data(workspace["id"])
                workspaces = db.list_workspaces(user.id)
    return workspaces


def current_workspace(
    user: User = Depends(current_user), x_workspace_id: str | None = Header(default=None),
) -> Workspace:
    """FastAPI dependency: the workspace named in the X-Workspace-Id header, or the user's first one."""
    if x_workspace_id:
        found = db.get_workspace(x_workspace_id, user.id)
        if not found:
            raise HTTPException(status_code=404, detail="Workspace not found.")
    else:
        found = user_workspaces(user)[0]
    return Workspace(id=found["id"], name=found["name"], role=found["role"], user=user)


def owned_workspace(workspace_id: str, user: User) -> dict[str, Any]:
    found = db.get_workspace(workspace_id, user.id)
    if not found:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if found["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the workspace owner can do this.")
    return found


# --- general -------------------------------------------------------------------------

def search_settings() -> dict[str, Any]:
    languages, reason = extract.ocr_status()
    return {"embedder": models.EMBEDDER_ID, "reranker": models.RERANKER_ID or None,
            "ocr": {"available": reason is None, "languages": languages, "reason": reason}}


@api.get("")
@api.get("/")
def api_root():
    return {"name": "AfriSearch AI API", "version": __version__, "docs": "/api/docs"}


@api.get("/health")
def health():
    """For uptime monitors: 200 when the database answers and the data folder is writable, else 503."""
    problems = []
    try:
        with db.connect() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as exc:
        problems.append(f"database: {exc}")
    try:
        probe = config.DATA_DIR / ".health-check"
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:
        problems.append(f"data folder: {exc}")
    body = {"status": "error" if problems else "ok", "version": __version__, **search_settings()}
    if problems:
        logger.error("Health check failed: %s", "; ".join(problems))
        return JSONResponse({**body, "problems": problems}, status_code=503)
    return body


@api.get("/config")
def public_config():
    """What the web app needs before sign-in (safe to expose: the anon key is public)."""
    return {
        "version": __version__,
        "auth": config.AUTH_MODE,
        "supabase_url": config.SUPABASE_URL or None,
        "supabase_anon_key": config.SUPABASE_ANON_KEY or None,
        "auth_providers": config.AUTH_PROVIDERS,
        "max_upload_mb": config.MAX_UPLOAD_BYTES // (1024 * 1024),
        "max_files_per_upload": config.MAX_FILES_PER_UPLOAD,
        "sentry_dsn": config.SENTRY_DSN_WEB or None,
        "org_name": config.ORG_NAME or None,
        "contact_email": config.CONTACT_EMAIL or None,
        "workspace_quota_mb": round(config.WORKSPACE_QUOTA_BYTES / 1024 / 1024) or None,
        "environment": config.ENVIRONMENT,
        "file_types": sorted(ext.lstrip(".") for ext in config.ALLOWED_EXTENSIONS),
        "email": mailer.enabled(),
    }


@api.get("/me")
def me(user: User = Depends(current_user)):
    return {"user": {"id": user.id, "email": user.email, "name": user.name}, "workspaces": user_workspaces(user)}


@api.get("/me/export")
def export_my_data(user: User = Depends(current_user)):
    """A zip of everything stored about the user, plus the documents of workspaces they own."""
    data = db.user_data(user.id)
    archive = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("afrisearch-data.json", json.dumps(data, ensure_ascii=False, indent=2))
        for workspace in data["workspaces"]:
            if workspace["role"] != "owner":
                continue
            workspace_store = store.get_store(workspace["id"])
            manifest = workspace_store.load_manifest()
            folder = re.sub(r"[^\w .-]", "_", workspace["name"]) or workspace["id"]
            for path in workspace_store.uploaded_files():
                # Keep the stored name's unique prefix, so two files called report.pdf don't collide.
                zip_file.write(path, f"documents/{folder}/{path.name[:33]}{store.display_name(path.name, manifest)}")
    archive.close()
    return FileResponse(archive.name, filename=f"afrisearch-export-{time.strftime('%Y%m%d')}.zip",
                        background=BackgroundTask(os.unlink, archive.name))  # removed once sent


def delete_auth_account(user_id: str) -> bool:
    """Delete the Supabase sign-in account too, when the server has the admin key."""
    if config.AUTH_MODE != "supabase" or not config.SUPABASE_SERVICE_ROLE_KEY:
        return False
    request = urllib.request.Request(
        f"{config.SUPABASE_URL}/auth/v1/admin/users/{user_id}", method="DELETE",
        headers={"apikey": config.SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15):
            return True
    except Exception:
        logger.exception("Couldn't delete the Supabase account of %s", user_id)
        return False


@api.delete("/me")
def delete_my_account(body: DeleteAccountRequest, user: User = Depends(current_user)):
    """Delete the user's workspaces (for everyone in them), chats, ratings and memberships."""
    if body.confirm.strip().lower() != (user.email or "delete").lower():
        raise HTTPException(status_code=400, detail=f"Type {user.email or 'DELETE'} to confirm.")
    for workspace in db.list_workspaces(user.id):
        if workspace["role"] == "owner":
            store.get_store(workspace["id"]).delete_all()
            store.forget_store(workspace["id"])
            db.delete_workspace(workspace["id"])
    db.delete_user(user.id)
    auth_deleted = delete_auth_account(user.id)
    message = "Your data has been deleted."
    if config.AUTH_MODE == "supabase" and not auth_deleted:
        message += " Your sign-in account still exists; contact the administrator to remove it."
    return {"message": message, "auth_account_deleted": auth_deleted}


@api.get("/providers")
def list_providers(user: User = Depends(current_user)):
    return {
        "providers": [provider.describe() for provider in llm.PROVIDERS.values()],
        "default": llm.default_provider(),
    }


# --- workspace management ----------------------------------------------------------------

@api.get("/workspaces")
def list_workspaces(user: User = Depends(current_user)):
    return {"workspaces": user_workspaces(user)}


@api.post("/workspaces", status_code=201)
def create_workspace(body: NameRequest, user: User = Depends(current_user)):
    return db.create_workspace(body.name.strip(), user.id)


@api.patch("/workspaces/{workspace_id}")
def rename_workspace(workspace_id: str, body: NameRequest, user: User = Depends(current_user)):
    owned_workspace(workspace_id, user)
    db.rename_workspace(workspace_id, body.name.strip())
    return db.get_workspace(workspace_id, user.id)


@api.delete("/workspaces/{workspace_id}")
def delete_workspace(workspace_id: str, user: User = Depends(current_user)):
    owned_workspace(workspace_id, user)
    if len(db.list_workspaces(user.id)) == 1:
        raise HTTPException(status_code=400, detail="You can't delete your only workspace.")
    store.get_store(workspace_id).delete_all()
    store.forget_store(workspace_id)
    db.delete_workspace(workspace_id)
    return {"message": "Workspace deleted."}


@api.get("/workspaces/{workspace_id}/members")
def list_members(workspace_id: str, user: User = Depends(current_user)):
    if not db.get_workspace(workspace_id, user.id):
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return team(workspace_id)


def team(workspace_id: str) -> dict[str, Any]:
    return {"members": db.list_members(workspace_id), "invitations": db.list_invitations(workspace_id)}


@api.post("/workspaces/{workspace_id}/members", status_code=201)
def add_member(workspace_id: str, body: MemberRequest, user: User = Depends(current_user)):
    """Add someone by email. People without an account yet are invited: they join on first sign-in."""
    workspace = owned_workspace(workspace_id, user)
    email = body.email.strip()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Enter an email address.")
    invitee = db.find_user_by_email(email)
    if invitee:
        db.add_member(workspace_id, invitee["id"])
        message = f"{email} can now use this workspace."
    else:
        db.invite(workspace_id, email, user.id)
        message = f"Invitation saved. {email} joins this workspace when they sign up or sign in with that email."
    mailer.send(mailer.invitation(email, user.name or user.email, workspace["name"], has_account=bool(invitee)))
    if mailer.enabled():
        message += " We've emailed them."
    return {**team(workspace_id), "message": message}


@api.delete("/workspaces/{workspace_id}/invitations/{email}")
def cancel_invitation(workspace_id: str, email: str, user: User = Depends(current_user)):
    owned_workspace(workspace_id, user)
    db.cancel_invitation(workspace_id, email)
    return team(workspace_id)


@api.delete("/workspaces/{workspace_id}/members/{member_id}")
def remove_member(workspace_id: str, member_id: str, user: User = Depends(current_user)):
    if member_id != user.id:  # members may leave; only owners remove others
        owned_workspace(workspace_id, user)
    db.remove_member(workspace_id, member_id)
    return team(workspace_id)


# --- documents ----------------------------------------------------------------------------

async def read_limited(upload: UploadFile) -> bytes | None:
    """The upload's content, or None as soon as it passes the size limit (never all of a huge file)."""
    parts, size = [], 0
    while chunk := await upload.read(1024 * 1024):
        size += len(chunk)
        if size > config.MAX_UPLOAD_BYTES:
            return None
        parts.append(chunk)
    return b"".join(parts)


@api.post("/documents/upload")
async def upload_documents(files: list[UploadFile] = File(...), workspace: Workspace = Depends(current_workspace)):
    if len(files) > config.MAX_FILES_PER_UPLOAD:
        raise HTTPException(status_code=400, detail=f"Upload at most {config.MAX_FILES_PER_UPLOAD} files at a time.")
    limits.check(f"upload:{workspace.user.id}", limits.UPLOAD_LIMITS, cost=len(files))
    contents, errors = [], []
    for upload in files:
        content = await read_limited(upload)
        if content is None:
            errors.append({"filename": upload.filename or "upload", "error": "File exceeds 15 MB limit."})
        else:
            contents.append((upload.filename or "upload.txt", content))
    saved, rejected = workspace.store.save_uploads(contents)
    return {"saved": saved, "errors": errors + rejected,
            "message": "Upload finished. Index the documents to search new files."}


@api.post("/documents/index")
def index_documents(full: bool = False, wait: bool = True, workspace: Workspace = Depends(current_workspace)):
    """Index new uploads (?full=true re-reads every document).

    With wait=false the work runs in the background and the job is returned at
    once; follow it with GET /api/jobs/{id}.
    """
    if not wait:
        return {"job": jobs.start_index_job(workspace.id, workspace.user.id, full)}
    try:
        result = workspace.store.rebuild(full=full)
    except Exception as exc:
        logger.exception("Indexing failed")
        raise HTTPException(status_code=500, detail=f"Indexing failed: {exc}") from exc
    message = f"Added {len(result['new_documents'])} document(s); {result['indexed_chunks']} chunks indexed in total."
    if result["failed"]:
        message += f" {len(result['failed'])} file(s) could not be indexed."
    return {**result, "message": message}


@api.get("/jobs")
def list_jobs(active: bool = False, workspace: Workspace = Depends(current_workspace)):
    return {"jobs": db.list_jobs(workspace.id, active_only=active)}


@api.get("/jobs/{job_id}")
def get_job(job_id: str, workspace: Workspace = Depends(current_workspace)):
    job = db.get_job(job_id, workspace.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@api.get("/documents")
def list_documents(workspace: Workspace = Depends(current_workspace)):
    documents, stale = workspace.store.documents()
    return {"documents": documents,
            "indexed_chunks": len(workspace.store.chunks),
            # Documents indexed with another search model or chunking; re-index to search them.
            "stale_documents": stale,
            # Uploaded files that aren't in the index (new, or failed to index).
            "unindexed_files": len(workspace.store.uploaded_files()) - len(documents),
            "storage": {"used_bytes": workspace.store.bytes_used(), "quota_bytes": config.WORKSPACE_QUOTA_BYTES or None},
            **search_settings()}


@api.get("/documents/{source_id}/passages")
def document_passages(source_id: str, workspace: Workspace = Depends(current_workspace)):
    passages = workspace.store.passages(source_id)
    if not passages:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"source_id": source_id, "source_name": passages[0]["source_name"], "passages": passages}


@api.get("/documents/{source_id}/file")
def document_file(source_id: str, workspace: Workspace = Depends(current_workspace)):
    """The original uploaded file, e.g. to open a PDF at a cited page."""
    try:
        path = workspace.store.file_path(source_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    name = store.display_name(source_id, workspace.store.load_manifest())
    return FileResponse(path, filename=name, content_disposition_type="inline")


@api.post("/documents/{source_id}/replace")
async def replace_document(source_id: str, file: UploadFile = File(...), workspace: Workspace = Depends(current_workspace)):
    """Upload a new version of a document; the old file and its passages are removed.

    Answers that cited the old version keep their quoted passages. Index afterwards
    (as for any upload) to make the new version searchable.
    """
    try:
        workspace.store.file_path(source_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    limits.check(f"upload:{workspace.user.id}", limits.UPLOAD_LIMITS)
    content = await read_limited(file)
    if content is None:
        raise HTTPException(status_code=400, detail="File exceeds 15 MB limit.")
    saved, errors = workspace.store.save_uploads([(file.filename or "upload.txt", content)])
    if not saved:
        raise HTTPException(status_code=400, detail=errors[0]["error"])
    workspace.store.remove(source_id)
    return {"saved": saved[0], "replaced": source_id,
            "message": "New version uploaded. Index the documents to make it searchable."}


@api.delete("/documents/{source_id}")
def delete_document(source_id: str, workspace: Workspace = Depends(current_workspace)):
    try:
        removed = workspace.store.remove(source_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    return {"source_id": source_id, "removed_chunks": removed,
            "message": f"Deleted document and {removed} indexed chunks."}


# --- asking --------------------------------------------------------------------------------

def check_index_ready(workspace: Workspace) -> None:
    status = workspace.store.status()
    if status == "empty":
        raise HTTPException(status_code=400, detail="No documents indexed yet. Upload files and index them first.")
    if status == "stale":
        raise HTTPException(
            status_code=409,
            detail="The search model or chunk settings changed. Re-index the documents before asking.",
        )


def choose_provider(request: AskRequest) -> str | None:
    if not request.generate_answer:
        return None
    provider = request.provider or llm.default_provider()
    if provider not in llm.PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown or unavailable provider: {provider}. See GET /api/providers.")
    return provider


def chat_history(chat: dict[str, Any] | None) -> list[dict[str, str]]:
    """Earlier question/answer pairs of a chat."""
    if not chat:
        return []
    turns, question = [], None
    for message in db.list_messages(chat["id"]):
        if message["role"] == "user":
            question = message["content"]
        elif question is not None:
            turns.append({"question": question, "answer": message["content"]})
            question = None
    return turns


@dataclass
class PreparedAsk:
    provider: str | None
    chat: dict[str, Any] | None
    history: list[dict[str, str]]
    sources: list[dict[str, Any]]
    covered: bool


def prepare_ask(request: AskRequest, workspace: Workspace, check_available: bool) -> PreparedAsk:
    limits.check(f"ask:{workspace.user.id}", limits.ASK_LIMITS)
    check_index_ready(workspace)
    provider = choose_provider(request)
    if provider and check_available:
        reason = llm.PROVIDERS[provider].unavailable_reason()
        if reason:
            raise HTTPException(status_code=400, detail=f"{llm.PROVIDERS[provider].label} is not available: {reason}")
    chat = None
    if request.chat_id:
        chat = db.get_chat(request.chat_id, workspace.id, workspace.user.id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found.")
    history = chat_history(chat)

    def search(query: str) -> list[dict[str, Any]]:
        return workspace.store.retrieve(query, request.top_k, rerank=request.rerank, source_ids=request.source_ids)

    sources = search(request.question)
    # A follow-up like "and the price?" may find nothing on its own; then search
    # again together with the previous question. Questions that work on their own
    # (including a new topic in the same chat) are searched as they are.
    with_context = answers.search_query(request.question, history)
    if not answers.is_covered(sources) and with_context != request.question:
        alternative = search(with_context)
        if answers.is_covered(alternative):
            sources = alternative
    if request.save and not chat:
        chat = db.create_chat(workspace.id, workspace.user.id, request.question)
    covered = answers.is_covered(sources)
    # When nothing is good enough, all closest passages are shown; otherwise only
    # the ones close to the best, which are also all the model gets to see.
    return PreparedAsk(provider, chat, history, answers.focus(sources) if covered else sources, covered)


def search_summary(request: AskRequest, prepared: PreparedAsk) -> dict[str, Any]:
    return {
        "question": request.question,
        "provider": prepared.provider,
        "model": llm.PROVIDERS[prepared.provider].model if prepared.provider else None,
        "reranked": any("rerank_score" in item for item in prepared.sources),
        "covered": prepared.covered,
        "chat_id": prepared.chat["id"] if prepared.chat else None,
        "sources": answers.source_payload(prepared.sources),
    }


def account_usage(workspace: Workspace, provider: str | None, usage: llm.Usage) -> dict[str, Any] | None:
    """Record the tokens an answer used against the workspace; returns them for the message."""
    if not provider or not (usage.input_tokens or usage.output_tokens):
        return None  # local models and canned answers cost nothing
    model = llm.PROVIDERS[provider].model
    cost = llm.cost_usd(model, usage)
    db.record_usage(workspace.id, workspace.user.id, provider, model, usage.input_tokens, usage.output_tokens, cost)
    return {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "cost_usd": cost}


def save_turn(prepared: PreparedAsk, summary: dict[str, Any], answer: str | None, removed: list[str],
              error: str | None, seconds: float, usage: dict[str, Any] | None = None) -> str | None:
    """Store the answer in the chat; returns the assistant message id."""
    if not prepared.chat:
        return None
    data = {key: summary[key] for key in ("provider", "model", "reranked", "covered", "sources")}
    data.update(removed_citations=removed, error=error, seconds=round(seconds, 1), usage=usage)
    return db.add_message(prepared.chat["id"], "assistant", answer or "", data)["id"]


@api.post("/ask")
def ask(request: AskRequest, workspace: Workspace = Depends(current_workspace)):
    started = time.monotonic()
    prepared = prepare_ask(request, workspace, check_available=False)
    summary = search_summary(request, prepared)
    if prepared.chat:
        db.add_message(prepared.chat["id"], "user", request.question)
    answer, removed = None, []
    usage = llm.Usage()
    if prepared.provider:
        try:
            answer = answers.generate_answer(request.question, prepared.sources, prepared.provider,
                                             prepared.history, usage)
        except llm.ProviderError as exc:
            account_usage(workspace, prepared.provider, usage)  # a refusal may still be billed
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            # SDK errors: bad API key, rate limits, network, model download, GPU memory...
            logger.exception("Answer generation with %s failed", prepared.provider)
            raise HTTPException(status_code=502, detail=f"{prepared.provider} failed: {exc}") from exc
        answer, removed = clean_citations(answer, len(prepared.sources))
    used = account_usage(workspace, prepared.provider, usage)
    message_id = save_turn(prepared, summary, answer, removed, None, time.monotonic() - started, used)
    return {**summary, "answer": answer, "removed_citations": removed, "message_id": message_id}


@api.post("/ask/stream")
def ask_stream(request: AskRequest, workspace: Workspace = Depends(current_workspace)):
    """Like /api/ask, but streams newline-delimited JSON events as the answer is written.

    Events: {"type": "sources", ...} first (same fields as /api/ask minus the answer),
    then {"type": "token", "text": ...} pieces, then {"type": "done", "answer",
    "removed_citations", "message_id"} with citations cleaned, or {"type": "error", "detail"}.
    """
    started = time.monotonic()
    prepared = prepare_ask(request, workspace, check_available=True)
    summary = search_summary(request, prepared)
    if prepared.chat:
        db.add_message(prepared.chat["id"], "user", request.question)

    def event(kind: str, **fields: Any) -> str:
        return json.dumps({"type": kind, **fields}, ensure_ascii=False) + "\n"

    def events():
        yield event("sources", **summary)
        if not prepared.provider:
            message_id = save_turn(prepared, summary, None, [], None, time.monotonic() - started)
            yield event("done", answer=None, removed_citations=[], message_id=message_id)
            return
        pieces: list[str] = []
        usage = llm.Usage()
        try:
            if not prepared.sources or not prepared.covered:
                canned = answers.canned("not_covered" if prepared.sources else "no_sources", request.question)
                pieces.append(canned)
                yield event("token", text=canned)
            else:
                prompt = answers.build_prompt(request.question, prepared.sources, prepared.history)
                for piece in llm.stream(prepared.provider, answers.SYSTEM_PROMPT, prompt, usage):
                    pieces.append(piece)
                    yield event("token", text=piece)
        except Exception as exc:
            # A refusal or a model error means the text so far isn't a real answer: discard
            # it. After a network or SDK failure, the partial text is kept with the error.
            discard = isinstance(exc, llm.ProviderError)
            if discard:
                detail = str(exc)
            else:
                logger.exception("Answer generation with %s failed", prepared.provider)
                detail = f"{prepared.provider} failed: {exc}"
            used = account_usage(workspace, prepared.provider, usage)
            save_turn(prepared, summary, "" if discard else "".join(pieces), [], detail, time.monotonic() - started, used)
            yield event("error", detail=detail, discard_partial=discard)
            return
        answer, removed = clean_citations("".join(pieces), len(prepared.sources))
        used = account_usage(workspace, prepared.provider, usage)
        message_id = save_turn(prepared, summary, answer, removed, None, time.monotonic() - started, used)
        yield event("done", answer=answer, removed_citations=removed, message_id=message_id)

    return StreamingResponse(events(), media_type="application/x-ndjson")


# --- chats ------------------------------------------------------------------------------------

def owned_chat(chat_id: str, workspace: Workspace) -> dict[str, Any]:
    chat = db.get_chat(chat_id, workspace.id, workspace.user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return chat


@api.get("/chats")
def list_chats(workspace: Workspace = Depends(current_workspace)):
    """The user's chats, and chats others have shared with this workspace."""
    return {"chats": db.list_chats(workspace.id, workspace.user.id),
            "shared": db.list_shared_chats(workspace.id, workspace.user.id)}


@api.post("/chats", status_code=201)
def create_chat(body: TitleRequest, workspace: Workspace = Depends(current_workspace)):
    return db.create_chat(workspace.id, workspace.user.id, body.title.strip())


@api.get("/chats/{chat_id}")
def get_chat(chat_id: str, workspace: Workspace = Depends(current_workspace)):
    """A chat with its messages: the user's own, or one shared with the workspace (read-only)."""
    chat = db.get_visible_chat(chat_id, workspace.id, workspace.user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return {**chat, "shared": bool(chat["shared"]), "mine": chat["user_id"] == workspace.user.id,
            "messages": db.list_messages(chat_id)}


@api.patch("/chats/{chat_id}")
def update_chat(chat_id: str, body: ChatUpdate, workspace: Workspace = Depends(current_workspace)):
    """Rename a chat, or share it with the workspace (only its owner can)."""
    owned_chat(chat_id, workspace)
    if body.title is not None:
        db.rename_chat(chat_id, body.title.strip())
    if body.shared is not None:
        db.set_chat_shared(chat_id, body.shared)
    return owned_chat(chat_id, workspace)


@api.delete("/chats/{chat_id}")
def delete_chat(chat_id: str, workspace: Workspace = Depends(current_workspace)):
    owned_chat(chat_id, workspace)
    db.delete_chat(chat_id)
    return {"message": "Chat deleted."}


# --- feedback and insights ----------------------------------------------------------------------

@api.post("/feedback")
def add_feedback(feedback: FeedbackRequest, workspace: Workspace = Depends(current_workspace)):
    """Store a rating of an answer (and on the chat message, when message_id is given)."""
    if feedback.message_id and not db.get_message(feedback.message_id, workspace.id, workspace.user.id):
        raise HTTPException(status_code=404, detail="Message not found.")
    db.add_feedback(workspace.id, workspace.user.id, feedback.model_dump())
    return {"message": "Thanks for the feedback."}


@api.get("/feedback")
def list_feedback(limit: int = 20, workspace: Workspace = Depends(current_workspace)):
    """Rating totals and the most recent ratings in this workspace, newest first."""
    return db.feedback_summary(workspace.id, limit)


@api.get("/insights")
def insights(workspace: Workspace = Depends(current_workspace)):
    documents, _ = workspace.store.documents()
    return {
        "documents": len(documents),
        "passages": len(workspace.store.chunks),
        "ocr_documents": sum(doc["ocr"] for doc in documents),
        "bytes": sum(doc["bytes"] or 0 for doc in documents),
        **db.insights(workspace.id),
        "feedback": db.feedback_summary(workspace.id, limit=10),
        # Hosted-model tokens and estimated cost this calendar month (UTC).
        "usage": db.usage_summary(workspace.id, db.now()[:8] + "01"),
    }


app.include_router(api)


# --- security headers ------------------------------------------------------------------------

def inline_script_hashes() -> list[str]:
    """CSP hashes of the inline scripts in the built index.html (the dark-mode script)."""
    index = config.WEB_DIST / "index.html"
    if not index.is_file():
        return []
    scripts = re.findall(r"<script>(.*?)</script>", index.read_text(encoding="utf-8"), flags=re.S)
    return [f"'sha256-{base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()}'" for s in scripts]


def content_security_policy() -> str:
    connect = " ".join(filter(None, ["'self'", config.SUPABASE_URL]))
    return "; ".join([
        "default-src 'self'",
        f"script-src 'self' {' '.join(inline_script_hashes())}".strip(),
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",  # React style attributes
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data: blob: https:",  # https: for Google profile pictures
        f"connect-src {connect}",
        "object-src 'self' blob:",  # the browser's PDF viewer for "Open document"
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    ])


_csp: list[str] = []


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")  # uploaded text is never run as HTML
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if not request.url.path.startswith("/api/docs"):  # the interactive API docs load from a CDN
        if not _csp:
            _csp.append(content_security_policy())
        response.headers.setdefault("Content-Security-Policy", _csp[0])
    return response


# --- the web app -----------------------------------------------------------------------------------

@app.get("/{path:path}", include_in_schema=False)
def web_app(path: str):
    """Serve the built web app; unknown paths get index.html so client-side routes work."""
    if path.startswith("api/") or path == "api":
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    index = config.WEB_DIST / "index.html"
    if not index.is_file():
        return JSONResponse({"name": "AfriSearch AI API", "version": __version__, "docs": "/api/docs",
                             "web_app": "not built (cd web && npm install && npm run build)"})
    candidate = (config.WEB_DIST / path).resolve()
    if path and candidate.is_file() and config.WEB_DIST.resolve() in candidate.parents:
        # Hashed asset names change with every build, so they can be cached for long.
        cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
        return FileResponse(candidate, headers={"Cache-Control": cache})
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
