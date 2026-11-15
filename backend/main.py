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

from backend import __version__, answers, auth, billing, config, db, entitlements, extract, jobs, limits, llm, mailer, models, store
from backend.auth import Organization, User, current_organization, current_user
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
    auth.validate_auth_config()
    billing.validate_billing_config()
    db.fail_interrupted_jobs()
    try:
        with db.connect() as conn:
            row = conn.execute("SELECT organization_id FROM organization_ai_keys LIMIT 1").fetchone()
            if row:
                byok = db.get_all_raw_organization_ai_keys(row["organization_id"])
                if byok:
                    llm.set_request_api_keys(byok)
    except Exception:
        pass
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
    # Model ID to use for the selected provider (e.g. gemini-2.5-pro, gpt-4o, claude-3-5-sonnet).
    model: str | None = None
    # Reorder passages with the reranker; defaults to on when one is configured.
    rerank: bool | None = None
    # Only search these documents (source ids from GET /api/documents); all when empty.
    source_ids: list[str] | None = Field(default=None, max_length=200)
    # Only search documents carrying any of these tags/folders; all when empty.
    tags: list[str] | None = Field(default=None, max_length=50)
    # Continue this chat (earlier turns help with follow-up questions) and save the turn.
    chat_id: str | None = None
    # Save the question and answer in a new chat when no chat_id is given.
    save: bool = False
    # Deep Book Mode / Long-Context analysis: read broad multi-chapter context across documents
    deep_mode: bool = False


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
    role: Literal["admin", "member", "viewer"] = "member"


class UpdateMemberRoleRequest(BaseModel):
    role: Literal["admin", "member", "viewer"]


class DocumentTagsRequest(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=20)


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RenameOrganizationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TransferOwnershipRequest(BaseModel):
    new_owner_id: str = Field(min_length=1)


class InviteOrganizationMemberRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: Literal["admin", "member"] = "member"


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=10, max_length=256)


class SetOrganizationAIKeyRequest(BaseModel):
    provider: Literal["openai", "claude", "gemini"]
    api_key: str = Field(min_length=10, max_length=500)


class CreateDeveloperApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    workspace_id: str | None = None


class V1AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    workspace_id: str | None = None
    top_k: int = 5
    rerank: bool = True
    provider: str | None = None
    model: str | None = None
    tags: list[str] = Field(default_factory=list)
    deep_mode: bool = False


class V1SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    workspace_id: str | None = None
    top_k: int = 5
    rerank: bool = True
    tags: list[str] = Field(default_factory=list)


# --- workspaces ----------------------------------------------------------------------

@dataclass(frozen=True)
class Workspace:
    id: str
    name: str
    role: str
    user: User
    organization_id: str

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


def user_workspaces(user: User, organization_id: str | None = None) -> list[dict[str, Any]]:
    """The user's workspaces; a first one is created for new users."""
    workspaces = db.list_workspaces(user.id, organization_id=organization_id)
    if not workspaces:
        with _first_workspace_lock:  # two first requests at once must not create two
            workspaces = db.list_workspaces(user.id, organization_id=organization_id)
            if not workspaces:
                workspace = db.create_workspace(
                    DEFAULT_WORKSPACE_NAME, user.id, organization_id=organization_id
                )
                if user.id == "local":
                    import_legacy_data(workspace["id"])
                workspaces = db.list_workspaces(user.id, organization_id=organization_id)
    return workspaces


def get_workspace_membership(
    workspace_id: str, user_id: str, organization_id: str | None = None
) -> dict[str, Any] | None:
    """Retrieve workspace membership within an organization.

    In Stage A, access is derived from organization containment and membership.
    Fine-grained workspace-level roles (viewer, editor, admin) will plug into this hook.
    """
    return db.get_workspace(workspace_id, user_id, organization_id=organization_id)


