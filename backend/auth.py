"""Who is making a request: a Supabase-signed-in user, or the local user when sign-in is off."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException

from backend import config, db, mailer


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str


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


def current_user(authorization: str | None = Header(default=None)) -> User:
    """FastAPI dependency: the signed-in user (created in the database on first sight)."""
    if config.AUTH_MODE == "none":
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
