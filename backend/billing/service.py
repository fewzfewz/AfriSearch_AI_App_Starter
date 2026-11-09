"""Billing service orchestrating Stripe, Chapa, webhooks, and invoice management."""
from __future__ import annotations

import logging
from typing import Any

from backend import config, db
from backend.billing.base import PaymentProvider
from backend.billing.chapa_provider import ChapaProvider
from backend.billing.stripe_provider import StripeProvider

logger = logging.getLogger(__name__)

_providers: dict[str, PaymentProvider] = {
    "stripe": StripeProvider(),
    "chapa": ChapaProvider(),
}


def get_provider(provider_name: str) -> PaymentProvider:
    provider = _providers.get(provider_name.lower())
    if not provider:
        raise ValueError(f"Unsupported payment provider: '{provider_name}'. Supported: 'stripe', 'chapa'.")
    return provider


def create_checkout_session(
    organization_id: str,
    organization_name: str,
    plan_id: str,
    seats: int = 1,
    provider: str = "stripe",
    user_email: str = "",
    user_name: str = "",
    return_url: str | None = None,
    currency: str | None = None,
) -> dict[str, Any]:
    pay_provider = get_provider(provider)
    base_url = return_url or config.BILLING_RETURN_URL_BASE
    success_url = f"{base_url}/settings?billing_status=success&plan={plan_id}&provider={provider}"
    cancel_url = f"{base_url}/settings?billing_status=canceled"

    chosen_currency = currency or ("ETB" if provider.lower() == "chapa" else "USD")

    return pay_provider.create_checkout_session(
        organization_id=organization_id,
        organization_name=organization_name,
        plan_id=plan_id,
        seats=seats,
        user_email=user_email,
        user_name=user_name,
        success_url=success_url,
        cancel_url=cancel_url,
        currency=chosen_currency,
    )


def create_portal_session(
    organization_id: str,
    return_url: str | None = None,
) -> dict[str, Any]:
    sub = db.get_organization_subscription(organization_id)
    provider_name = sub.get("provider", "stripe")
    pay_provider = get_provider(provider_name if provider_name in _providers else "stripe")

    base_url = return_url or f"{config.BILLING_RETURN_URL_BASE}/settings"
    customer_id = sub.get("provider_customer_id") or ""
    return pay_provider.create_portal_session(
        customer_id=customer_id,
        return_url=base_url,
    )


def handle_webhook(
    provider_name: str,
    raw_body: bytes,
    headers: dict[str, str],
) -> dict[str, Any]:
    provider = get_provider(provider_name)
    return provider.parse_and_process_webhook(raw_body, headers)


def list_invoices(organization_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return db.list_organization_invoices(organization_id, limit=limit)
