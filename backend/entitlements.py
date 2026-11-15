"""Subscription plans and entitlement enforcement."""
from __future__ import annotations

from typing import Any
from fastapi import HTTPException
from backend import db

PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "id": "free",
        "name": "Free Tier",
        "price_usd": 0,
        "price_etb": 0,
        "max_seats": 5,
        "max_workspaces": 3,
        "max_storage_bytes": 100 * 1024 * 1024,  # 100 MB
        "max_documents": 50,
        "max_queries_per_month": 100,
        "allowed_models": [
            "gemini",
            "qwen",
            "gpt",
            "local",
            "fake/echo",
            "canned",
        ],
        "ocr_enabled": True,
        "api_access": False,
    },
    "pro": {
        "id": "pro",
        "name": "Pro Tier",
        "price_usd": 29,
        "price_etb": 3500,
        "max_seats": 15,
        "max_workspaces": 10,
        "max_storage_bytes": 10 * 1024 * 1024 * 1024,  # 10 GB
        "max_documents": 500,
        "max_queries_per_month": 1500,
        "allowed_models": [
            "claude-3-5-sonnet",
            "claude-sonnet",
            "gpt-4o",
            "gemini-flash",
            "gemini-pro",
            "qwen-small",
            "local/qwen2.5-0.5b",
            "fake/echo",
            "canned",
        ],
        "ocr_enabled": True,
        "api_access": True,
    },
    "business": {
        "id": "business",
        "name": "Business Tier",
        "price_usd": 149,
        "price_etb": 18000,
        "max_seats": 50,
        "max_workspaces": 999999,
        "max_storage_bytes": 100 * 1024 * 1024 * 1024,  # 100 GB
        "max_documents": 10000,
        "max_queries_per_month": 10000,
        "allowed_models": ["*"],
        "ocr_enabled": True,
        "api_access": True,
    },
    "enterprise": {
        "id": "enterprise",
        "name": "Enterprise Tier",
        "price_usd": 500,
        "price_etb": 60000,
        "max_seats": 999999,
        "max_workspaces": 999999,
        "max_storage_bytes": 1024 * 1024 * 1024 * 1024,  # 1 TB
        "max_documents": 100000,
        "max_queries_per_month": 100000,
        "allowed_models": ["*"],
        "ocr_enabled": True,
        "api_access": True,
    },
}


def get_plan(plan_id: str) -> dict[str, Any]:
    return PLANS.get(plan_id, PLANS["free"])


def get_organization_plan(org_id: str) -> dict[str, Any]:
    sub = db.get_organization_subscription(org_id)
    plan_id = sub.get("plan_id", "free")
    return get_plan(plan_id)


def check_can_create_workspace(org_id: str) -> None:
    plan = get_organization_plan(org_id)
    summary = db.get_organization_usage_summary(org_id)
    if summary["workspace_count"] >= plan["max_workspaces"]:
        raise HTTPException(
            status_code=402,
            detail=f"Workspace limit reached ({plan['max_workspaces']} workspaces) for the {plan['name']}. Upgrade plan to create more workspaces.",
            headers={"X-Upgrade-Required": "workspaces"},
        )


def check_can_add_member(org_id: str) -> None:
    plan = get_organization_plan(org_id)
    summary = db.get_organization_usage_summary(org_id)
    if summary["seats_used"] >= plan["max_seats"]:
        raise HTTPException(
            status_code=402,
            detail=f"Seat limit reached ({plan['max_seats']} members) for the {plan['name']}. Upgrade plan to invite more members.",
            headers={"X-Upgrade-Required": "seats"},
        )


def check_can_upload(org_id: str, new_bytes: int, file_count: int = 1) -> None:
    plan = get_organization_plan(org_id)
    summary = db.get_organization_usage_summary(org_id)
    if summary["storage_bytes"] + new_bytes > plan["max_storage_bytes"]:
        max_mb = plan["max_storage_bytes"] // (1024 * 1024)
        raise HTTPException(
            status_code=402,
            detail=f"Organization storage quota exceeded ({max_mb} MB) for the {plan['name']}. Upgrade plan to upload more files.",
            headers={"X-Upgrade-Required": "storage"},
        )
    if summary["document_count"] + file_count > plan["max_documents"]:
        raise HTTPException(
            status_code=402,
            detail=f"Organization document limit reached ({plan['max_documents']} documents) for the {plan['name']}. Upgrade plan to upload more documents.",
            headers={"X-Upgrade-Required": "documents"},
        )


def check_can_ask(org_id: str, model_id: str | None = None, kind: str | None = None) -> None:
    plan = get_organization_plan(org_id)

    # 1. Model accessibility check
    if model_id and plan["allowed_models"] != ["*"]:
        # Local models and test fakes are not gated by cloud subscription tiers
        if kind == "local" or model_id.startswith("fake"):
            pass
        else:
            byok_keys = db.get_all_raw_organization_ai_keys(org_id)
            has_byok = any(
                p in model_id.lower()
                or (p in ("openai", "chatgpt") and "gpt" in model_id.lower())
                or (p in ("google", "gemini") and "gemini" in model_id.lower())
                or (p in ("anthropic", "claude") and "claude" in model_id.lower())
                for p in byok_keys.keys()
            )
            if not has_byok:
                allowed = model_id in plan["allowed_models"] or any(model_id.startswith(m) for m in plan["allowed_models"])
                if not allowed:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Model '{model_id}' is not available on the {plan['name']}. Upgrade to Pro or Business to use this model.",
                        headers={"X-Upgrade-Required": "model"},
                    )

    # 2. Monthly AI query quota check
    summary = db.get_organization_usage_summary(org_id)
    if summary["questions_count"] >= plan["max_queries_per_month"]:
        raise HTTPException(
            status_code=402,
            detail=f"Monthly AI question quota reached ({plan['max_queries_per_month']} questions) for the {plan['name']}. Upgrade plan to continue asking questions.",
            headers={"X-Upgrade-Required": "queries"},
        )


def check_can_use_api(org_id: str) -> None:
    plan = get_organization_plan(org_id)
    if not plan.get("api_access", False):
        raise HTTPException(
            status_code=402,
            detail=f"Developer API key access is not available on the {plan['name']}. Upgrade to Pro or Business to generate API keys and integrate with your systems.",
            headers={"X-Upgrade-Required": "api_access"},
        )
