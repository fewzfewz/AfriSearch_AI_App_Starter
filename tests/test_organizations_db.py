"""Tests for SAAS-P0-01 Stage A & Stage B: Database schema, migration, organizations, and invitations."""
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend import config, db


@pytest.fixture
def clean_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    db._initialized.clear()
    return tmp_path / "data"


def test_schema_creation_and_tables(clean_db):
    with db.connect() as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "organizations" in tables
        assert "organization_members" in tables
        assert "organization_invitations" in tables
        assert "workspaces" in tables

        # Verify organization_id column on workspaces
        ws_cols = {row[1] for row in conn.execute("PRAGMA table_info(workspaces)").fetchall()}
        assert "organization_id" in ws_cols


def test_organization_crud(clean_db):
    db.ensure_user("u1", "alice@example.com", "Alice Smith")
    org = db.create_organization("Acme Corp", "u1")
    assert org["name"] == "Acme Corp"
    assert org["owner_id"] == "u1"
    assert org["role"] == "owner"

    fetched = db.get_organization(org["id"], "u1")
    assert fetched is not None
    assert fetched["name"] == "Acme Corp"
    assert fetched["role"] == "owner"

    db.rename_organization(org["id"], "Acme Global")
    updated = db.get_organization(org["id"], "u1")
    assert updated["name"] == "Acme Global"

    # Listing
    orgs = db.list_user_organizations("u1")
    # Alice has her auto-created Personal Organization + Acme Global
    names = {o["name"] for o in orgs}
    assert "Acme Global" in names
    assert "Alice Smith's Organization" in names


def test_atomic_ownership_transfer(clean_db):
    db.ensure_user("owner1", "owner1@example.com", "Owner One")
    db.ensure_user("member1", "member1@example.com", "Member One")

    org = db.create_organization("Transfer Org", "owner1")
    db.add_organization_member(org["id"], "member1", role="member")

    # Transfer ownership
    db.transfer_organization_ownership(org["id"], "owner1", "member1")

    # Check new owner
    org_updated = db.get_organization(org["id"], "member1")
    assert org_updated["owner_id"] == "member1"
    assert org_updated["role"] == "owner"

    # Check old owner role demoted to admin
    old_owner_org = db.get_organization(org["id"], "owner1")
    assert old_owner_org["role"] == "admin"


def test_organization_deletion_safeguards(clean_db):
    db.ensure_user("o1", "o1@example.com", "O1")
    db.ensure_user("m1", "m1@example.com", "M1")

    org = db.create_organization("Multi Org", "o1")
    db.add_organization_member(org["id"], "m1", role="member")

    # Deleting an org with multiple members must raise ValueError
    with pytest.raises(ValueError, match="multiple members"):
        db.delete_organization(org["id"], "o1")

    # Non-owner attempting deletion must raise PermissionError
    with pytest.raises(PermissionError, match="Only the organization owner"):
        db.delete_organization(org["id"], "m1")

    # After removing other member, deletion succeeds
    db.remove_organization_member(org["id"], "m1")
    db.delete_organization(org["id"], "o1")
    assert db.get_organization(org["id"], "o1") is None


def test_cryptographic_invitation_lifecycle(clean_db):
    db.ensure_user("owner", "owner@example.com", "Owner")
    org = db.create_organization("Invite Org", "owner")

    invitation, raw_token = db.create_organization_invitation(
        org["id"], "invitee@example.com", "admin", "owner"
    )
    assert invitation["email"] == "invitee@example.com"
    assert invitation["role"] == "admin"

    # Token should not match hash directly
    assert raw_token != invitation["id"]

    # Retrieve by token
    info = db.get_invitation_by_token(raw_token)
    assert info is not None
    assert info["email"] == "invitee@example.com"
    assert info["organization_name"] == "Invite Org"

    # User registers and accepts invitation
    db.ensure_user("invitee_user", "invitee@example.com", "Invitee User")
    result = db.accept_organization_invitation(raw_token, "invitee_user", "invitee@example.com")
    assert result["organization_id"] == org["id"]
    assert result["role"] == "admin"

    # Membership verified
    members = db.list_organization_members(org["id"])
    member_emails = {m["email"] for m in members}
    assert "invitee@example.com" in member_emails

    # Token cannot be reused (single-use)
    with pytest.raises(ValueError, match="Invalid invitation token"):
        db.accept_organization_invitation(raw_token, "invitee_user", "invitee@example.com")


