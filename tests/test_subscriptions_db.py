import pytest
from backend import db

def test_organization_created_with_default_free_subscription(app_env):
    user_id = "sub-user-1"
    db.ensure_user(user_id, "sub1@example.com", "Sub User One")
    orgs = db.list_user_organizations(user_id)
    assert len(orgs) == 1
    org = orgs[0]

    sub = db.get_organization_subscription(org["id"])
    assert sub["organization_id"] == org["id"]
    assert sub["plan_id"] == "free"
    assert sub["status"] == "active"
    assert sub["seats_purchased"] == 1
    assert sub["provider"] == "none"


def test_custom_organization_gets_free_subscription(app_env):
    user_id = "sub-user-2"
    db.ensure_user(user_id, "sub2@example.com", "Sub User Two")
    org = db.create_organization("Acme Corp", user_id)

    sub = db.get_organization_subscription(org["id"])
    assert sub["organization_id"] == org["id"]
    assert sub["plan_id"] == "free"
    assert sub["status"] == "active"


def test_update_organization_subscription(app_env):
    user_id = "sub-user-3"
    db.ensure_user(user_id, "sub3@example.com", "Sub User Three")
    org = db.create_organization("Beta Lab", user_id)

    updated = db.update_organization_subscription(
        org["id"],
        plan_id="pro",
        seats_purchased=5,
        provider="stripe",
        provider_customer_id="cus_123",
        provider_subscription_id="sub_123",
    )
    assert updated["plan_id"] == "pro"
    assert updated["seats_purchased"] == 5
    assert updated["provider"] == "stripe"
    assert updated["provider_customer_id"] == "cus_123"

    sub = db.get_organization_subscription(org["id"])
    assert sub["plan_id"] == "pro"
    assert sub["seats_purchased"] == 5


def test_organization_usage_summary(app_env):
    user_id = "sub-user-4"
    db.ensure_user(user_id, "sub4@example.com", "Sub User Four")
    org = db.create_organization("Gamma Res", user_id)

    ws1 = db.create_workspace("WS 1", user_id, organization_id=org["id"])
    ws2 = db.create_workspace("WS 2", user_id, organization_id=org["id"])

    # Record some usage
    db.record_usage(ws1["id"], user_id, "google", "gemini-flash", 100, 200, 0.001)
    db.record_usage(ws2["id"], user_id, "anthropic", "claude-sonnet", 50, 100, 0.005)

    summary = db.get_organization_usage_summary(org["id"])
    assert summary["organization_id"] == org["id"]
    assert summary["workspace_count"] == 2
    assert summary["member_count"] == 1
    assert summary["questions_count"] == 2
    assert summary["input_tokens"] == 150
    assert summary["output_tokens"] == 300
    assert summary["cost_usd"] == 0.006
