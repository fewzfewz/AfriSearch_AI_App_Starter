"""Tests for SAAS-P0-01 Stage C: Multi-tenant backend authorization pipeline & cross-tenant isolation."""
import time
import jwt
import pytest

from backend import config, db
from conftest import SOLAR_GUIDE, upload

SECRET = "test-secret-at-least-32-bytes-long!!"


def token(sub="user-1", email="user1@example.com", secret=SECRET, audience="authenticated", expires_in=3600,
          algorithm="HS256", **extra):
    claims = {
        "sub": sub,
        "email": email,
        "aud": audience,
        "exp": int(time.time()) + expires_in,
        "user_metadata": {"full_name": email.split("@")[0].title()},
        **extra,
    }
    return jwt.encode(claims, secret, algorithm=algorithm)


def as_user(**kwargs):
    return {"Authorization": f"Bearer {token(**kwargs)}"}


@pytest.fixture
def supabase(app_env, monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "supabase")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", SECRET)


def test_current_organization_default_and_header(client, supabase):
    amina = as_user(sub="amina", email="amina@example.com")
    me = client.get("/me", headers=amina).json()
    assert len(me["organizations"]) >= 1
    default_org = me["organizations"][0]
    assert default_org["owner_id"] == "amina"

    # Default request without X-Organization-Id uses default org
    res = client.get("/workspaces", headers=amina)
    assert res.status_code == 200

    # Request with valid X-Organization-Id succeeds
    res_valid = client.get("/workspaces", headers={**amina, "X-Organization-Id": default_org["id"]})
    assert res_valid.status_code == 200

    # Request with invalid X-Organization-Id returns 404
    res_invalid = client.get("/workspaces", headers={**amina, "X-Organization-Id": "nonexistent-org"})
    assert res_invalid.status_code == 404


def test_ordinary_users_cannot_access_system_recovery_org(client, supabase):
    amina = as_user(sub="amina", email="amina@example.com")
    res = client.get("/workspaces", headers={**amina, "X-Organization-Id": db.SYSTEM_RECOVERY_ORG_ID})
    assert res.status_code == 404


def test_cross_tenant_workspace_isolation(client, supabase):
    amina = as_user(sub="amina", email="amina@example.com")
    juma = as_user(sub="juma", email="juma@example.com")

    # Amina creates workspace in her org
    amina_me = client.get("/me", headers=amina).json()
    amina_org_id = amina_me["organizations"][0]["id"]
    amina_ws = client.post("/workspaces", headers=amina, json={"name": "Amina Workspace"}).json()

    # Juma creates workspace in his org
    juma_me = client.get("/me", headers=juma).json()
    juma_org_id = juma_me["organizations"][0]["id"]
    assert amina_org_id != juma_org_id

    # Juma tries to access Amina's workspace directly
    res = client.get("/documents", headers={**juma, "X-Workspace-Id": amina_ws["id"]})
    assert res.status_code == 404

    # Juma tries to specify Amina's org and workspace
    res_spoof = client.get("/documents", headers={
        **juma,
        "X-Organization-Id": amina_org_id,
        "X-Workspace-Id": amina_ws["id"],
    })
    assert res_spoof.status_code == 404


def test_cross_tenant_document_download_blocked(client, supabase):
    amina = as_user(sub="amina", email="amina@example.com")
    juma = as_user(sub="juma", email="juma@example.com")

    # Amina uploads document and indexes it
    upload_res = client.post("/documents/upload", headers=amina,
                             files=[("files", ("secret.txt", b"confidential research", "text/plain"))])
    assert upload_res.status_code == 200
    client.post("/documents/index", headers=amina)

    doc_res = client.get("/documents", headers=amina).json()
    assert len(doc_res["documents"]) == 1
    source_id = doc_res["documents"][0]["source_id"]
    amina_ws_id = client.get("/me", headers=amina).json()["workspaces"][0]["id"]

    # Juma tries to download Amina's document
    dl_res = client.get(f"/documents/{source_id}/file", headers={**juma, "X-Workspace-Id": amina_ws_id})
    assert dl_res.status_code == 404


def test_local_mode_preservation(client):
    # In local mode (AFRISEARCH_AUTH=none)
    me = client.get("/me").json()
    assert me["user"]["id"] == "local"
    assert len(me["organizations"]) >= 1
    assert me["organizations"][0]["name"] == "Local user's Organization"

    # Workspace operations work cleanly
    ws_res = client.get("/workspaces")
    assert ws_res.status_code == 200
    assert len(ws_res.json()["workspaces"]) >= 1
