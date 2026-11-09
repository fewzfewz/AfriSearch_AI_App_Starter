"""Security Remediation Phase 1 Verification Tests.

Covers:
- TASK-SEC-01: Production Authentication Fail-Closed
- TASK-SEC-02: Payment Webhook Signature Verification (Stripe & Chapa)
- TASK-SEC-03: Workspace Organization Authorization, RBAC & Cross-Tenant Prevention
- TASK-SEC-04: Production Billing Configuration & Docker Compose Validation
"""
from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import auth, billing, config, db, main
from backend.billing import get_provider

client = TestClient(main.app)


# ==============================================================================
# Helpers
# ==============================================================================

def create_user(user_id: str, email: str, name: str) -> None:
    db.ensure_user(user_id, email, name)


def make_stripe_signature(raw_body: bytes, secret: str, timestamp: int | None = None) -> str:
    t = timestamp or int(time.time())
    signed_payload = f"{t}.".encode("utf-8") + raw_body
    computed = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={t},v1={computed}"


def make_chapa_signature(raw_body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


# ==============================================================================
# TASK-SEC-01: Production Authentication Fail-Closed
# ==============================================================================

def test_production_auth_fail_closed_when_none(monkeypatch):
    """Production must never start with AFRISEARCH_AUTH=none."""
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "AUTH_MODE", "none")

    with pytest.raises(RuntimeError, match="cannot run with AFRISEARCH_AUTH=none"):
        auth.validate_auth_config()


def test_production_auth_fail_closed_when_supabase_misconfigured(monkeypatch):
    """Production with Supabase auth must fail if SUPABASE_URL is missing or invalid."""
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "AUTH_MODE", "supabase")
    monkeypatch.setattr(config, "SUPABASE_URL", "")

    with pytest.raises(RuntimeError, match="SUPABASE_URL must be a valid HTTP/HTTPS URL"):
        auth.validate_auth_config()

    monkeypatch.setattr(config, "SUPABASE_URL", "not-a-valid-url")
    with pytest.raises(RuntimeError, match="SUPABASE_URL must be a valid HTTP/HTTPS URL"):
        auth.validate_auth_config()


def test_production_auth_valid_supabase_passes(monkeypatch):
    """Production with valid Supabase URL passes validation."""
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "AUTH_MODE", "supabase")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://xyzcompany.supabase.co")

    # Should not raise
    auth.validate_auth_config()


def test_dev_test_auth_allows_none(monkeypatch):
    """Development and test environments can safely use AFRISEARCH_AUTH=none."""
    monkeypatch.setattr(config, "ENVIRONMENT", "development")
    monkeypatch.setattr(config, "AUTH_MODE", "none")

    # Should not raise in development
    auth.validate_auth_config()

    user = auth.current_user(authorization=None)
    assert user.id == "local"


def test_current_user_prohibits_none_in_production(monkeypatch):
    """current_user() dependency fails closed with HTTP 500 if AUTH_MODE=none in production."""
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "AUTH_MODE", "none")

    with pytest.raises(HTTPException) as exc_info:
        auth.current_user(authorization=None)
    assert exc_info.value.status_code == 500
    assert "AFRISEARCH_AUTH=none is prohibited in production" in exc_info.value.detail


# ==============================================================================
# TASK-SEC-02: Payment Webhook Verification (Stripe & Chapa)
# ==============================================================================

def test_stripe_webhook_rejects_missing_secret(monkeypatch):
    """Stripe webhook signature check must fail if webhook secret is unset or empty."""
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "")
    provider = get_provider("stripe")

    body = b'{"id":"evt_123","type":"checkout.session.completed"}'
    headers = {"stripe-signature": "t=123,v1=fake_sig"}

    assert provider.verify_webhook_signature(body, headers) is False

    resp = client.post("/api/webhooks/stripe", content=body, headers=headers)
    assert resp.status_code == 400
    assert "Invalid Stripe webhook signature" in resp.json()["detail"]


