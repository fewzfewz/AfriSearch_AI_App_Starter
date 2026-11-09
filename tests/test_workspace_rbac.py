import pytest
from backend import db
from test_accounts import as_user

SOLAR_GUIDE = (
    b"Solar Panel Maintenance Guide. Solar panels should be cleaned every month to remove dust. "
    b"Dust can lower output by up to 25 percent."
)


@pytest.fixture
def rbac_setup(client, app_env, monkeypatch):
    """Setup workspace with owner, admin, member, and viewer users."""
    from backend import config
    from test_accounts import SECRET

    monkeypatch.setattr(config, "AUTH_MODE", "supabase")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", SECRET)

    owner = as_user(sub="owner", email="owner@example.org")
    admin = as_user(sub="admin", email="admin@example.org")
    member = as_user(sub="member", email="member@example.org")
    viewer = as_user(sub="viewer", email="viewer@example.org")

    # Ensure all users have signed in
    client.get("/me", headers=owner)
    client.get("/me", headers=admin)
    client.get("/me", headers=member)
    client.get("/me", headers=viewer)

    # Get owner workspace
    ws_id = client.get("/me", headers=owner).json()["workspaces"][0]["id"]

    # Add admin, member, viewer
    client.post(f"/workspaces/{ws_id}/members", headers=owner, json={"email": "admin@example.org", "role": "admin"})
    client.post(f"/workspaces/{ws_id}/members", headers=owner, json={"email": "member@example.org", "role": "member"})
    client.post(f"/workspaces/{ws_id}/members", headers=owner, json={"email": "viewer@example.org", "role": "viewer"})

    return {
        "ws_id": ws_id,
        "owner": {**owner, "X-Workspace-Id": ws_id},
        "admin": {**admin, "X-Workspace-Id": ws_id},
        "member": {**member, "X-Workspace-Id": ws_id},
        "viewer": {**viewer, "X-Workspace-Id": ws_id},
    }


def test_rbac_member_roles_in_team_listing(client, rbac_setup):
    ws_id = rbac_setup["ws_id"]
    res = client.get(f"/workspaces/{ws_id}/members", headers=rbac_setup["owner"])
    assert res.status_code == 200
    roles = {m["email"]: m["role"] for m in res.json()["members"]}
    assert roles["owner@example.org"] == "owner"
    assert roles["admin@example.org"] == "admin"
    assert roles["member@example.org"] == "member"
    assert roles["viewer@example.org"] == "viewer"


def test_admin_can_upload_and_index(client, rbac_setup):
    admin_hdr = rbac_setup["admin"]
    res = client.post("/documents/upload", headers=admin_hdr, files=[("files", ("solar.txt", SOLAR_GUIDE, "text/plain"))])
    assert res.status_code == 200
    res_index = client.post("/documents/index", headers=admin_hdr)
    assert res_index.status_code == 200


def test_member_and_viewer_cannot_upload_or_delete(client, rbac_setup):
    admin_hdr = rbac_setup["admin"]
    member_hdr = rbac_setup["member"]
    viewer_hdr = rbac_setup["viewer"]

    # Admin uploads file
    client.post("/documents/upload", headers=admin_hdr, files=[("files", ("guide.txt", SOLAR_GUIDE, "text/plain"))])
    client.post("/documents/index", headers=admin_hdr)
    docs = client.get("/documents", headers=member_hdr).json()["documents"]
    assert len(docs) == 1
    doc_id = docs[0]["source_id"]

    # Member attempts upload -> 403
    res_mem_upload = client.post("/documents/upload", headers=member_hdr, files=[("files", ("bad.txt", b"Bad", "text/plain"))])
    assert res_mem_upload.status_code == 403

    # Viewer attempts upload -> 403
    res_view_upload = client.post("/documents/upload", headers=viewer_hdr, files=[("files", ("bad2.txt", b"Bad", "text/plain"))])
    assert res_view_upload.status_code == 403

    # Member attempts delete -> 403
    assert client.delete(f"/documents/{doc_id}", headers=member_hdr).status_code == 403

    # Viewer attempts delete -> 403
    assert client.delete(f"/documents/{doc_id}", headers=viewer_hdr).status_code == 403

    # Viewer attempts tag update -> 403
    assert client.patch(f"/documents/{doc_id}/tags", headers=viewer_hdr, json={"tags": ["Legal"]}).status_code == 403

    # Member CAN update tags
    tag_res = client.patch(f"/documents/{doc_id}/tags", headers=member_hdr, json={"tags": ["Legal"]})
    assert tag_res.status_code == 200
    assert tag_res.json()["tags"] == ["Legal"]


def test_viewer_read_only_access(client, rbac_setup):
    admin_hdr = rbac_setup["admin"]
    viewer_hdr = rbac_setup["viewer"]

    # Admin uploads file
    client.post("/documents/upload", headers=admin_hdr, files=[("files", ("solar.txt", SOLAR_GUIDE, "text/plain"))])
    client.post("/documents/index", headers=admin_hdr)

    # Viewer can read documents and passages
    res_docs = client.get("/documents", headers=viewer_hdr)
    assert res_docs.status_code == 200
    doc_id = res_docs.json()["documents"][0]["source_id"]

    res_file = client.get(f"/documents/{doc_id}/file", headers=viewer_hdr)
    assert res_file.status_code == 200

    # Viewer cannot save chats
    res_chat = client.post("/ask", headers=viewer_hdr, json={"question": "What is solar?", "save": True})
    assert res_chat.status_code == 403
    assert "Viewers cannot create or save chats" in res_chat.json()["detail"]


def test_update_member_role_and_promotion(client, rbac_setup):
    ws_id = rbac_setup["ws_id"]
    owner_hdr = rbac_setup["owner"]
    viewer_hdr = rbac_setup["viewer"]

    # Find viewer user_id
    members = client.get(f"/workspaces/{ws_id}/members", headers=owner_hdr).json()["members"]
    viewer_record = next(m for m in members if m["email"] == "viewer@example.org")

    # Viewer cannot upload
    assert client.post("/documents/upload", headers=viewer_hdr, files=[("files", ("f.txt", b"x", "text/plain"))]).status_code == 403

    # Promote viewer to admin
    patch_res = client.patch(
        f"/workspaces/{ws_id}/members/{viewer_record['id']}",
        headers=owner_hdr,
        json={"role": "admin"},
    )
    assert patch_res.status_code == 200

    # Viewer (now admin) can now upload!
    res_admin_upload = client.post("/documents/upload", headers=viewer_hdr, files=[("files", ("f.txt", SOLAR_GUIDE, "text/plain"))])
    assert res_admin_upload.status_code == 200
