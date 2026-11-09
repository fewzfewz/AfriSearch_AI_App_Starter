"""Tests for SAAS-P0-01 Stage D: Organization REST API endpoints."""
import time
import jwt
import pytest

from backend import config, db

SECRET = "test-secret-at-least-32-bytes-long!!"


def token(sub="user-1", email="user1@example.com", secret=SECRET, audience="authenticated", expires_in=3600,
          algorithm="HS256", **extra):
    claims = {
        "sub": sub,
        "email": email,
        "aud": audience,
        "exp": int(time.time()) + expires_in,
        "user_metadata": {"full_name": email.split("@")[0].title()},
        **extra,
    }
    return jwt.encode(claims, secret, algorithm=algorithm)


def as_user(**kwargs):
    return {"Authorization": f"Bearer {token(**kwargs)}"}


@pytest.fixture
def supabase(app_env, monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "supabase")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", SECRET)


def test_list_and_create_organizations(client, supabase):
    amina = as_user(sub="amina", email="amina@example.com")
    res = client.get("/organizations", headers=amina)
    assert res.status_code == 200
    orgs = res.json()["organizations"]
    assert len(orgs) == 1
    assert orgs[0]["name"] == "Amina's Organization"

    create_res = client.post("/organizations", headers=amina, json={"name": "Research Institute"})
    assert create_res.status_code == 201
    created = create_res.json()
    assert created["name"] == "Research Institute"
    assert created["owner_id"] == "amina"
    assert created["role"] == "owner"

    list_again = client.get("/organizations", headers=amina).json()["organizations"]
    assert len(list_again) == 2
    names = {o["name"] for o in list_again}
    assert "Research Institute" in names


def test_get_and_rename_organization(client, supabase):
    amina = as_user(sub="amina", email="amina@example.com")
    juma = as_user(sub="juma", email="juma@example.com")

    org = client.post("/organizations", headers=amina, json={"name": "Original Name"}).json()
    org_id = org["id"]

    # Get organization details
    get_res = client.get(f"/organizations/{org_id}", headers=amina)
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Original Name"

    # Non-member getting organization gets 404
    assert client.get(f"/organizations/{org_id}", headers=juma).status_code == 404

    # Non-member renaming gets 404
    assert client.patch(f"/organizations/{org_id}", headers=juma, json={"name": "Hacked"}).status_code == 404

    # Owner renames
    patch_res = client.patch(f"/organizations/{org_id}", headers=amina, json={"name": "Renamed Institute"})
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Renamed Institute"


def test_delete_organization_safeguards(client, supabase):
    amina = as_user(sub="amina", email="amina@example.com")
    juma = as_user(sub="juma", email="juma@example.com")

    org = client.post("/organizations", headers=amina, json={"name": "Delete Test Org"}).json()
    org_id = org["id"]

    # Add Juma as a member
    db.ensure_user("juma", "juma@example.com", "Juma")
    db.add_organization_member(org_id, "juma", role="member")

    # Juma (non-owner) attempting to delete gets 403
    assert client.delete(f"/organizations/{org_id}", headers=juma).status_code == 403

    # Amina attempting to delete with multiple members gets 409 Conflict (ADR-02)
    conflict_res = client.delete(f"/organizations/{org_id}", headers=amina)
    assert conflict_res.status_code == 409
    assert "multiple members" in conflict_res.json()["detail"]

    # Remove Juma
    client.delete(f"/organizations/{org_id}/members/juma", headers=amina)

    # Now deletion succeeds
    del_res = client.delete(f"/organizations/{org_id}", headers=amina)
    assert del_res.status_code == 200
    assert client.get(f"/organizations/{org_id}", headers=amina).status_code == 404


def test_transfer_ownership(client, supabase):
    amina = as_user(sub="amina", email="amina@example.com")
    juma = as_user(sub="juma", email="juma@example.com")

    org = client.post("/organizations", headers=amina, json={"name": "Transfer Org"}).json()
    org_id = org["id"]

    db.ensure_user("juma", "juma@example.com", "Juma")
    db.add_organization_member(org_id, "juma", role="member")

    # Juma cannot transfer ownership (not owner)
    assert client.post(
        f"/organizations/{org_id}/transfer-ownership",
        headers=juma,
        json={"new_owner_id": "juma"},
    ).status_code == 403

    # Amina transfers ownership to Juma
    transfer_res = client.post(
        f"/organizations/{org_id}/transfer-ownership",
        headers=amina,
        json={"new_owner_id": "juma"},
    )
    assert transfer_res.status_code == 200

    # Juma is now owner
    juma_org = client.get(f"/organizations/{org_id}", headers=juma).json()
    assert juma_org["owner_id"] == "juma"
    assert juma_org["role"] == "owner"

    # Amina is now admin
    amina_org = client.get(f"/organizations/{org_id}", headers=amina).json()
    assert amina_org["role"] == "admin"