def test_stripe_webhook_rejects_empty_secret(monkeypatch):
    """Stripe webhook signature check must fail if secret is whitespace."""
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "   ")
    provider = get_provider("stripe")

    body = b'{"id":"evt_123","type":"checkout.session.completed"}'
    headers = {"stripe-signature": "t=123,v1=fake_sig"}

    assert provider.verify_webhook_signature(body, headers) is False


def test_stripe_webhook_rejects_invalid_signature(monkeypatch):
    """Stripe webhook with incorrect signature must be rejected."""
    secret = "whsec_test_stripe_secret_key_123"
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", secret)
    provider = get_provider("stripe")

    body = b'{"id":"evt_123","type":"checkout.session.completed"}'
    headers = {"stripe-signature": "t=123,v1=bad_signature_hash"}

    assert provider.verify_webhook_signature(body, headers) is False

    resp = client.post("/api/webhooks/stripe", content=body, headers=headers)
    assert resp.status_code == 400
    assert "Invalid Stripe webhook signature" in resp.json()["detail"]


def test_stripe_webhook_accepts_valid_signature_and_handles_malformed_and_duplicate(monkeypatch):
    """Stripe webhook verifies valid signature, handles malformed payloads, and handles duplicates."""
    secret = "whsec_test_stripe_secret_key_123"
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", secret)
    create_user("local", "local@example.com", "Local User")
    org = db.create_organization("Stripe Sec Test Org", "local")

    event_id = f"evt_sec_stripe_{int(time.time() * 1000)}"
    valid_payload = {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_valid",
                "client_reference_id": org["id"],
                "customer": "cus_valid_123",
                "subscription": "sub_valid_123",
                "amount_total": 2900,
                "currency": "usd",
                "metadata": {
                    "organization_id": org["id"],
                    "plan_id": "pro",
                    "seats": 1,
                },
            }
        },
    }
    raw_body = json.dumps(valid_payload).encode("utf-8")
    sig = make_stripe_signature(raw_body, secret)
    headers = {"Stripe-Signature": sig, "Content-Type": "application/json"}

    # 1. Valid delivery -> 200
    resp = client.post("/api/webhooks/stripe", content=raw_body, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"

    # 2. Duplicate delivery -> 200 already_processed
    resp_dup = client.post("/api/webhooks/stripe", content=raw_body, headers=headers)
    assert resp_dup.status_code == 200
    assert resp_dup.json()["status"] == "already_processed"

    # 3. Malformed JSON payload with valid signature for that byte sequence -> 400 Malformed
    bad_json = b"NOT_JSON_BODY_DATA"
    bad_sig = make_stripe_signature(bad_json, secret)
    resp_bad = client.post("/api/webhooks/stripe", content=bad_json, headers={"Stripe-Signature": bad_sig})
    assert resp_bad.status_code == 400
    assert "Malformed webhook JSON" in resp_bad.json()["detail"]


def test_chapa_webhook_rejects_missing_secret(monkeypatch):
    """Chapa webhook signature check must fail if webhook secret is unset."""
    monkeypatch.setattr(config, "CHAPA_WEBHOOK_SECRET", "")
    monkeypatch.setattr(config, "CHAPA_SECRET_KEY", "")
    provider = get_provider("chapa")

    body = b'{"event":"charge.success","tx_ref":"tx_123"}'
    headers = {"x-chapa-signature": "fake_sig"}

    assert provider.verify_webhook_signature(body, headers) is False

    resp = client.post("/api/webhooks/chapa", content=body, headers=headers)
    assert resp.status_code == 400
    assert "Invalid Chapa webhook signature" in resp.json()["detail"]


def test_chapa_webhook_rejects_invalid_signature(monkeypatch):
    """Chapa webhook with invalid signature must be rejected."""
    secret = "chapa_sec_test_secret_key_456"
    monkeypatch.setattr(config, "CHAPA_WEBHOOK_SECRET", secret)
    provider = get_provider("chapa")

    body = b'{"event":"charge.success","tx_ref":"tx_123"}'
    headers = {"x-chapa-signature": "wrong_signature_hash"}

    assert provider.verify_webhook_signature(body, headers) is False

    resp = client.post("/api/webhooks/chapa", content=body, headers=headers)
    assert resp.status_code == 400
    assert "Invalid Chapa webhook signature" in resp.json()["detail"]


def test_chapa_webhook_accepts_valid_signature_and_handles_malformed_and_duplicate(monkeypatch):
    """Chapa webhook verifies valid signature, handles malformed JSON, and duplicate events."""
    secret = "chapa_sec_test_secret_key_456"
    monkeypatch.setattr(config, "CHAPA_WEBHOOK_SECRET", secret)
    create_user("local", "local@example.com", "Local User")
    org = db.create_organization("Chapa Sec Test Org", "local")

    tx_ref = f"afrisearch_{org['id'][:8]}_pro_{int(time.time())}"
    valid_payload = {
        "event": "charge.success",
        "tx_ref": tx_ref,
        "status": "success",
        "amount": 3500,
        "currency": "ETB",
        "meta": {
            "organization_id": org["id"],
            "plan_id": "pro",
            "seats": 1,
        },
    }
    raw_body = json.dumps(valid_payload).encode("utf-8")
    sig = make_chapa_signature(raw_body, secret)
    headers = {"x-chapa-signature": sig, "Content-Type": "application/json"}

    # 1. Valid signature -> 200
    resp = client.post("/api/webhooks/chapa", content=raw_body, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"

    # 2. Duplicate event -> 200 already_processed
    resp_dup = client.post("/api/webhooks/chapa", content=raw_body, headers=headers)
    assert resp_dup.status_code == 200
    assert resp_dup.json()["status"] == "already_processed"

    # 3. Malformed JSON -> 400
    bad_bytes = b"MALFORMED_CHAPA_JSON"
    bad_sig = make_chapa_signature(bad_bytes, secret)
    resp_bad = client.post("/api/webhooks/chapa", content=bad_bytes, headers={"x-chapa-signature": bad_sig})
    assert resp_bad.status_code == 400
    assert "Malformed Chapa webhook JSON" in resp_bad.json()["detail"]


def test_billing_startup_validation(monkeypatch):
    """Production validates that enabled payment providers have required webhook secrets."""
    monkeypatch.setattr(config, "ENVIRONMENT", "production")

    # When billing is disabled, validation passes cleanly
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "")
    monkeypatch.setattr(config, "CHAPA_SECRET_KEY", "")
    billing.validate_billing_config()

    # When Stripe is enabled without webhook secret, it fails
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_live_test123")
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "")
    with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY is configured but STRIPE_WEBHOOK_SECRET is missing"):
        billing.validate_billing_config()

    # When Stripe has webhook secret, it passes
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "whsec_test123")
    billing.validate_billing_config()

    # When Chapa is enabled without webhook secret, it fails
    monkeypatch.setattr(config, "CHAPA_SECRET_KEY", "CHASECK_live_test123")
    monkeypatch.setattr(config, "CHAPA_WEBHOOK_SECRET", "")
    # Note: Chapa fallback to secret_key only occurs if secret_key itself is non-empty,
    # but in our check we test explicit webhook validation:
    # If CHAPA_WEBHOOK_SECRET is empty string, ChapaProvider property falls back to self.secret_key.
    # To test missing secret on provider:
    p = get_provider("chapa")
    p._webhook_secret = ""
    with pytest.raises(RuntimeError, match="CHAPA_SECRET_KEY is configured but CHAPA_WEBHOOK_SECRET is missing"):
        billing.validate_billing_config()
    p._webhook_secret = None


