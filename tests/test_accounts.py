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

    client.get("/me", headers=guest)  # guest has an account
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


def test_export_contains_my_data_and_documents(client, app_env, fake_model):
    import io
    import json
    import zipfile

    from conftest import upload as upload_files

    upload_files(client, ("guide.txt", SOLAR_GUIDE))
    client.post("/documents/index")
    client.post("/ask", json={"question": "How often should panels be cleaned?", "save": True})
    response = client.get("/me/export")
    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    data = json.loads(archive.read("afrisearch-data.json"))
    assert data["chats"][0]["messages"][0]["content"] == "How often should panels be cleaned?"
    assert [w["name"] for w in data["workspaces"]] == ["My documents"]
    documents = [n for n in archive.namelist() if n.startswith("documents/My documents/")]
    assert len(documents) == 1 and documents[0].endswith("_guide.txt")
    assert archive.read(documents[0]) == SOLAR_GUIDE


def test_deleting_an_account_removes_its_data(client, supabase, fake_model):
    owner, guest = as_user(sub="owner", email="owner@example.org"), as_user(sub="guest", email="guest@example.org")
    owned = client.get("/me", headers=owner).json()["workspaces"][0]["id"]
    guest_space = client.get("/me", headers=guest).json()["workspaces"][0]["id"]
    client.post(f"/workspaces/{guest_space}/members", headers=guest, json={"email": "owner@example.org"})
    client.post("/documents/upload", headers=owner, files=[("files", ("g.txt", SOLAR_GUIDE, "text/plain"))])

    wrong = client.request("DELETE", "/me", headers=owner, json={"confirm": "someone@else.org"})
    assert wrong.status_code == 400
    deleted = client.request("DELETE", "/me", headers=owner, json={"confirm": "OWNER@example.org"})
    assert deleted.status_code == 200
    assert "sign-in account still exists" in deleted.json()["message"]  # no admin key configured

    from backend import config, db, store as store_module
    assert not store_module.workspace_dir(owned).exists()
    assert db.get_workspace(owned, "owner") is None
    assert [m["id"] for m in client.get(f"/workspaces/{guest_space}/members", headers=guest).json()["members"]] == ["guest"]
    assert client.get("/me", headers=owner).json()["workspaces"][0]["id"] != owned  # signs in fresh


def test_people_without_an_account_are_invited_and_join_on_sign_in(client, supabase):
    owner = as_user(sub="owner", email="owner@example.org")
    workspace = client.get("/me", headers=owner).json()["workspaces"][0]["id"]
    invited = client.post(f"/workspaces/{workspace}/members", headers=owner, json={"email": "New.Person@Example.org"}).json()
    assert "joins this workspace when they sign up" in invited["message"]
    assert [i["email"] for i in invited["invitations"]] == ["new.person@example.org"]
    assert [m["email"] for m in invited["members"]] == ["owner@example.org"]

    newcomer = as_user(sub="new", email="new.person@example.org")
    workspaces = client.get("/me", headers=newcomer).json()["workspaces"]
    assert workspace in [w["id"] for w in workspaces]  # joined on first sign-in
    team = client.get(f"/workspaces/{workspace}/members", headers=owner).json()
    assert team["invitations"] == []
    assert {m["email"] for m in team["members"]} == {"owner@example.org", "new.person@example.org"}


def test_owners_can_cancel_invitations(client, supabase):
    owner = as_user(sub="owner", email="owner@example.org")
    workspace = client.get("/me", headers=owner).json()["workspaces"][0]["id"]
    client.post(f"/workspaces/{workspace}/members", headers=owner, json={"email": "late@example.org"})
    assert client.delete(f"/workspaces/{workspace}/invitations/late@example.org", headers=owner).json()["invitations"] == []
    later = as_user(sub="late", email="late@example.org")
    assert workspace not in [w["id"] for w in client.get("/me", headers=later).json()["workspaces"]]
