"""Abstract interface and data structures for payment gateway providers."""
from __future__ import annotations

from typing import Any, Protocol


class PaymentProvider(Protocol):
    """Protocol implemented by Stripe, Chapa, and mock billing providers."""

    name: str

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
        """Create a hosted checkout session and return checkout_url and session_id."""
        ...

    def create_portal_session(
        self,
        customer_id: str,
        return_url: str,
    ) -> dict[str, Any]:
        """Create a billing management portal session and return portal_url."""
        ...

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> bool:
        """Verify the cryptographic signature of an incoming webhook."""
        ...

    def parse_and_process_webhook(
        self,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Parse raw webhook bytes, verify, update database state, and return processing summary."""
        ...