# ==============================================================================
# TASK-SEC-03: Workspace Organization Authorization
# ==============================================================================

def test_workspace_organization_authorization_and_cross_tenant_isolation(monkeypatch):
    """Verify server-side workspace organization resolution and tenant boundary enforcement."""
    # Setup users
    user_alice = "user_alice_test"
    user_bob = "user_bob_test"
    user_carol = "user_carol_test"
    create_user(user_alice, "alice@example.com", "Alice Owner")
    create_user(user_bob, "bob@example.com", "Bob MultiOrg")
    create_user(user_carol, "carol@example.com", "Carol Outsider")

    # Org A (owned by Alice, Bob is a member)
    org_a = db.create_organization("Acme Org A", user_alice)
    org_a_id = org_a["id"]
    db.add_organization_member(org_a_id, user_bob, "member")

    # Workspace A in Org A
    ws_a = db.create_workspace("Acme Research", user_alice, organization_id=org_a_id)
    ws_a_id = ws_a["id"]

    # Org B (owned by Bob)
    org_b = db.create_organization("Beta Org B", user_bob)
    org_b_id = org_b["id"]
    ws_b = db.create_workspace("Beta Product", user_bob, organization_id=org_b_id)
    ws_b_id = ws_b["id"]

    # Add Bob to Workspace A as viewer
    db.add_member(ws_a_id, user_bob, role="viewer")

    # 1. Alice (Org Owner) accesses ws_a -> has 'owner' role even without explicit row in members
    ws_alice = db.get_workspace(ws_a_id, user_alice)
    assert ws_alice is not None
    assert ws_alice["role"] == "owner"
    assert ws_alice["organization_id"] == org_a_id

    # 2. Bob (legitimate multi-org member) accesses ws_a in Org A -> has 'viewer' role
    ws_bob_a = db.get_workspace(ws_a_id, user_bob)
    assert ws_bob_a is not None
    assert ws_bob_a["role"] == "viewer"
    assert ws_bob_a["organization_id"] == org_a_id

    # 3. Bob accesses ws_b in Org B -> has 'owner' role
    ws_bob_b = db.get_workspace(ws_b_id, user_bob)
    assert ws_bob_b is not None
    assert ws_bob_b["role"] == "owner"
    assert ws_bob_b["organization_id"] == org_b_id

    # 4. Carol (outsider) attempts to access ws_a -> None (404)
    ws_carol_a = db.get_workspace(ws_a_id, user_carol)
    assert ws_carol_a is None

    # 5. Missing organization header: resolving with organization_id=None succeeds server-side
    ws_no_header = db.get_workspace(ws_a_id, user_alice, organization_id=None)
    assert ws_no_header is not None
    assert ws_no_header["id"] == ws_a_id

    # 6. Incorrect organization header: asserting org_b_id for ws_a (which is in org_a_id) returns None
    ws_wrong_header = db.get_workspace(ws_a_id, user_alice, organization_id=org_b_id)
    assert ws_wrong_header is None


