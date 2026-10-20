"""Who is making a request: a Supabase-signed-in user, or the local user when sign-in is off."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Header, HTTPException

from backend import config, db, mailer


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str


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