def current_workspace(
    user: User = Depends(current_user),
    x_organization_id: str | None = Header(default=None),
    x_workspace_id: str | None = Header(default=None),
) -> Workspace:
    """FastAPI dependency: the workspace named in X-Workspace-Id, or the first workspace in the active organization."""
    if not isinstance(x_organization_id, str):
        x_organization_id = None
    if not isinstance(x_workspace_id, str):
        x_workspace_id = None

    if user.api_key_record:
        key_org_id = user.api_key_record["organization_id"]
        key_ws_id = user.api_key_record.get("workspace_id")
        target_ws_id = x_workspace_id or key_ws_id
        if key_ws_id and x_workspace_id and x_workspace_id != key_ws_id:
            raise HTTPException(status_code=403, detail="API key is restricted to a different workspace.")

        if target_ws_id:
            found = db.get_workspace(target_ws_id, user.id, organization_id=key_org_id)
            if not found:
                raise HTTPException(status_code=404, detail="Workspace not found.")
        else:
            workspaces = user_workspaces(user, organization_id=key_org_id)
            if not workspaces:
                raise HTTPException(status_code=404, detail="No workspaces found.")
            found = workspaces[0]

        return Workspace(
            id=found["id"],
            name=found["name"],
            role=found["role"],
            user=user,
            organization_id=found.get("organization_id") or key_org_id,
        )

    if x_workspace_id:
        found = db.get_workspace(x_workspace_id, user.id, organization_id=x_organization_id)
        if not found:
            raise HTTPException(status_code=404, detail="Workspace not found.")
    else:
        if x_organization_id:
            org = db.get_organization(x_organization_id, user.id)
            if not org:
                raise HTTPException(status_code=404, detail="Organization not found.")
            org_id = org["id"]
        else:
            user_orgs = db.list_user_organizations(user.id)
            if not user_orgs:
                name_cand = user.name.strip()
                org_name = f"{name_cand}'s Organization" if name_cand else "Personal Organization"
                new_org = db.create_organization(org_name, user.id)
                org_id = new_org["id"]
            else:
                org_id = user_orgs[0]["id"]
        workspaces = user_workspaces(user, organization_id=org_id)
        if not workspaces:
            raise HTTPException(status_code=404, detail="No workspaces found.")
        found = workspaces[0]

    return Workspace(
        id=found["id"],
        name=found["name"],
        role=found["role"],
        user=user,
        organization_id=found.get("organization_id") or "",
    )


def owned_workspace(workspace_id: str, user: User, org: Organization | None = None) -> dict[str, Any]:
    org_id = org.id if org else None
    found = db.get_workspace(workspace_id, user.id, organization_id=org_id)
    if not found:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if found["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the workspace owner can do this.")
    return found


ROLE_LEVELS: dict[str, int] = {
    "owner": 4,
    "admin": 3,
    "member": 2,
    "viewer": 1,
}


def require_workspace_role(workspace: Workspace, min_role: str) -> None:
    user_level = ROLE_LEVELS.get(workspace.role, 0)
    required_level = ROLE_LEVELS.get(min_role, 0)
    if user_level < required_level:
        raise HTTPException(
            status_code=403,
            detail=f"Action requires at least '{min_role}' role in this workspace (you have '{workspace.role}').",
        )