def test_organization_admin_workspace_permissions():
    """Organization admin has automatic admin access to workspaces in their organization."""
    owner_id = "user_org_owner_1"
    admin_id = "user_org_admin_1"
    member_id = "user_org_member_1"

    create_user(owner_id, "owner1@test.com", "Owner")
    create_user(admin_id, "admin1@test.com", "Admin")
    create_user(member_id, "member1@test.com", "Member")

    org = db.create_organization("Enterprise Org", owner_id)
    org_id = org["id"]
    db.add_organization_member(org_id, admin_id, "admin")
    db.add_organization_member(org_id, member_id, "member")

    ws = db.create_workspace("Secure Workspace", owner_id, organization_id=org_id)
    ws_id = ws["id"]

    # Admin was not explicitly added to members table, but has org admin role -> role is 'admin'
    ws_admin = db.get_workspace(ws_id, admin_id)
    assert ws_admin is not None
    assert ws_admin["role"] == "admin"

    # Member was not explicitly added to members table -> None (no access)
    ws_member = db.get_workspace(ws_id, member_id)
    assert ws_member is None

    # Add member as viewer -> role is 'viewer'
    db.add_member(ws_id, member_id, role="viewer")
    ws_viewer = db.get_workspace(ws_id, member_id)
    assert ws_viewer is not None
    assert ws_viewer["role"] == "viewer"


