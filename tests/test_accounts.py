"""Sign-in with Supabase tokens, workspaces, members, and keeping users' data apart."""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend import auth, config
from conftest import SOLAR_GUIDE, upload

SECRET = "test-secret-at-least-32-bytes-long!!"


def token(sub="user-1", email="amina@example.org", secret=SECRET, audience="authenticated", expires_in=3600,
          algorithm="HS256", **extra):
    claims = {"sub": sub, "email": email, "aud": audience, "exp": int(time.time()) + expires_in,
              "user_metadata": {"full_name": email.split("@")[0].title()}, **extra}
    return jwt.encode(claims, secret, algorithm=algorithm)


def as_user(**kwargs):
    return {"Authorization": f"Bearer {token(**kwargs)}"}


@pytest.fixture
def supabase(app_env, monkeypatch):
    """Sign-in on, with the legacy shared-secret token signing."""
    monkeypatch.setattr(config, "AUTH_MODE", "supabase")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", SECRET)


def test_local_mode_needs_no_sign_in(client):
    body = client.get("/me").json()
    assert body["user"]["id"] == "local"
    assert [w["name"] for w in body["workspaces"]] == ["My documents"]


def test_public_config_tells_the_web_app_how_to_sign_in(client, supabase, monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "public-anon-key")
    monkeypatch.setattr(config, "AUTH_PROVIDERS", ["google"])
    body = client.get("/config").json()  # no token needed
    assert body["auth"] == "supabase"
    assert body["supabase_url"] == "https://project.supabase.co"
    assert body["supabase_anon_key"] == "public-anon-key"
    assert body["auth_providers"] == ["google"]
    assert "pdf" in body["file_types"]


def test_requests_need_a_valid_token(client, supabase):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.get("/me", headers=as_user(secret="another-secret-that-is-32-bytes!!")).status_code == 401
    assert client.get("/me", headers=as_user(audience="anon")).status_code == 401
    expired = client.get("/me", headers=as_user(expires_in=-10))
    assert expired.status_code == 401
    assert "expired" in expired.json()["detail"]

    body = client.get("/me", headers=as_user()).json()
    assert body["user"] == {"id": "user-1", "email": "amina@example.org", "name": "Amina"}


def test_tokens_signed_with_published_keys(client, supabase, monkeypatch):
    """Newer Supabase projects sign with asymmetric keys published as JWKS."""
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", "")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class FakeJwks:
        def get_signing_key_from_jwt(self, _token):
            return jwt.PyJWK.from_dict(
                {**jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True), "alg": "RS256"})

    monkeypatch.setattr(auth, "_jwks", lambda: FakeJwks())
    good = token(secret=private_key, algorithm="RS256")
    assert client.get("/me", headers={"Authorization": f"Bearer {good}"}).status_code == 200
    forged = token(secret=rsa.generate_private_key(public_exponent=65537, key_size=2048), algorithm="RS256")
    assert client.get("/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_users_never_see_each_others_documents(client, supabase):
    amina, juma = as_user(sub="amina"), as_user(sub="juma", email="juma@example.org")
    upload_response = client.post("/documents/upload", headers=amina,
                                  files=[("files", ("guide.txt", SOLAR_GUIDE, "text/plain"))])
    assert upload_response.status_code == 200
    client.post("/documents/index", headers=amina)
    assert len(client.get("/documents", headers=amina).json()["documents"]) == 1
    assert client.get("/documents", headers=juma).json()["documents"] == []

    aminas_workspace = client.get("/me", headers=amina).json()["workspaces"][0]["id"]
    assert client.get("/documents", headers={**juma, "X-Workspace-Id": aminas_workspace}).status_code == 404


def test_workspaces_can_be_created_renamed_and_deleted(client, app_env):
    upload(client, ("guide.txt", SOLAR_GUIDE))
    client.post("/documents/index")
    farm = client.post("/workspaces", json={"name": "Farm"}).json()
    assert farm["role"] == "owner"
    in_farm = {"X-Workspace-Id": farm["id"]}
    assert client.get("/documents", headers=in_farm).json()["documents"] == []  # separate documents

    assert client.patch(f"/workspaces/{farm['id']}", json={"name": "Farm 2026"}).json()["name"] == "Farm 2026"
    upload(client, ("other.txt", b"Batteries last about ten years."))  # into the first workspace
    assert client.delete(f"/workspaces/{farm['id']}").status_code == 200
    assert [w["name"] for w in client.get("/workspaces").json()["workspaces"]] == ["My documents"]
    only = client.get("/workspaces").json()["workspaces"][0]["id"]
    assert client.delete(f"/workspaces/{only}").status_code == 400  # can't delete the last one


def test_members_share_a_workspace(client, supabase):
    owner, guest = as_user(sub="owner", email="owner@example.org"), as_user(sub="guest", email="guest@example.org")
    workspace = client.get("/me", headers=owner).json()["workspaces"][0]["id"]

    missing = client.post(f"/workspaces/{workspace}/members", headers=owner, json={"email": "guest@example.org"})
    assert missing.status_code == 404  # guest hasn't signed up yet
    client.get("/me", headers=guest)  # guest signs in once
    members = client.post(f"/workspaces/{workspace}/members", headers=owner,
                          json={"email": "GUEST@example.org"}).json()["members"]
    assert {m["email"]: m["role"] for m in members} == {"owner@example.org": "owner", "guest@example.org": "member"}

    in_shared = {**guest, "X-Workspace-Id": workspace}
    assert client.get("/documents", headers=in_shared).status_code == 200
    assert client.patch(f"/workspaces/{workspace}", headers=guest, json={"name": "Mine"}).status_code == 403
    assert client.post(f"/workspaces/{workspace}/members", headers=guest,
                       json={"email": "owner@example.org"}).status_code == 403

    client.delete(f"/workspaces/{workspace}/members/guest", headers=guest)  # guest leaves
    assert client.get("/documents", headers=in_shared).status_code == 404