def test_organization_members_endpoints(client, supabase):
    amina = as_user(sub="amina", email="amina@example.com")
    juma = as_user(sub="juma", email="juma@example.com")

    org = client.post("/organizations", headers=amina, json={"name": "Members Org"}).json()
    org_id = org["id"]

    db.ensure_user("juma", "juma@example.com", "Juma")
    db.add_organization_member(org_id, "juma", role="member")

    # List members
    members_res = client.get(f"/organizations/{org_id}/members", headers=amina)
    assert members_res.status_code == 200
    members = members_res.json()["members"]
    assert len(members) == 2
    emails = {m["email"]: m["role"] for m in members}
    assert emails["amina@example.com"] == "owner"
    assert emails["juma@example.com"] == "member"

    # Amina (owner) cannot leave without transferring ownership
    leave_owner = client.delete(f"/organizations/{org_id}/members/amina", headers=amina)
    assert leave_owner.status_code == 400

    # Juma (member) leaves
    leave_juma = client.delete(f"/organizations/{org_id}/members/juma", headers=juma)
    assert leave_juma.status_code == 200
    assert len(leave_juma.json()["members"]) == 1


def test_invitation_lifecycle_api(client, supabase):
    amina = as_user(sub="amina", email="amina@example.com")
    guest = as_user(sub="guest", email="guest@example.com")

    org = client.post("/organizations", headers=amina, json={"name": "Invite API Org"}).json()
    org_id = org["id"]

    # Send invitation
    inv_res = client.post(
        f"/organizations/{org_id}/invitations",
        headers=amina,
        json={"email": "guest@example.com", "role": "admin"},
    )
    assert inv_res.status_code == 201
    data = inv_res.json()
    assert data["email"] == "guest@example.com"
    assert data["role"] == "admin"
    raw_token = data["token"]
    assert raw_token

    # List invitations
    list_inv = client.get(f"/organizations/{org_id}/invitations", headers=amina)
    assert list_inv.status_code == 200
    assert len(list_inv.json()["invitations"]) == 1

    # Wrong user tries to accept
    hacker = as_user(sub="hacker", email="hacker@example.com")
    wrong_accept = client.post(
        "/organizations/invitations/accept",
        headers=hacker,
        json={"token": raw_token},
    )
    assert wrong_accept.status_code == 403

    # Correct user accepts invitation
    accept_res = client.post(
        "/organizations/invitations/accept",
        headers=guest,
        json={"token": raw_token},
    )
    assert accept_res.status_code == 200
    assert accept_res.json()["organization_id"] == org_id
    assert accept_res.json()["role"] == "admin"

    # Verify guest is now an admin member
    guest_org = client.get(f"/organizations/{org_id}", headers=guest)
    assert guest_org.status_code == 200
    assert guest_org.json()["role"] == "admin"

    # Token cannot be reused (pruned)
    reuse_res = client.post(
        "/organizations/invitations/accept",
        headers=guest,
        json={"token": raw_token},
    )
    assert reuse_res.status_code == 404


def test_cancel_invitation_api(client, supabase):
    amina = as_user(sub="amina", email="amina@example.com")
    org = client.post("/organizations", headers=amina, json={"name": "Cancel Test Org"}).json()
    org_id = org["id"]

    client.post(
        f"/organizations/{org_id}/invitations",
        headers=amina,
        json={"email": "cancelme@example.com", "role": "member"},
    )
    assert len(client.get(f"/organizations/{org_id}/invitations", headers=amina).json()["invitations"]) == 1

    cancel_res = client.delete(f"/organizations/{org_id}/invitations/cancelme@example.com", headers=amina)
    assert cancel_res.status_code == 200
    assert len(cancel_res.json()["invitations"]) == 0
