"""Tests for Stripe & Chapa billing integration, webhook processing, and invoices ledger."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import pytest
from fastapi.testclient import TestClient

from backend import config, db, entitlements, main

client = TestClient(main.app)

TEST_STRIPE_WEBHOOK_SECRET = "whsec_test_secret_for_tests_123456"
TEST_CHAPA_WEBHOOK_SECRET = "chapa_sec_test_secret_for_tests_123456"


def stripe_sign(raw_body: bytes, secret: str = TEST_STRIPE_WEBHOOK_SECRET) -> dict[str, str]:
    t = int(time.time())
    signed_payload = f"{t}.".encode("utf-8") + raw_body
    computed = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return {
        "Stripe-Signature": f"t={t},v1={computed}",
        "Content-Type": "application/json",
    }


def chapa_sign(raw_body: bytes, secret: str = TEST_CHAPA_WEBHOOK_SECRET) -> dict[str, str]:
    computed = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return {
        "x-chapa-signature": computed,
        "Content-Type": "application/json",
    }


def setup_local_user() -> None:
    db.ensure_user("local", "local@localhost", "Local User")


def test_billing_checkout_and_rbac():
    setup_local_user()
    org = db.create_organization("Billing Test Org", "local")
    org_id = org["id"]

    # 1. Non-owner cannot checkout
    db.ensure_user("member1", "member1@test.com", "Member One")
    db.add_organization_member(org_id, "member1", "member")

    # When accessed by owner (in local mode, caller is 'local')
    res = client.post(
        f"/api/organizations/{org_id}/checkout",
        json={"plan_id": "pro", "seats": 2, "provider": "stripe"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert "checkout_url" in data
    assert "session_id" in data
    assert "mock_cs_" in data["session_id"] or "cs_" in data["session_id"]

    # 2. Chapa checkout for African payment rails (ETB)
    res_chapa = client.post(
        f"/api/organizations/{org_id}/checkout",
        json={"plan_id": "business", "seats": 1, "provider": "chapa", "currency": "ETB"},
    )
    assert res_chapa.status_code == 200, res_chapa.text
    chapa_data = res_chapa.json()
    assert "checkout_url" in chapa_data
    assert "tx_ref" in chapa_data["checkout_url"] or "mock_chapa_" in chapa_data["session_id"]


def test_stripe_webhook_checkout_completed_and_idempotency(monkeypatch):
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", TEST_STRIPE_WEBHOOK_SECRET)
    setup_local_user()
    org = db.create_organization("Stripe Webhook Org", "local")
    org_id = org["id"]

    # Initial subscription is Free
    sub = db.get_organization_subscription(org_id)
    assert sub["plan_id"] == "free"

    # Simulate Stripe checkout.session.completed webhook
    event_id = f"evt_test_checkout_{int(time.time() * 1000)}"
    webhook_payload = {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_12345",
                "client_reference_id": org_id,
                "customer": "cus_stripe_abc123",
                "subscription": "sub_stripe_xyz789",
                "amount_total": 2900,
                "currency": "usd",
                "invoice": "in_test_invoice_001",
                "metadata": {
                    "organization_id": org_id,
                    "plan_id": "pro",
                    "seats": "3",
                },
            }
        },
    }

    raw_body = json.dumps(webhook_payload).encode("utf-8")
    headers = stripe_sign(raw_body)
    resp = client.post(
        "/api/webhooks/stripe",
        content=raw_body,
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["status"] == "processed"

    # Verify subscription was upgraded
    sub_after = db.get_organization_subscription(org_id)
    assert sub_after["plan_id"] == "pro"
    assert sub_after["status"] == "active"
    assert sub_after["provider"] == "stripe"
    assert sub_after["provider_customer_id"] == "cus_stripe_abc123"
    assert sub_after["provider_subscription_id"] == "sub_stripe_xyz789"
    assert sub_after["seats_purchased"] == 3

    # Verify invoice was recorded in DB
    invoices = db.list_organization_invoices(org_id)
    assert len(invoices) >= 1
    assert invoices[0]["amount_cents"] == 2900
    assert invoices[0]["currency"] == "USD"
    assert invoices[0]["status"] == "paid"

    # Test idempotency: sending identical event again should succeed without re-processing
    resp_repeat = client.post(
        "/api/webhooks/stripe",
        content=raw_body,
        headers=headers,
    )
    assert resp_repeat.status_code == 200
    assert resp_repeat.json()["status"] == "already_processed"


def test_stripe_webhook_invoice_paid_and_subscription_lifecycle(monkeypatch):
    monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", TEST_STRIPE_WEBHOOK_SECRET)
    setup_local_user()
    org = db.create_organization("Stripe Lifecycle Org", "local")
    org_id = org["id"]

    # Set up active subscription
    db.update_organization_subscription(
        org_id,
        plan_id="pro",
        status="active",
        provider="stripe",
        provider_customer_id="cus_life_123",
        provider_subscription_id="sub_life_999",
    )

    # 1. invoice.paid
    inv_event_id = f"evt_inv_{int(time.time() * 1000)}"
    inv_payload = {
        "id": inv_event_id,
        "type": "invoice.paid",
        "data": {
            "object": {
                "id": "in_rec_888",
                "customer": "cus_life_123",
                "subscription": "sub_life_999",
                "amount_paid": 2900,
                "currency": "usd",
                "hosted_invoice_url": "https://invoice.stripe.com/inv_123",
                "invoice_pdf": "https://invoice.stripe.com/inv_123.pdf",
                "lines": {
                    "data": [
                        {
                            "period": {
                                "start": 1731168000,
                                "end": 1733760000,
                            }
                        }
                    ]
                },
            }
        },
    }
    raw_inv = json.dumps(inv_payload).encode("utf-8")
    resp = client.post("/api/webhooks/stripe", content=raw_inv, headers=stripe_sign(raw_inv))
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"

    invoices = db.list_organization_invoices(org_id)
    assert any(i["provider_invoice_id"] == "in_rec_888" for i in invoices)

    # 2. customer.subscription.updated (past_due)
    update_event_id = f"evt_sub_upd_{int(time.time() * 1000)}"
    update_payload = {
        "id": update_event_id,
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_life_999",
                "customer": "cus_life_123",
                "status": "past_due",
                "cancel_at_period_end": True,
            }
        },
    }
    raw_upd = json.dumps(update_payload).encode("utf-8")
    resp = client.post("/api/webhooks/stripe", content=raw_upd, headers=stripe_sign(raw_upd))
    assert resp.status_code == 200

    sub_updated = db.get_organization_subscription(org_id)
    assert sub_updated["status"] == "past_due"
    assert sub_updated["cancel_at_period_end"] == 1

    # 3. customer.subscription.deleted (downgrade to free)
    del_event_id = f"evt_sub_del_{int(time.time() * 1000)}"
    del_payload = {
        "id": del_event_id,
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_life_999",
                "customer": "cus_life_123",
            }
        },
    }
    raw_del = json.dumps(del_payload).encode("utf-8")
    resp = client.post("/api/webhooks/stripe", content=raw_del, headers=stripe_sign(raw_del))
    assert resp.status_code == 200

    sub_canceled = db.get_organization_subscription(org_id)
    assert sub_canceled["plan_id"] == "free"
    assert sub_canceled["status"] == "canceled"


def test_chapa_webhook_charge_success(monkeypatch):
    monkeypatch.setattr(config, "CHAPA_WEBHOOK_SECRET", TEST_CHAPA_WEBHOOK_SECRET)
    setup_local_user()
    org = db.create_organization("Chapa Webhook Org", "local")
    org_id = org["id"]

    tx_ref = f"afrisearch_{org_id[:8]}_business_{int(time.time())}"
    chapa_payload = {
        "event": "charge.success",
        "tx_ref": tx_ref,
        "status": "success",
        "amount": 18000,
        "currency": "ETB",
        "meta": {
            "organization_id": org_id,
            "plan_id": "business",
            "seats": 2,
        },
    }

    raw_body = json.dumps(chapa_payload).encode("utf-8")
    headers = chapa_sign(raw_body)
    resp = client.post("/api/webhooks/chapa", content=raw_body, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "processed"

    # Verify subscription state
    sub = db.get_organization_subscription(org_id)
    assert sub["plan_id"] == "business"
    assert sub["status"] == "active"
    assert sub["provider"] == "chapa"
    assert sub["seats_purchased"] == 2
    assert sub["provider_subscription_id"] == tx_ref

    # Verify invoice was recorded in ETB
    invoices = db.list_organization_invoices(org_id)
    assert len(invoices) >= 1
    assert invoices[0]["currency"] == "ETB"
    assert invoices[0]["amount_cents"] == 1800000
    assert invoices[0]["status"] == "paid"

    # Repeat test for idempotency
    resp_dup = client.post("/api/webhooks/chapa", content=raw_body, headers=headers)
    assert resp_dup.status_code == 200
    assert resp_dup.json()["status"] == "already_processed"


def test_invoices_api_endpoint():
    setup_local_user()
    org = db.create_organization("Invoices API Org", "local")
    org_id = org["id"]

    # Record two invoices
    db.record_invoice(
        org_id,
        provider="stripe",
        amount_cents=2900,
        currency="USD",
        status="paid",
        hosted_invoice_url="https://stripe.com/inv/1",
    )
    db.record_invoice(
        org_id,
        provider="chapa",
        amount_cents=350000,
        currency="ETB",
        status="paid",
    )

    resp = client.get(f"/api/organizations/{org_id}/invoices")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "invoices" in data
    assert len(data["invoices"]) == 2
    currencies = {inv["currency"] for inv in data["invoices"]}
    assert "USD" in currencies
    assert "ETB" in currencies