def check_workspace_admin_or_owner(workspace_id: str, user_id: str) -> dict[str, Any]:
    ws = db.get_workspace(workspace_id, user_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if ws["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only workspace owners and admins can perform this action.")
    return ws


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
    return {
        "user": {"id": user.id, "email": user.email, "name": user.name},
        "organizations": db.list_user_organizations(user.id),
        "workspaces": user_workspaces(user),
    }


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
def list_providers(
    user: User = Depends(current_user),
    x_organization_id: str | None = Header(default=None),
):
    if not isinstance(x_organization_id, str):
        x_organization_id = None

    org_id = None
    if user.api_key_record:
        org_id = user.api_key_record.get("organization_id")
    elif x_organization_id:
        org_id = x_organization_id
    else:
        user_orgs = db.list_user_organizations(user.id)
        if user_orgs:
            org_id = user_orgs[0]["id"]

    if org_id:
        byok_keys = db.get_all_raw_organization_ai_keys(org_id)
        if byok_keys:
            llm.set_request_api_keys(byok_keys)

    return {
        "providers": [provider.describe() for provider in llm.PROVIDERS.values()],
        "default": llm.default_provider(),
    }


# --- organization management --------------------------------------------------------

@api.get("/organizations")
def list_organizations(user: User = Depends(current_user)):
    return {"organizations": db.list_user_organizations(user.id)}


@api.post("/organizations", status_code=201)
def create_organization(body: CreateOrganizationRequest, user: User = Depends(current_user)):
    try:
        org = db.create_organization(body.name.strip(), user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return org


@api.get("/organizations/{org_id}")
def get_organization(org_id: str, user: User = Depends(current_user)):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return org


@api.patch("/organizations/{org_id}")
def rename_organization(org_id: str, body: RenameOrganizationRequest, user: User = Depends(current_user)):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if org["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only organization owners and admins can rename the organization.")
    try:
        db.rename_organization(org_id, body.name.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return db.get_organization(org_id, user.id)


@api.delete("/organizations/{org_id}")
def delete_organization(org_id: str, user: User = Depends(current_user)):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if org["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the organization owner can delete the organization.")
    try:
        db.delete_organization(org_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return {"message": "Organization deleted."}


@api.post("/organizations/{org_id}/transfer-ownership")
def transfer_organization_ownership(
    org_id: str, body: TransferOwnershipRequest, user: User = Depends(current_user)
):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if org["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the organization owner can transfer ownership.")
    try:
        db.transfer_organization_ownership(org_id, user.id, body.new_owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": "Ownership transferred successfully."}


@api.get("/organizations/{org_id}/members")
def list_organization_members(org_id: str, user: User = Depends(current_user)):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return {"members": db.list_organization_members(org_id)}


@api.delete("/organizations/{org_id}/members/{target_user_id}")
def remove_organization_member(
    org_id: str, target_user_id: str, user: User = Depends(current_user)
):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if target_user_id == user.id:
        if org["role"] == "owner":
            raise HTTPException(
                status_code=400, detail="Organization owner cannot leave. Transfer ownership first."
            )
    else:
        if org["role"] not in ("owner", "admin"):
            raise HTTPException(
                status_code=403, detail="Only organization owners and admins can remove members."
            )
    try:
        db.remove_organization_member(org_id, target_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"members": db.list_organization_members(org_id), "message": "Member removed."}


@api.post("/organizations/{org_id}/invitations", status_code=201)
def create_organization_invitation(
    org_id: str, body: InviteOrganizationMemberRequest, user: User = Depends(current_user)
):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if org["role"] not in ("owner", "admin"):
        raise HTTPException(
            status_code=403, detail="Only organization owners and admins can invite members."
        )
    entitlements.check_can_add_member(org_id)
    try:
        invitation, raw_token = db.create_organization_invitation(
            org_id, body.email, body.role, user.id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if mailer.enabled():
        mailer.send(
            mailer.organization_invitation(
                to=body.email,
                inviter=user.name or user.email,
                organization=org["name"],
                role=body.role,
                raw_token=raw_token,
            )
        )
    return {**invitation, "token": raw_token}


@api.get("/organizations/{org_id}/invitations")
def list_organization_invitations(org_id: str, user: User = Depends(current_user)):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if org["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only organization owners and admins can view invitations.")
    return {"invitations": db.list_organization_invitations(org_id)}


@api.delete("/organizations/{org_id}/invitations/{email}")
def cancel_organization_invitation(
    org_id: str, email: str, user: User = Depends(current_user)
):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if org["role"] not in ("owner", "admin"):
        raise HTTPException(
            status_code=403, detail="Only organization owners and admins can cancel invitations."
        )
    db.cancel_organization_invitation(org_id, email)
    return {
        "invitations": db.list_organization_invitations(org_id),
        "message": "Invitation cancelled.",
    }


@api.post("/organizations/invitations/accept")
def accept_organization_invitation(
    body: AcceptInvitationRequest, user: User = Depends(current_user)
):
    if config.AUTH_MODE == "supabase" and not user.email:
        raise HTTPException(
            status_code=400,
            detail="A verified email address is required to accept an organization invitation.",
        )
    try:
        result = db.accept_organization_invitation(body.token, user.id, user.email)
    except ValueError as exc:
        err_msg = str(exc)
        if "expired" in err_msg.lower():
            raise HTTPException(status_code=410, detail=err_msg)
        elif "sent to" in err_msg.lower():
            raise HTTPException(status_code=403, detail=err_msg)
        else:
            raise HTTPException(status_code=404, detail=err_msg)
    return {
        "message": "Invitation accepted.",
        "organization_id": result["organization_id"],
        "role": result["role"],
    }


# --- subscriptions, plans & usage ---------------------------------------------------

@api.get("/plans")
def list_plans():
    return {"plans": list(entitlements.PLANS.values())}


@api.get("/organizations/{org_id}/subscription")
def get_organization_subscription(org_id: str, user: User = Depends(current_user)):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    sub = db.get_organization_subscription(org_id)
    plan = entitlements.get_plan(sub.get("plan_id", "free"))
    return {
        "subscription": sub,
        "plan": plan,
    }


@api.get("/organizations/{org_id}/usage")
def get_organization_usage(org_id: str, user: User = Depends(current_user)):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    sub = db.get_organization_subscription(org_id)
    plan = entitlements.get_plan(sub.get("plan_id", "free"))
    usage = db.get_organization_usage_summary(org_id)
    return {
        "usage": usage,
        "limits": {
            "max_workspaces": plan["max_workspaces"],
            "max_seats": plan["max_seats"],
            "max_storage_bytes": plan["max_storage_bytes"],
            "max_documents": plan["max_documents"],
            "max_queries_per_month": plan["max_queries_per_month"],
        },
        "plan": plan,
    }


class CheckoutRequest(BaseModel):
    plan_id: str
    seats: int = 1
    provider: str = "stripe"
    currency: str | None = None
    return_url: str | None = None


@api.post("/organizations/{org_id}/checkout")
def create_checkout_session(
    org_id: str,
    req: CheckoutRequest,
    user: User = Depends(current_user),
):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if org.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only the organization owner can manage subscriptions and purchases.")
    try:
        session = billing.create_checkout_session(
            organization_id=org_id,
            organization_name=org["name"],
            plan_id=req.plan_id,
            seats=req.seats,
            provider=req.provider,
            user_email=user.email,
            user_name=user.name,
            return_url=req.return_url,
            currency=req.currency,
        )
        return session
    except Exception as e:
        logger.exception("Checkout session creation failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@api.post("/organizations/{org_id}/billing-portal")
def create_billing_portal_session(
    org_id: str,
    user: User = Depends(current_user),
):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if org.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only the organization owner can access the billing portal.")
    try:
        return billing.create_portal_session(org_id)
    except Exception as e:
        logger.exception("Billing portal session failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@api.get("/organizations/{org_id}/invoices")
def list_organization_invoices(
    org_id: str,
    user: User = Depends(current_user),
):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    invoices = billing.list_invoices(org_id)
    return {"invoices": invoices}


@api.get("/organizations/{org_id}/ai-keys")
def get_organization_ai_keys(org_id: str, user: User = Depends(current_user)):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if org.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only organization owners and admins can view AI provider keys.")
    return {"keys": db.get_organization_ai_keys(org_id)}


@api.post("/organizations/{org_id}/ai-keys")
def set_organization_ai_key(org_id: str, body: SetOrganizationAIKeyRequest, user: User = Depends(current_user)):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if org.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only organization owners and admins can configure AI provider keys.")
    try:
        return db.set_organization_ai_key(org_id, body.provider, body.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@api.delete("/organizations/{org_id}/ai-keys/{provider}")
def delete_organization_ai_key(org_id: str, provider: str, user: User = Depends(current_user)):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if org.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only organization owners and admins can remove AI provider keys.")
    deleted = db.delete_organization_ai_key(org_id, provider)
    llm.clear_request_api_keys(provider)
    return {"status": "ok" if deleted else "not_found", "provider": provider}


@api.get("/organizations/{org_id}/api-keys")
def list_developer_api_keys(org_id: str, user: User = Depends(current_user)):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if org.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only organization owners and admins can view API keys.")
    return {"api_keys": db.list_developer_api_keys(org_id)}


@api.post("/organizations/{org_id}/api-keys", status_code=201)
def create_developer_api_key(org_id: str, body: CreateDeveloperApiKeyRequest, user: User = Depends(current_user)):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if org.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only organization owners and admins can generate API keys.")
    entitlements.check_can_use_api(org_id)
    try:
        key_meta, raw_secret = db.create_developer_api_key(
            org_id=org_id,
            user_id=user.id,
            name=body.name,
            workspace_id=body.workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"key": key_meta, "secret": raw_secret}


@api.delete("/organizations/{org_id}/api-keys/{key_id}")
def revoke_developer_api_key(org_id: str, key_id: str, user: User = Depends(current_user)):
    org = db.get_organization(org_id, user.id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if org.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only organization owners and admins can revoke API keys.")
    revoked = db.revoke_developer_api_key(org_id, key_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found.")
    return {"status": "ok", "id": key_id}


@api.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    raw_body = await request.body()
    headers = dict(request.headers)
    try:
        result = billing.handle_webhook("stripe", raw_body, headers)
        return JSONResponse(status_code=200, content=result)
    except ValueError as e:
        logger.warning("Stripe webhook verification or validation failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Stripe webhook handling failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error handling webhook")


@api.post("/webhooks/chapa")
async def chapa_webhook(request: Request):
    raw_body = await request.body()
    headers = dict(request.headers)
    try:
        result = billing.handle_webhook("chapa", raw_body, headers)
        return JSONResponse(status_code=200, content=result)
    except ValueError as e:
        logger.warning("Chapa webhook verification or validation failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Chapa webhook handling failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error handling webhook")


# --- workspace management ----------------------------------------------------------------

@api.get("/workspaces")
def list_workspaces(org: Organization = Depends(current_organization)):
    return {"workspaces": user_workspaces(org.user, organization_id=org.id)}


@api.post("/workspaces", status_code=201)
def create_workspace(body: NameRequest, org: Organization = Depends(current_organization)):
    entitlements.check_can_create_workspace(org.id)
    return db.create_workspace(body.name.strip(), org.user.id, organization_id=org.id)


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
    workspace = check_workspace_admin_or_owner(workspace_id, user.id)
    email = body.email.strip()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Enter an email address.")
    invitee = db.find_user_by_email(email)
    if invitee:
        db.add_member(workspace_id, invitee["id"], role=body.role)
        message = f"{email} can now use this workspace as a {body.role}."
    else:
        db.invite(workspace_id, email, user.id)
        message = f"Invitation saved. {email} joins this workspace when they sign up or sign in with that email."
    mailer.send(mailer.invitation(email, user.name or user.email, workspace["name"], has_account=bool(invitee)))
    if mailer.enabled():
        message += " We've emailed them."
    return {**team(workspace_id), "message": message}


@api.patch("/workspaces/{workspace_id}/members/{member_id}")
def update_member_role(
    workspace_id: str, member_id: str, body: UpdateMemberRoleRequest, user: User = Depends(current_user)
):
    check_workspace_admin_or_owner(workspace_id, user.id)
    try:
        db.update_workspace_member_role(workspace_id, member_id, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return team(workspace_id)


@api.delete("/workspaces/{workspace_id}/invitations/{email}")
def cancel_invitation(workspace_id: str, email: str, user: User = Depends(current_user)):
    check_workspace_admin_or_owner(workspace_id, user.id)
    db.cancel_invitation(workspace_id, email)
    return team(workspace_id)


@api.delete("/workspaces/{workspace_id}/members/{member_id}")
def remove_member(workspace_id: str, member_id: str, user: User = Depends(current_user)):
    if member_id != user.id:  # members may leave; only owners and admins remove others
        check_workspace_admin_or_owner(workspace_id, user.id)
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
    require_workspace_role(workspace, "admin")
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
    if workspace.organization_id and contents:
        total_upload_bytes = sum(len(c) for _, c in contents)
        entitlements.check_can_upload(workspace.organization_id, total_upload_bytes, len(contents))
    saved, rejected = workspace.store.save_uploads(contents)
    return {"saved": saved, "errors": errors + rejected,
            "message": "Upload finished. Index the documents to search new files."}


@api.post("/documents/index")
def index_documents(full: bool = False, wait: bool = True, workspace: Workspace = Depends(current_workspace)):
    """Index new uploads (?full=true re-reads every document).

    With wait=false the work runs in the background and the job is returned at
    once; follow it with GET /api/jobs/{id}.
    """
    require_workspace_role(workspace, "admin")
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
def list_documents(tag: str | None = None, workspace: Workspace = Depends(current_workspace)):
    documents, stale = workspace.store.documents()
    all_tags = workspace.store.all_tags()
    if tag:
        tag_lower = tag.strip().lower()
        documents = [d for d in documents if any(t.lower() == tag_lower for t in d.get("tags", []))]
    return {"documents": documents,
            "tags": all_tags,
            "indexed_chunks": len(workspace.store.chunks),
            # Documents indexed with another search model or chunking; re-index to search them.
            "stale_documents": stale,
            # Uploaded files that aren't in the index (new, or failed to index).
            "unindexed_files": len(workspace.store.uploaded_files()) - len(documents),
            "storage": {"used_bytes": workspace.store.bytes_used(), "quota_bytes": config.WORKSPACE_QUOTA_BYTES or None},
            **search_settings()}


@api.get("/documents/tags")
def list_document_tags(workspace: Workspace = Depends(current_workspace)):
    return {"tags": workspace.store.all_tags()}


@api.patch("/documents/{source_id}/tags")
@api.put("/documents/{source_id}/tags")
def update_document_tags(source_id: str, body: DocumentTagsRequest, workspace: Workspace = Depends(current_workspace)):
    require_workspace_role(workspace, "member")
    try:
        updated = workspace.store.set_document_tags(source_id, body.tags)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    return {"source_id": source_id, "tags": updated}


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
    require_workspace_role(workspace, "admin")
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
    old_tags = workspace.store.get_document_tags(source_id)
    workspace.store.remove(source_id)
    if old_tags:
        workspace.store.set_document_tags(saved[0]["stored_name"], old_tags)
    return {"saved": saved[0], "replaced": source_id,
            "message": "New version uploaded. Index the documents to make it searchable."}


@api.delete("/documents/{source_id}")
def delete_document(source_id: str, workspace: Workspace = Depends(current_workspace)):
    require_workspace_role(workspace, "admin")
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
    api_key: str | None = None
    deep_mode: bool = False


def prepare_ask(request: AskRequest, workspace: Workspace, check_available: bool) -> PreparedAsk:
    limits.check(f"ask:{workspace.user.id}", limits.ASK_LIMITS)
    check_index_ready(workspace)
    org_id = workspace.organization_id
    if not org_id:
        user_orgs = db.list_user_organizations(workspace.user.id)
        if user_orgs:
            org_id = user_orgs[0]["id"]

    byok_keys = db.get_all_raw_organization_ai_keys(org_id) if org_id else {}
    if byok_keys:
        llm.set_request_api_keys(byok_keys)
    provider = choose_provider(request)
    provider_api_key = None
    if provider and byok_keys:
        aliases = {
            "chatgpt": "openai",
            "openai": "chatgpt",
            "claude": "anthropic",
            "anthropic": "claude",
            "gemini": "google",
            "google": "gemini",
        }
        provider_api_key = byok_keys.get(provider) or byok_keys.get(aliases.get(provider, ""))
    if provider and check_available:
        reason = llm.PROVIDERS[provider].unavailable_reason(api_key=provider_api_key)
        if reason:
            raise HTTPException(status_code=400, detail=f"{llm.PROVIDERS[provider].label} is not available: {reason}")
    if org_id:
        prov = llm.PROVIDERS.get(provider) if provider else None
        model_name = request.model or (prov.model if prov else None)
        kind_name = prov.kind if prov else None
        entitlements.check_can_ask(org_id, model_name, kind=kind_name)
    chat = None
    if request.chat_id:
        chat = db.get_chat(request.chat_id, workspace.id, workspace.user.id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found.")
    history = chat_history(chat)

    if request.deep_mode:
        sources = workspace.store.retrieve_deep(
            request.question,
            source_ids=request.source_ids,
            tags=request.tags,
            provider=provider,
            model=request.model,
        )
        covered = bool(sources)
    else:
        def search(query: str) -> list[dict[str, Any]]:
            return workspace.store.retrieve(
                query, request.top_k, rerank=request.rerank, source_ids=request.source_ids, tags=request.tags
            )

        sources = search(request.question)
        # A follow-up like "and the price?" may find nothing on its own; then search
        # again together with the previous question. Questions that work on their own
        # (including a new topic in the same chat) are searched as they are.
        with_context = answers.search_query(request.question, history)
        if not answers.is_covered(sources) and with_context != request.question:
            alternative = search(with_context)
            if answers.is_covered(alternative):
                sources = alternative
        covered = answers.is_covered(sources)

    if request.save and workspace.role == "viewer":
        raise HTTPException(status_code=403, detail="Viewers cannot create or save chats in this workspace.")
    if request.save and not chat:
        chat = db.create_chat(workspace.id, workspace.user.id, request.question)

    return PreparedAsk(
        provider,
        chat,
        history,
        answers.focus(sources) if (covered and not request.deep_mode) else sources,
        covered,
        api_key=provider_api_key,
        deep_mode=request.deep_mode,
    )


def search_summary(request: AskRequest, prepared: PreparedAsk) -> dict[str, Any]:
    active_model = request.model or (llm.PROVIDERS[prepared.provider].model if prepared.provider else None)
    return {
        "question": request.question,
        "provider": prepared.provider,
        "model": active_model,
        "deep_mode": prepared.deep_mode,
        "reranked": any("rerank_score" in item for item in prepared.sources),
        "covered": prepared.covered,
        "chat_id": prepared.chat["id"] if prepared.chat else None,
        "sources": answers.source_payload(prepared.sources),
        "tags": request.tags,
    }


def account_usage(workspace: Workspace, provider: str | None, usage: llm.Usage) -> dict[str, Any] | None:
    """Record the tokens an answer used against the workspace; returns them for the message."""
    prov = provider or "local"
    model = llm.PROVIDERS[prov].model if prov in llm.PROVIDERS else prov
    cost = llm.cost_usd(model, usage) if prov in llm.PROVIDERS else 0.0
    in_tok = usage.input_tokens or 0
    out_tok = usage.output_tokens or 0
    db.record_usage(workspace.id, workspace.user.id, prov, model, in_tok, out_tok, cost)
    if in_tok or out_tok:
        return {"input_tokens": in_tok, "output_tokens": out_tok, "cost_usd": cost}
    return None


def maybe_rename_chat(chat: dict[str, Any], question: str, answer: str | None) -> str | None:
    """If this is the first assistant turn in the chat, auto-rename with a clean title."""
    try:
        chat_id = chat["id"]
        messages = db.list_messages(chat_id)
        # Exactly 1 user message (or fewer) exists before this assistant message is saved
        if len(messages) <= 1:
            current_title = chat.get("title", "")
            if current_title in ("New chat", question[:120], question.strip()):
                title = answers.generate_chat_title(question, answer)
                if title:
                    db.rename_chat(chat_id, title)
                    return title
    except Exception:
        logger.exception("Failed to auto-rename chat %s", chat.get("id"))
    return None


def save_turn(prepared: PreparedAsk, summary: dict[str, Any], answer: str | None, removed: list[str],
              error: str | None, seconds: float, usage: dict[str, Any] | None = None,
              suggestions: list[str] | None = None) -> tuple[str | None, str | None]:
    """Store the answer in the chat; returns (assistant_message_id, new_chat_title)."""
    if not prepared.chat:
        return None, None
    new_title = maybe_rename_chat(prepared.chat, summary["question"], answer)
    data = {key: summary[key] for key in ("provider", "model", "deep_mode", "reranked", "covered", "sources")}
    data.update(removed_citations=removed, error=error, seconds=round(seconds, 1), usage=usage, suggestions=suggestions or [])
    message_id = db.add_message(prepared.chat["id"], "assistant", answer or "", data)["id"]
    return message_id, new_title


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
            system_prompt = (
                answers.deep_system_prompt_for_provider(prepared.provider)
                if prepared.deep_mode
                else answers.SYSTEM_PROMPT
            )
            answer = answers.generate_answer(
                request.question,
                prepared.sources,
                prepared.provider,
                prepared.history,
                usage,
                model=request.model,
                api_key=prepared.api_key,
                system_prompt=system_prompt,
                deep_mode=prepared.deep_mode,
            )
        except llm.ProviderError as exc:
            account_usage(workspace, prepared.provider, usage)  # a refusal may still be billed
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            # SDK errors: bad API key, rate limits, network, model download, GPU memory...
            logger.exception("Answer generation with %s failed", prepared.provider)
            raise HTTPException(status_code=502, detail=f"{prepared.provider} failed: {exc}") from exc
        answer, removed = clean_citations(answer, len(prepared.sources))
    used = account_usage(workspace, prepared.provider, usage)
    suggestions = answers.generate_suggestions(request.question, prepared.sources, answer, prepared.covered)
    message_id, new_title = save_turn(prepared, summary, answer, removed, None, time.monotonic() - started, used, suggestions)
    return {
        **summary,
        "answer": answer,
        "removed_citations": removed,
        "message_id": message_id,
        "suggestions": suggestions,
        "chat_title": new_title or (prepared.chat["title"] if prepared.chat else None),
    }


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

    stream_org_id = workspace.organization_id
    if not stream_org_id:
        user_orgs = db.list_user_organizations(workspace.user.id)
        if user_orgs:
            stream_org_id = user_orgs[0]["id"]
    byok_keys = db.get_all_raw_organization_ai_keys(stream_org_id) if stream_org_id else {}

    def event(kind: str, **fields: Any) -> str:
        return json.dumps({"type": kind, **fields}, ensure_ascii=False) + "\n"

    def events():
        if byok_keys:
            llm.set_request_api_keys(byok_keys)
        yield event("sources", **summary)
        if not prepared.provider:
            used = account_usage(workspace, None, llm.Usage())
            suggestions = answers.generate_suggestions(request.question, prepared.sources, None, prepared.covered)
            message_id, new_title = save_turn(prepared, summary, None, [], None, time.monotonic() - started, used, suggestions=suggestions)
            yield event("done", answer=None, removed_citations=[], message_id=message_id, suggestions=suggestions, chat_title=new_title)
            return
        pieces: list[str] = []
        usage = llm.Usage()
        try:
            if not prepared.sources or not prepared.covered:
                canned = answers.canned("not_covered" if prepared.sources else "no_sources", request.question)
                pieces.append(canned)
                yield event("token", text=canned)
            else:
                system_prompt = (
                answers.deep_system_prompt_for_provider(prepared.provider)
                if prepared.deep_mode
                else answers.SYSTEM_PROMPT
            )
                prompt = answers.build_prompt(
                    request.question,
                    prepared.sources,
                    prepared.history,
                    deep_mode=prepared.deep_mode,
                    provider=prepared.provider,
                )
                for piece in llm.stream(
                    prepared.provider,
                    system_prompt,
                    prompt,
                    usage,
                    model=request.model,
                    api_key=prepared.api_key,
                ):
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
        suggestions = answers.generate_suggestions(request.question, prepared.sources, answer, prepared.covered)
        message_id, new_title = save_turn(prepared, summary, answer, removed, None, time.monotonic() - started, used, suggestions)
        yield event("done", answer=answer, removed_citations=removed, message_id=message_id, suggestions=suggestions, chat_title=new_title)

    return StreamingResponse(events(), media_type="application/x-ndjson")


# --- chats ------------------------------------------------------------------------------------

def owned_chat(chat_id: str, workspace: Workspace) -> dict[str, Any]:
    chat = db.get_chat(chat_id, workspace.id, workspace.user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return chat


@api.get("/chats")
def list_chats(
    before: str | None = None,
    limit: int = 50,
    workspace: Workspace = Depends(current_workspace),
):
    """The user's chats, and chats others have shared with this workspace."""
    chats = db.list_chats(workspace.id, workspace.user.id, limit=limit, before=before)
    shared = db.list_shared_chats(workspace.id, workspace.user.id) if before is None else []
    has_more = len(chats) == limit
    next_cursor = chats[-1]["updated_at"] if chats and has_more else None
    return {
        "chats": chats,
        "shared": shared,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


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


# --- developer v1 endpoints ---------------------------------------------------------

@api.post("/v1/ask")
def v1_ask(
    body: V1AskRequest,
    user: User = Depends(current_user),
    x_organization_id: str | None = Header(default=None),
    x_workspace_id: str | None = Header(default=None),
):
    if not isinstance(x_organization_id, str):
        x_organization_id = None
    if not isinstance(x_workspace_id, str):
        x_workspace_id = None
    target_ws_id = body.workspace_id or x_workspace_id
    if user.api_key_record:
        org_id = user.api_key_record["organization_id"]
        key_ws = user.api_key_record.get("workspace_id")
        if key_ws and target_ws_id and target_ws_id != key_ws:
            raise HTTPException(status_code=403, detail="API key is restricted to a different workspace.")
        target_ws_id = target_ws_id or key_ws
    else:
        org_id = x_organization_id

    if target_ws_id:
        ws_row = db.get_workspace(target_ws_id, user.id, organization_id=org_id)
        if not ws_row:
            raise HTTPException(status_code=404, detail="Workspace not found.")
    else:
        if not org_id:
            user_orgs = db.list_user_organizations(user.id)
            org_id = user_orgs[0]["id"] if user_orgs else None
        workspaces = user_workspaces(user, organization_id=org_id)
        if not workspaces:
            raise HTTPException(status_code=404, detail="No workspaces found.")
        ws_row = workspaces[0]

    ws = Workspace(
        id=ws_row["id"],
        name=ws_row["name"],
        role=ws_row["role"],
        user=user,
        organization_id=ws_row.get("organization_id") or (org_id or ""),
    )

    if ws.organization_id:
        byok_keys = db.get_all_raw_organization_ai_keys(ws.organization_id)
        if byok_keys:
            llm.set_request_api_keys(byok_keys)

    ask_req = AskRequest(
        question=body.question,
        provider=body.provider,
        model=body.model,
        top_k=body.top_k,
        rerank=body.rerank,
        tags=body.tags,
        save=False,
        deep_mode=body.deep_mode,
    )
    res = ask(ask_req, workspace=ws)
    return {
        "question": res["question"],
        "answer": res["answer"],
        "sources": res.get("sources", []),
        "provider": res.get("provider"),
        "model": res.get("model"),
        "reranked": res.get("reranked", False),
        "covered": res.get("covered", False),
        "removed_citations": res.get("removed_citations", []),
    }


@api.post("/v1/search")
def v1_search(
    body: V1SearchRequest,
    user: User = Depends(current_user),
    x_organization_id: str | None = Header(default=None),
    x_workspace_id: str | None = Header(default=None),
):
    if not isinstance(x_organization_id, str):
        x_organization_id = None
    if not isinstance(x_workspace_id, str):
        x_workspace_id = None
    target_ws_id = body.workspace_id or x_workspace_id
    if user.api_key_record:
        org_id = user.api_key_record["organization_id"]
        key_ws = user.api_key_record.get("workspace_id")
        if key_ws and target_ws_id and target_ws_id != key_ws:
            raise HTTPException(status_code=403, detail="API key is restricted to a different workspace.")
        target_ws_id = target_ws_id or key_ws
    else:
        org_id = x_organization_id

    if target_ws_id:
        ws_row = db.get_workspace(target_ws_id, user.id, organization_id=org_id)
        if not ws_row:
            raise HTTPException(status_code=404, detail="Workspace not found.")
    else:
        if not org_id:
            user_orgs = db.list_user_organizations(user.id)
            org_id = user_orgs[0]["id"] if user_orgs else None
        workspaces = user_workspaces(user, organization_id=org_id)
        if not workspaces:
            raise HTTPException(status_code=404, detail="No workspaces found.")
        ws_row = workspaces[0]

    ws = Workspace(
        id=ws_row["id"],
        name=ws_row["name"],
        role=ws_row["role"],
        user=user,
        organization_id=ws_row.get("organization_id") or (org_id or ""),
    )
    status = ws.store.status()
    if status == "stale":
        raise HTTPException(
            status_code=409,
            detail="The search model or chunk settings changed. Re-index the documents before searching.",
        )
    if status == "empty":
        return {
            "query": body.query,
            "workspace_id": ws.id,
            "count": 0,
            "sources": [],
        }
    sources = ws.store.retrieve(body.query, top_k=body.top_k, rerank=body.rerank, tags=body.tags)
    return {
        "query": body.query,
        "workspace_id": ws.id,
        "count": len(sources),
        "sources": sources,
    }


@api.get("/v1/workspaces")
def v1_workspaces(
    user: User = Depends(current_user),
    x_organization_id: str | None = Header(default=None),
):
    if not isinstance(x_organization_id, str):
        x_organization_id = None
    if user.api_key_record:
        org_id = user.api_key_record["organization_id"]
        key_ws_id = user.api_key_record.get("workspace_id")
        workspaces = user_workspaces(user, organization_id=org_id)
        if key_ws_id:
            workspaces = [w for w in workspaces if w["id"] == key_ws_id]
        return {"workspaces": workspaces}

    org_id = x_organization_id
    workspaces = user_workspaces(user, organization_id=org_id)
    return {"workspaces": workspaces}


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
