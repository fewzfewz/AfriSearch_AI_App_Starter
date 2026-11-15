import pytest
from backend import db, entitlements, llm


def setup_local_user():
    db.ensure_user("local", "local@localhost", "Local user")


def test_byok_keys_crud(client, app_env):
    setup_local_user()
    org = db.create_organization("BYOK Org", "local")

    # Set OpenAI key
    res = client.post(
        f"/organizations/{org['id']}/ai-keys",
        json={"provider": "openai", "api_key": "sk-proj-1234567890abcdefghijklmnopqrstuvwxyz"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["provider"] == "openai"
    assert "sk-proj" in data["key_hint"]

    # Verify secret is encrypted in database
    raw_decrypted = db.get_raw_organization_ai_key(org["id"], "openai")
    assert raw_decrypted == "sk-proj-1234567890abcdefghijklmnopqrstuvwxyz"

    # List keys (redacted hints only)
    res = client.get(f"/organizations/{org['id']}/ai-keys")
    assert res.status_code == 200
    keys = res.json()["keys"]
    assert "openai" in keys
    assert "1234567890" not in keys["openai"]  # full key not exposed

    # Delete key
    res = client.delete(f"/organizations/{org['id']}/ai-keys/openai")
    assert res.status_code == 200

    # Ensure deleted
    res = client.get(f"/organizations/{org['id']}/ai-keys")
    assert res.status_code == 200
    assert "openai" not in res.json()["keys"]


def test_developer_api_key_gating_and_lifecycle(client, app_env):
    setup_local_user()
    org = db.create_organization("API Key Org", "local")

    # Free tier should be blocked from creating developer API keys
    res = client.post(
        f"/organizations/{org['id']}/api-keys",
        json={"name": "Test Free Key"},
    )
    assert res.status_code == 402
    assert res.headers.get("x-upgrade-required") == "api_access"

    # Upgrade to Pro
    db.update_organization_subscription(org["id"], plan_id="pro")

    # Now key creation succeeds
    res = client.post(
        f"/organizations/{org['id']}/api-keys",
        json={"name": "Production Widget Key"},
    )
    assert res.status_code == 201
    created = res.json()
    raw_secret = created["secret"]
    key_meta = created["key"]
    assert raw_secret.startswith("afri_live_")
    assert key_meta["name"] == "Production Widget Key"

    # List keys
    list_res = client.get(f"/organizations/{org['id']}/api-keys")
    assert list_res.status_code == 200
    keys_list = list_res.json()["api_keys"]
    assert len(keys_list) == 1
    assert keys_list[0]["id"] == key_meta["id"]

    # Call v1 endpoints with Bearer auth
    v1_ws_res = client.get(
        "/v1/workspaces",
        headers={"Authorization": f"Bearer {raw_secret}"},
    )
    assert v1_ws_res.status_code == 200
    ws_data = v1_ws_res.json()
    assert "workspaces" in ws_data
    assert len(ws_data["workspaces"]) >= 1

    # Call v1 search
    search_res = client.post(
        "/v1/search",
        headers={"X-API-Key": raw_secret},
        json={"query": "test query"},
    )
    assert search_res.status_code == 200
    assert search_res.json()["query"] == "test query"

    # Invalid token check
    bad_auth_res = client.get(
        "/v1/workspaces",
        headers={"Authorization": "Bearer afri_live_invalidtoken1234567890"},
    )
    assert bad_auth_res.status_code == 401

    # Revoke key
    del_res = client.delete(f"/organizations/{org['id']}/api-keys/{key_meta['id']}")
    assert del_res.status_code == 200

    # Revoked key no longer works
    revoked_res = client.get(
        "/v1/workspaces",
        headers={"Authorization": f"Bearer {raw_secret}"},
    )
    assert revoked_res.status_code == 401