def test_expired_invitation_rejected(clean_db):
    db.ensure_user("owner", "owner@example.com", "Owner")
    org = db.create_organization("Expire Org", "owner")

    invitation, raw_token = db.create_organization_invitation(
        org["id"], "late@example.com", "member", "owner", expires_days=-1
    )

    db.ensure_user("late_user", "late@example.com", "Late User")
    with pytest.raises(ValueError, match="expired"):
        db.accept_organization_invitation(raw_token, "late_user", "late@example.com")


def test_invitation_wrong_email_rejected(clean_db):
    db.ensure_user("owner", "owner@example.com", "Owner")
    org = db.create_organization("Email Check Org", "owner")

    invitation, raw_token = db.create_organization_invitation(
        org["id"], "target@example.com", "member", "owner"
    )

    db.ensure_user("attacker", "hacker@example.com", "Hacker")
    with pytest.raises(ValueError, match="Invitation was sent to target@example.com"):
        db.accept_organization_invitation(raw_token, "attacker", "hacker@example.com")


def test_legacy_data_migration_and_recovery(clean_db):
    # Simulate a pre-organization database state
    db_path = clean_db / "afrisearch.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    raw_conn = sqlite3.connect(db_path)
    raw_conn.executescript("""
    CREATE TABLE users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE workspaces (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE members (
        workspace_id TEXT NOT NULL REFERENCES workspaces (id),
        user_id TEXT NOT NULL REFERENCES users (id),
        role TEXT NOT NULL,
        added_at TEXT NOT NULL,
        PRIMARY KEY (workspace_id, user_id)
    );
    CREATE TABLE chats (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    INSERT INTO users VALUES ('legacy-u1', 'legacy@example.com', 'Legacy User', '2025-01-01T00:00:00');
    INSERT INTO workspaces VALUES ('ws-owned', 'Owned Workspace', '2025-01-01T00:00:00');
    INSERT INTO members VALUES ('ws-owned', 'legacy-u1', 'owner', '2025-01-01T00:00:00');
    INSERT INTO workspaces VALUES ('ws-orphan', 'Orphaned Workspace', '2025-01-01T00:00:00');
    """)
    raw_conn.close()

    # Now open with db.connect(), triggering migrate()
    with db.connect() as conn:
        ws_owned = conn.execute("SELECT organization_id FROM workspaces WHERE id = 'ws-owned'").fetchone()
        assert ws_owned["organization_id"] is not None
        assert ws_owned["organization_id"] != db.SYSTEM_RECOVERY_ORG_ID

        # Owner has Personal Organization created
        org = conn.execute("SELECT name, owner_id FROM organizations WHERE id = ?", (ws_owned["organization_id"],)).fetchone()
        assert org["name"] == "Legacy User's Organization"
        assert org["owner_id"] == "legacy-u1"

        # Orphan workspace mapped to System Recovery Organization
        ws_orphan = conn.execute("SELECT organization_id FROM workspaces WHERE id = 'ws-orphan'").fetchone()
        assert ws_orphan["organization_id"] == db.SYSTEM_RECOVERY_ORG_ID

    # System Recovery Organization is invisible to normal users
    assert db.get_organization(db.SYSTEM_RECOVERY_ORG_ID, "legacy-u1") is None
    orgs = db.list_user_organizations("legacy-u1")
    assert all(o["id"] != db.SYSTEM_RECOVERY_ORG_ID for o in orgs)

    # Test explicit recovery of orphan workspace to legacy user's organization
    db.recover_workspace("ws-orphan", ws_owned["organization_id"])
    with db.connect() as conn:
        ws_recovered = conn.execute("SELECT organization_id FROM workspaces WHERE id = 'ws-orphan'").fetchone()
        assert ws_recovered["organization_id"] == ws_owned["organization_id"]


def test_migration_is_idempotent(clean_db):
    db.ensure_user("u1", "u1@example.com", "U1")
    ws = db.create_workspace("WS1", "u1")

    with db.connect() as conn:
        org_count_1 = conn.execute("SELECT count(*) FROM organizations").fetchone()[0]
        ws_count_1 = conn.execute("SELECT count(*) FROM workspaces").fetchone()[0]

        # Re-run migrate
        db.migrate(conn)

        org_count_2 = conn.execute("SELECT count(*) FROM organizations").fetchone()[0]
        ws_count_2 = conn.execute("SELECT count(*) FROM workspaces").fetchone()[0]

        assert org_count_1 == org_count_2
        assert ws_count_1 == ws_count_2
