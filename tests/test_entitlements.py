import pytest
from backend import db, entitlements, llm


def setup_local_user():
    db.ensure_user("local", "local@localhost", "Local user")


def test_list_plans(client, app_env):
    res = client.get("/plans")
    assert res.status_code == 200
    plans = res.json()["plans"]
    plan_ids = [p["id"] for p in plans]
    assert "free" in plan_ids
    assert "pro" in plan_ids
    assert "business" in plan_ids
    assert "enterprise" in plan_ids


def test_get_subscription_and_usage(client, app_env):
    setup_local_user()
    org = db.create_organization("Org One", "local")

    sub_res = client.get(f"/organizations/{org['id']}/subscription")
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["subscription"]["plan_id"] == "free"
    assert sub_data["plan"]["id"] == "free"

    usage_res = client.get(f"/organizations/{org['id']}/usage")
    assert usage_res.status_code == 200
    usage_data = usage_res.json()
    assert usage_data["usage"]["organization_id"] == org["id"]
    assert "max_workspaces" in usage_data["limits"]
    assert "max_seats" in usage_data["limits"]


def test_workspace_limit_enforcement_and_upgrade(client, app_env):
    setup_local_user()
    org = db.create_organization("Limit Org", "local")
    headers = {"X-Organization-Id": org["id"]}

    # Free plan allows 3 workspaces. Create 3 workspaces:
    res1 = client.post("/workspaces", json={"name": "WS 1"}, headers=headers)
    assert res1.status_code == 201
    res2 = client.post("/workspaces", json={"name": "WS 2"}, headers=headers)
    assert res2.status_code == 201
    res3 = client.post("/workspaces", json={"name": "WS 3"}, headers=headers)
    assert res3.status_code == 201

    # 4th workspace should hit quota
    res4 = client.post("/workspaces", json={"name": "WS 4"}, headers=headers)
    assert res4.status_code == 402
    assert "Workspace limit reached" in res4.json()["detail"]
    assert res4.headers.get("x-upgrade-required") == "workspaces"

    # Upgrade to Pro
    db.update_organization_subscription(org["id"], plan_id="pro")

    # Now 4th workspace succeeds
    res4_retry = client.post("/workspaces", json={"name": "WS 4"}, headers=headers)
    assert res4_retry.status_code == 201


def test_seat_limit_enforcement(client, app_env):
    setup_local_user()
    org = db.create_organization("Seats Org", "local")
    headers = {"X-Organization-Id": org["id"]}

    # Free plan has 5 seats. Owner takes 1 seat. We can invite 4 more:
    for i in range(1, 5):
        res = client.post(
            f"/organizations/{org['id']}/invitations",
            json={"email": f"invite{i}@example.com", "role": "member"},
            headers=headers,
        )
        assert res.status_code == 201

    # 5th invitation exceeds seat quota
    res_exceeded = client.post(
        f"/organizations/{org['id']}/invitations",
        json={"email": "overflow@example.com", "role": "member"},
        headers=headers,
    )
    assert res_exceeded.status_code == 402
    assert "Seat limit reached" in res_exceeded.json()["detail"]
    assert res_exceeded.headers.get("x-upgrade-required") == "seats"


def test_model_gating_and_query_quota(client, app_env, monkeypatch):
    setup_local_user()
    org = db.create_organization("AI Org", "local")
    ws = db.create_workspace("AI WS", "local", organization_id=org["id"])
    headers = {"X-Workspace-Id": ws["id"], "X-Organization-Id": org["id"]}

    # Upload a test file so index is ready
    client.post("/documents/upload", headers=headers, files=[("files", ("test.txt", b"Solar energy is renewable.", "text/plain"))])
    client.post("/documents/index", headers=headers)

    fake_opus = llm.Provider(
        id="opus",
        label="Claude Opus",
        kind="api",
        model="claude-opus-5-5",
        check=lambda: None,
        generate=lambda sys, prompt: "Opus answer",
    )
    monkeypatch.setitem(llm.PROVIDERS, "opus", fake_opus)

    res_blocked = client.post("/ask", json={"question": "What is solar energy?", "provider": "opus"}, headers=headers)
    assert res_blocked.status_code == 403
    assert "not available on the Free Tier" in res_blocked.json()["detail"]
    assert res_blocked.headers.get("x-upgrade-required") == "model"

    # Upgrade to Business tier
    db.update_organization_subscription(org["id"], plan_id="business")

    # Now asking with opus succeeds
    res_allowed = client.post("/ask", json={"question": "What is solar energy?", "provider": "opus"}, headers=headers)
    assert res_allowed.status_code == 200
