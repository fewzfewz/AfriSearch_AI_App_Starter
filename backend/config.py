"""Settings read from the environment, and where data is stored.

Other modules read these as `config.NAME` at call time, so tests (and the
evaluation script) can point DATA_DIR somewhere else.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Holds afrisearch.db (accounts, workspaces, chats, feedback, jobs) and
# workspaces/<id>/ (uploads and search index of each workspace).
DATA_DIR = Path(os.getenv("AFRISEARCH_DATA_DIR", str(ROOT / "data")))
# The built web app (cd web && npm run build); served at / when present.
WEB_DIST = Path(os.getenv("AFRISEARCH_WEB_DIST", str(ROOT / "web" / "dist")))

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_FILES_PER_UPLOAD = 20
# Total size of uploads per workspace; 0 means no limit.
WORKSPACE_QUOTA_BYTES = int(float(os.getenv("AFRISEARCH_WORKSPACE_QUOTA_MB", "500")) * 1024 * 1024)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}
ALLOWED_EXTENSIONS = {".pdf", ".txt"} | IMAGE_EXTENSIONS
CHUNK_SIZE = 180  # target words per chunk
CHUNK_OVERLAP = 35  # words of whole sentences repeated from the previous chunk

# Sign-in. "none": no accounts, everyone is the same local user (self-hosting on
# your own machine, development, tests). "supabase": users sign in with Supabase
# Auth and send its access token; each user gets their own workspaces.
AUTH_MODE = os.getenv("AFRISEARCH_AUTH", "none").strip().lower()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
# Optional: lets "Delete account" also delete the Supabase sign-in account. Secret;
# keep it on the server only.
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
# Only for Supabase projects that still sign tokens with the legacy shared
# secret (HS256); newer projects publish signing keys, which need no secret here.
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
# Extra sign-in buttons shown by the web app, e.g. "google"; enable them in Supabase too.
# Shown on the privacy notice and terms pages.
ORG_NAME = os.getenv("AFRISEARCH_ORG_NAME", "")
CONTACT_EMAIL = os.getenv("AFRISEARCH_CONTACT_EMAIL", "")
# Error tracking with Sentry (optional). The web app's DSN is public by design.
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
SENTRY_DSN_WEB = os.getenv("SENTRY_DSN_WEB", "")
ENVIRONMENT = os.getenv("AFRISEARCH_ENV", "development")

AUTH_PROVIDERS = [p.strip() for p in os.getenv("AFRISEARCH_AUTH_PROVIDERS", "").split(",") if p.strip()]
