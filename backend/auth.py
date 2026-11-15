"""Who is making a request: a Supabase-signed-in user, or the local user when sign-in is off."""
from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException

from backend import config, db, entitlements, mailer


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str
    api_key_record: dict[str, Any] | None = None


@dataclass(frozen=True)
class Organization:
    id: str
    name: str
    role: str
    user: User


# With AFRISEARCH_AUTH=none everyone is this user.
LOCAL_USER = User(id="local", email="", name="Local user")

_jwks_client: jwt.PyJWKClient | None = None
_jwks_lock = threading.Lock()


def _jwks() -> jwt.PyJWKClient:
    global _jwks_client
    with _jwks_lock:
        if _jwks_client is None:
            # Supabase publishes the public keys that sign its access tokens here.
            _jwks_client = jwt.PyJWKClient(f"{config.SUPABASE_URL}/auth/v1/.well-known/jwks.json", cache_keys=True)
        return _jwks_client


def verify_token(token: str) -> dict[str, Any]:
    """The claims of a valid Supabase access token; raises jwt.PyJWTError otherwise."""
    options = {"require": ["exp", "sub"]}
    if config.SUPABASE_JWT_SECRET:  # projects still on the legacy shared secret
        return jwt.decode(token, config.SUPABASE_JWT_SECRET, algorithms=["HS256"],
                          audience="authenticated", options=options)
    key = _jwks().get_signing_key_from_jwt(token).key
    return jwt.decode(token, key, algorithms=["ES256", "RS256"], audience="authenticated", options=options)


def validate_auth_config() -> None:
    """Validate authentication configuration at startup.

    In production (AFRISEARCH_ENV=production):
    - AFRISEARCH_AUTH must never be 'none'.
    - If AFRISEARCH_AUTH=supabase, SUPABASE_URL must be a valid HTTP/HTTPS URL.
    - Unsupported auth modes raise RuntimeError.
    """
    env = (config.ENVIRONMENT or "").strip().lower()
    auth_mode = (config.AUTH_MODE or "").strip().lower()

    if env == "production":
        if auth_mode == "none":
            raise RuntimeError(
                "Production security violation: AFRISEARCH_ENV=production cannot run with AFRISEARCH_AUTH=none. "
                "Configure a valid authentication provider (e.g. AFRISEARCH_AUTH=supabase)."
            )
        if auth_mode == "supabase":
            if not config.SUPABASE_URL or not config.SUPABASE_URL.startswith(("http://", "https://")):
                raise RuntimeError(
                    "Production configuration error: SUPABASE_URL must be a valid HTTP/HTTPS URL when AFRISEARCH_AUTH=supabase."
                )
        else:
            raise RuntimeError(
                f"Production configuration error: Unsupported authentication mode '{auth_mode}'."
            )
    else:
        if auth_mode not in ("none", "supabase"):
            raise RuntimeError(
                f"Configuration error: Unsupported authentication mode '{auth_mode}'."
            )


def current_user(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> User:
    """FastAPI dependency: the signed-in user or authenticated API key caller."""
    if not isinstance(authorization, str):
        authorization = None
    if not isinstance(x_api_key, str):
        x_api_key = None

    api_token: str | None = None
    if x_api_key and x_api_key.strip().startswith("afri_live_"):
        api_token = x_api_key.strip()
    elif authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.startswith("afri_live_"):
            api_token = token.strip()
        elif authorization.strip().startswith("afri_live_"):
            api_token = authorization.strip()

    if api_token:
        key_hash = hashlib.sha256(api_token.encode("utf-8")).hexdigest()
        key_record = db.get_developer_api_key_by_hash(key_hash)
        if not key_record:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        entitlements.check_can_use_api(key_record["organization_id"])
        db.touch_developer_api_key(key_record["id"])
        user_row = db.get_user(key_record["user_id"])
        if user_row:
            return User(
                id=user_row["id"],
                email=user_row.get("email", ""),
                name=user_row.get("name", key_record["name"]),
                api_key_record=key_record,
            )
        return User(
            id=key_record["user_id"],
            email="",
            name=key_record["name"],
            api_key_record=key_record,
        )

    if config.AUTH_MODE == "none":
        if (config.ENVIRONMENT or "").strip().lower() == "production":
            raise HTTPException(
                status_code=500,
                detail="Production authentication error: AFRISEARCH_AUTH=none is prohibited in production.",
            )
        user = LOCAL_USER
    elif config.AUTH_MODE == "supabase":
        if not config.SUPABASE_URL:
            raise HTTPException(status_code=500, detail="Sign-in is misconfigured: SUPABASE_URL is not set.")
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="Sign in to continue.",
                                headers={"WWW-Authenticate": "Bearer"})
        try:
            claims = verify_token(token)
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(status_code=401, detail="Your session expired. Sign in again.") from exc
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail="Invalid sign-in token.") from exc
        metadata = claims.get("user_metadata") or {}
        email = claims.get("email") or ""
        user = User(id=claims["sub"], email=email,
                    name=metadata.get("full_name") or metadata.get("name") or email.split("@")[0])
    else:
        raise HTTPException(status_code=500, detail=f"Unknown AFRISEARCH_AUTH mode '{config.AUTH_MODE}'.")
    if db.ensure_user(user.id, user.email, user.name) and config.AUTH_MODE == "supabase":
        mailer.send(mailer.welcome(user.email, user.name))
    return user


def current_organization(
    user: User = Depends(current_user),
    x_organization_id: str | None = Header(default=None),
) -> Organization:
    """FastAPI dependency: the organization named in X-Organization-Id, or the user's primary one."""
    if not isinstance(x_organization_id, str):
        x_organization_id = None

    if user.api_key_record:
        key_org_id = user.api_key_record["organization_id"]
        if x_organization_id and x_organization_id != key_org_id:
            raise HTTPException(
                status_code=403,
                detail="API key cannot access other organizations.",
            )
        found = db.get_organization(key_org_id, user.id) or db.get_organization(key_org_id)
        if not found:
            raise HTTPException(status_code=404, detail="Organization not found.")
        return Organization(id=found["id"], name=found["name"], role=found.get("role", "member"), user=user)

    if x_organization_id:
        found = db.get_organization(x_organization_id, user.id)
        if not found:
            raise HTTPException(status_code=404, detail="Organization not found.")
    else:
        user_orgs = db.list_user_organizations(user.id)
        if not user_orgs:
            name_cand = user.name.strip()
            org_name = f"{name_cand}'s Organization" if name_cand else "Personal Organization"
            new_org = db.create_organization(org_name, user.id)
            found = {**new_org, "role": "owner"}
        else:
            found = user_orgs[0]
    return Organization(id=found["id"], name=found["name"], role=found["role"], user=user)