def test_workspace_role_restrictions_via_dependency():
    """Verify require_workspace_role enforces viewer and member restrictions."""
    u = auth.User(id="test_user_role", email="u@test.com", name="Test User")

    ws_viewer = main.Workspace(id="ws1", name="WS", role="viewer", user=u, organization_id="org1")
    ws_member = main.Workspace(id="ws1", name="WS", role="member", user=u, organization_id="org1")
    ws_admin = main.Workspace(id="ws1", name="WS", role="admin", user=u, organization_id="org1")
    ws_owner = main.Workspace(id="ws1", name="WS", role="owner", user=u, organization_id="org1")

    # Admin requirement
    with pytest.raises(HTTPException) as exc1:
        main.require_workspace_role(ws_viewer, "admin")
    assert exc1.value.status_code == 403

    with pytest.raises(HTTPException) as exc2:
        main.require_workspace_role(ws_member, "admin")
    assert exc2.value.status_code == 403

    # Admin and Owner pass admin requirement
    main.require_workspace_role(ws_admin, "admin")
    main.require_workspace_role(ws_owner, "admin")


def test_legacy_workspace_compatibility():
    """Workspaces with NULL organization_id remain accessible to their members."""
    legacy_user = "user_legacy_01"
    create_user(legacy_user, "legacy@test.com", "Legacy User")

    with db.connect() as conn:
        ws_id = "ws_legacy_no_org"
        ts = db.now()
        conn.execute("INSERT OR REPLACE INTO workspaces (id, organization_id, name, created_at) VALUES (?, NULL, ?, ?)", (ws_id, "Legacy WS", ts))
        conn.execute("INSERT OR REPLACE INTO members (workspace_id, user_id, role, added_at) VALUES (?, ?, 'owner', ?)", (ws_id, legacy_user, ts))

    ws = db.get_workspace(ws_id, legacy_user)
    assert ws is not None
    assert ws["name"] == "Legacy WS"
    assert ws["role"] == "owner"


# ==============================================================================
# TASK-SEC-04: Production Billing Configuration & Docker Compose Validation
# ==============================================================================

def test_docker_compose_production_config_validates():
    """Validate that docker compose merge produces valid YAML with all billing variables."""
    root = Path(__file__).resolve().parents[1]
    compose_base = root / "docker-compose.yml"
    compose_prod = root / "deploy" / "docker-compose.prod.yml"

    assert compose_base.is_file()
    assert compose_prod.is_file()

    # Read docker-compose.prod.yml content and check billing variables
    prod_content = compose_prod.read_text(encoding="utf-8")
    for var in [
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "CHAPA_SECRET_KEY",
        "CHAPA_WEBHOOK_SECRET",
        "CHAPA_API_URL",
        "BILLING_RETURN_URL_BASE",
    ]:
        assert var in prod_content, f"Missing {var} in deploy/docker-compose.prod.yml"

    # Read .env.example content and check documentation
    env_content = (root / ".env.example").read_text(encoding="utf-8")
    for var in [
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "CHAPA_SECRET_KEY",
        "CHAPA_WEBHOOK_SECRET",
        "CHAPA_API_URL",
        "BILLING_RETURN_URL_BASE",
    ]:
        assert var in env_content, f"Missing {var} documentation in .env.example"

    # Validate using docker-compose config
    cmd = [
        "docker-compose",
        "-f",
        str(compose_base),
        "-f",
        str(compose_prod),
        "config",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, env={"AFRISEARCH_DOMAIN": "example.com", "PATH": subprocess.os.environ.get("PATH", "")})
    assert res.returncode == 0, f"docker-compose config failed: {res.stderr}"
    assert "STRIPE_SECRET_KEY" in res.stdout
    assert "CHAPA_WEBHOOK_SECRET" in res.stdout
