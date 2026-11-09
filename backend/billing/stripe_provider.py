"""Stripe payment provider integration using standard HTTP REST and webhooks."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from backend import config, db, entitlements

logger = logging.getLogger(__name__)

STRIPE_API_BASE = "https://api.stripe.com/v1"


def _to_iso(timestamp: int | float | None) -> str | None:
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


class StripeProvider:
    name: str = "stripe"

    def __init__(self, secret_key: str | None = None, webhook_secret: str | None = None):
        self._secret_key = secret_key
        self._webhook_secret = webhook_secret

    @property
    def secret_key(self) -> str:
        return self._secret_key if self._secret_key is not None else config.STRIPE_SECRET_KEY

    @property
    def webhook_secret(self) -> str:
        return self._webhook_secret if self._webhook_secret is not None else config.STRIPE_WEBHOOK_SECRET

    @property
    def is_configured(self) -> bool:
        return bool(self.secret_key and self.secret_key.startswith("sk_"))

    def create_checkout_session(
        self,
        organization_id: str,
        organization_name: str,
        plan_id: str,
        seats: int,
        user_email: str,
        user_name: str,
        success_url: str,
        cancel_url: str,
        currency: str = "USD",
    ) -> dict[str, Any]:
        plan = entitlements.get_plan(plan_id)
        unit_amount_cents = int(plan["price_usd"] * 100)

        # Simulation mode for local dev / testing when real keys are absent
        if not self.is_configured:
            session_id = f"mock_cs_{organization_id}_{int(time.time())}"
            mock_checkout_url = f"{success_url}?session_id={session_id}&provider=stripe"
            return {
                "checkout_url": mock_checkout_url,
                "session_id": session_id,
                "is_mock": True,
            }

        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "mode": "subscription",
            "client_reference_id": organization_id,
            "customer_email": user_email,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata[organization_id]": organization_id,
            "metadata[plan_id]": plan_id,
            "metadata[seats]": str(seats),
            "line_items[0][price_data][currency]": currency.lower(),
            "line_items[0][price_data][unit_amount]": str(unit_amount_cents),
            "line_items[0][price_data][product_data][name]": f"AfriSearch AI - {plan['name']}",
            "line_items[0][price_data][product_data][description]": f"{plan['name']} for {organization_name}",
            "line_items[0][price_data][recurring][interval]": "month",
            "line_items[0][quantity]": str(seats),
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{STRIPE_API_BASE}/checkout/sessions", headers=headers, data=data)
            if resp.status_code >= 400:
                logger.error("Stripe create_checkout_session failed: %s %s", resp.status_code, resp.text)
                raise ValueError(f"Stripe checkout initialization failed: {resp.text}")
            res_data = resp.json()
            return {
                "checkout_url": res_data.get("url"),
                "session_id": res_data.get("id"),
                "is_mock": False,
            }

    def create_portal_session(
        self,
        customer_id: str,
        return_url: str,
    ) -> dict[str, Any]:
        if not self.is_configured:
            return {"portal_url": return_url, "is_mock": True}

        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "customer": customer_id,
            "return_url": return_url,
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{STRIPE_API_BASE}/billing_portal/sessions", headers=headers, data=data)
            if resp.status_code >= 400:
                logger.error("Stripe create_portal_session failed: %s %s", resp.status_code, resp.text)
                raise ValueError(f"Stripe portal session failed: {resp.text}")
            res_data = resp.json()
            return {"portal_url": res_data.get("url"), "is_mock": False}

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> bool:
        if not self.webhook_secret or not self.webhook_secret.strip():
            logger.warning("Stripe webhook verification rejected: webhook_secret is missing or empty")
            return False

        sig_header = headers.get("stripe-signature") or headers.get("Stripe-Signature", "")
        if not sig_header or not sig_header.strip():
            logger.warning("Stripe webhook verification rejected: stripe-signature header missing or empty")
            return False

        # Parse t=...,v1=...
        pairs = {}
        for item in sig_header.split(","):
            if "=" in item:
                k, v = item.strip().split("=", 1)
                pairs[k] = v

        timestamp = pairs.get("t")
        expected_sig = pairs.get("v1")
        if not timestamp or not expected_sig:
            return False

        # Verify HMAC
        try:
            signed_payload = f"{timestamp}.".encode("utf-8") + raw_body
            computed = hmac.new(self.webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
            return hmac.compare_digest(computed, expected_sig)
        except Exception as e:
            logger.warning("Stripe signature verification failed: %s", e)
            return False

    def parse_and_process_webhook(
        self,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        if not self.verify_webhook_signature(raw_body, headers):
            raise ValueError("Invalid Stripe webhook signature")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"Malformed webhook JSON: {e}")

        event_id = payload.get("id")
        event_type = payload.get("type")
        if not event_id or not event_type:
            raise ValueError("Webhook missing id or type")

        if db.is_webhook_event_processed(event_id, "stripe"):
            return {"event_id": event_id, "event_type": event_type, "status": "already_processed"}

        data_obj = payload.get("data", {}).get("object", {})

        try:
            if event_type == "checkout.session.completed":
                org_id = data_obj.get("client_reference_id") or data_obj.get("metadata", {}).get("organization_id")
                plan_id = data_obj.get("metadata", {}).get("plan_id", "pro")
                seats = int(data_obj.get("metadata", {}).get("seats", 1))
                customer_id = data_obj.get("customer")
                sub_id = data_obj.get("subscription")

                if org_id:
                    db.update_organization_subscription(
                        org_id=org_id,
                        plan_id=plan_id,
                        status="active",
                        seats_purchased=seats,
                        provider="stripe",
                        provider_customer_id=customer_id,
                        provider_subscription_id=sub_id,
                    )
                    amount_total = data_obj.get("amount_total", 0)
                    currency = (data_obj.get("currency") or "USD").upper()
                    if amount_total > 0:
                        db.record_invoice(
                            organization_id=org_id,
                            provider="stripe",
                            amount_cents=amount_total,
                            currency=currency,
                            status="paid",
                            provider_invoice_id=data_obj.get("invoice") or event_id,
                            paid_at=db.now(),
                        )

            elif event_type == "invoice.paid":
                customer_id = data_obj.get("customer")
                sub_id = data_obj.get("subscription")
                sub = (
                    db.get_subscription_by_provider_sub_id(sub_id)
                    if sub_id
                    else None
                ) or (
                    db.get_subscription_by_customer_id(customer_id)
                    if customer_id
                    else None
                )

                if sub:
                    org_id = sub["organization_id"]
                    lines = data_obj.get("lines", {}).get("data", [])
                    period_end_ts = lines[0].get("period", {}).get("end") if lines else data_obj.get("period_end")
                    period_end_iso = _to_iso(period_end_ts)

                    db.record_invoice(
                        organization_id=org_id,
                        subscription_id=sub["id"],
                        provider="stripe",
                        provider_invoice_id=data_obj.get("id"),
                        amount_cents=data_obj.get("amount_paid", 0),
                        currency=(data_obj.get("currency") or "USD").upper(),
                        status="paid",
                        paid_at=db.now(),
                        hosted_invoice_url=data_obj.get("hosted_invoice_url"),
                        pdf_url=data_obj.get("invoice_pdf"),
                    )
                    if period_end_iso:
                        db.update_organization_subscription(org_id, current_period_end=period_end_iso)

            elif event_type == "customer.subscription.updated":
                sub_id = data_obj.get("id")
                sub = db.get_subscription_by_provider_sub_id(sub_id) if sub_id else None
                if sub:
                    org_id = sub["organization_id"]
                    stripe_status = data_obj.get("status", "active")
                    # Map stripe status
                    status_val = "active"
                    if stripe_status in ("past_due", "unpaid", "canceled", "trialing"):
                        status_val = stripe_status
                    cancel_at_period_end = bool(data_obj.get("cancel_at_period_end", False))
                    period_end_iso = _to_iso(data_obj.get("current_period_end"))
                    db.update_organization_subscription(
                        org_id=org_id,
                        status=status_val,
                        cancel_at_period_end=cancel_at_period_end,
                        current_period_end=period_end_iso,
                    )

            elif event_type == "customer.subscription.deleted":
                sub_id = data_obj.get("id")
                sub = db.get_subscription_by_provider_sub_id(sub_id) if sub_id else None
                if sub:
                    db.update_organization_subscription(
                        org_id=sub["organization_id"],
                        plan_id="free",
                        status="canceled",
                        cancel_at_period_end=False,
                    )

            db.record_webhook_event(event_id, "stripe", event_type, payload, status="processed")
            return {"event_id": event_id, "event_type": event_type, "status": "processed"}

        except Exception as e:
            logger.exception("Error processing Stripe webhook %s: %s", event_id, e)
            db.record_webhook_event(event_id, "stripe", event_type, payload, status="failed", error=str(e))
            raise
