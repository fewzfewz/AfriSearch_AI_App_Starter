"""Chapa payment provider for African payment rails (Telebirr, CBE Birr, ETB cards)."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from backend import config, db, entitlements

logger = logging.getLogger(__name__)


class ChapaProvider:
    name: str = "chapa"

    def __init__(self, secret_key: str | None = None, webhook_secret: str | None = None, api_url: str | None = None):
        self._secret_key = secret_key
        self._webhook_secret = webhook_secret
        self._api_url = api_url

    @property
    def secret_key(self) -> str:
        return self._secret_key if self._secret_key is not None else config.CHAPA_SECRET_KEY

    @property
    def webhook_secret(self) -> str:
        if self._webhook_secret is not None:
            return self._webhook_secret
        return config.CHAPA_WEBHOOK_SECRET or self.secret_key

    @property
    def api_url(self) -> str:
        return self._api_url if self._api_url is not None else config.CHAPA_API_URL

    @property
    def is_configured(self) -> bool:
        return bool(self.secret_key and self.secret_key.startswith("CHASECK_"))

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
        currency: str = "ETB",
    ) -> dict[str, Any]:
        plan = entitlements.get_plan(plan_id)
        unit_amount_etb = plan.get("price_etb", 3500)
        total_amount_etb = unit_amount_etb * seats
        tx_ref = f"afrisearch_{organization_id[:8]}_{plan_id}_{int(time.time())}"

        # Simulation mode for local dev / testing when real keys are absent
        if not self.is_configured:
            mock_checkout_url = f"{success_url}?tx_ref={tx_ref}&provider=chapa"
            return {
                "checkout_url": mock_checkout_url,
                "session_id": tx_ref,
                "is_mock": True,
            }

        name_parts = (user_name or "AfriSearch User").strip().split(None, 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else "User"

        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }
        body = {
            "amount": str(total_amount_etb),
            "currency": currency.upper(),
            "email": user_email or "billing@afrisearch.ai",
            "first_name": first_name,
            "last_name": last_name,
            "tx_ref": tx_ref,
            "callback_url": f"{config.APP_URL}/api/webhooks/chapa",
            "return_url": success_url,
            "customization": {
                "title": f"AfriSearch AI - {plan['name']}",
                "description": f"Subscription for {organization_name} ({seats} seat(s))",
            },
            "meta": {
                "organization_id": organization_id,
                "plan_id": plan_id,
                "seats": seats,
            },
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{self.api_url}/transaction/initialize", headers=headers, json=body)
            if resp.status_code >= 400:
                logger.error("Chapa transaction initialization failed: %s %s", resp.status_code, resp.text)
                raise ValueError(f"Chapa checkout initialization failed: {resp.text}")
            res_data = resp.json()
            checkout_url = res_data.get("data", {}).get("checkout_url")
            return {
                "checkout_url": checkout_url,
                "session_id": tx_ref,
                "is_mock": False,
            }

    def create_portal_session(
        self,
        customer_id: str,
        return_url: str,
    ) -> dict[str, Any]:
        # Chapa has no hosted customer billing portal; redirect directly to app settings
        return {"portal_url": return_url, "is_mock": True}

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> bool:
        if not self.webhook_secret or not self.webhook_secret.strip():
            logger.warning("Chapa webhook verification rejected: webhook_secret is missing or empty")
            return False

        sig_header = headers.get("x-chapa-signature") or headers.get("chapa-signature") or headers.get("Chapa-Signature", "")
        if not sig_header or not sig_header.strip():
            logger.warning("Chapa webhook verification rejected: chapa-signature header missing or empty")
            return False

        try:
            computed = hmac.new(self.webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
            return hmac.compare_digest(computed, sig_header.strip())
        except Exception as e:
            logger.warning("Chapa signature verification failed: %s", e)
            return False

    def parse_and_process_webhook(
        self,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        if not self.verify_webhook_signature(raw_body, headers):
            raise ValueError("Invalid Chapa webhook signature")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"Malformed Chapa webhook JSON: {e}")

        tx_ref = payload.get("tx_ref") or payload.get("data", {}).get("tx_ref")
        if not tx_ref:
            raise ValueError("Chapa webhook missing tx_ref")

        event_id = f"chapa_{tx_ref}"
        event_type = payload.get("event") or "charge.success"

        if db.is_webhook_event_processed(event_id, "chapa"):
            return {"event_id": event_id, "event_type": event_type, "status": "already_processed"}

        status = payload.get("status") or payload.get("data", {}).get("status")

        try:
            if status == "success":
                meta = payload.get("meta") or payload.get("data", {}).get("meta") or {}
                org_id = meta.get("organization_id")
                plan_id = meta.get("plan_id")
                seats = int(meta.get("seats", 1))

                # If meta was not preserved in callback, parse tx_ref: afrisearch_{org_prefix}_{plan}_{ts}
                if not org_id and tx_ref.startswith("afrisearch_"):
                    parts = tx_ref.split("_")
                    if len(parts) >= 3:
                        plan_id = parts[2]

                amount = payload.get("amount") or payload.get("data", {}).get("amount", 0)
                currency = payload.get("currency") or payload.get("data", {}).get("currency", "ETB")

                # If org_id is still unknown, search subscription by provider_subscription_id
                if not org_id:
                    existing = db.get_subscription_by_provider_sub_id(tx_ref)
                    if existing:
                        org_id = existing["organization_id"]

                if org_id:
                    now_dt = datetime.now(timezone.utc)
                    period_end = (now_dt + timedelta(days=30)).isoformat()
                    db.update_organization_subscription(
                        org_id=org_id,
                        plan_id=plan_id or "pro",
                        status="active",
                        seats_purchased=seats,
                        provider="chapa",
                        provider_subscription_id=tx_ref,
                        current_period_end=period_end,
                    )
                    amount_cents = int(float(amount) * 100)
                    db.record_invoice(
                        organization_id=org_id,
                        provider="chapa",
                        amount_cents=amount_cents,
                        currency=currency.upper(),
                        status="paid",
                        provider_invoice_id=tx_ref,
                        paid_at=db.now(),
                    )

            db.record_webhook_event(event_id, "chapa", event_type, payload, status="processed")
            return {"event_id": event_id, "event_type": event_type, "status": "processed"}

        except Exception as e:
            logger.exception("Error processing Chapa webhook %s: %s", event_id, e)
            db.record_webhook_event(event_id, "chapa", event_type, payload, status="failed", error=str(e))
            raise
