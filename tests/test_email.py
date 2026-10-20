"""Transactional email: what is sent when, and the Resend and SMTP back ends."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from backend import config, jobs, mailer
from conftest import SOLAR_GUIDE
from test_accounts import as_user


@pytest.fixture
def email_on(app_env, monkeypatch):
    monkeypatch.setattr(config, "EMAIL_BACKEND", "memory")
    monkeypatch.setattr(config, "APP_URL", "https://afrisearch.example.org")
    return mailer.outbox


@pytest.fixture
def supabase(app_env, monkeypatch):
    from test_accounts import SECRET

    monkeypatch.setattr(config, "AUTH_MODE", "supabase")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", SECRET)


def sent(outbox):
    mailer.wait()
    return list(outbox)


def test_email_is_off_by_default(client, supabase):
    client.get("/me", headers=as_user())
    mailer.wait()
    assert mailer.outbox == []
    assert client.get("/config").json()["email"] is False


def test_welcome_email_on_first_sign_in_only(client, supabase, email_on):
    client.get("/me", headers=as_user())
    client.get("/me", headers=as_user())
    [welcome] = sent(email_on)
    assert welcome.to == "amina@example.org" and welcome.subject == "Welcome to AfriSearch"
    assert "Hi Amina" in welcome.text
    assert "https://afrisearch.example.org/app/library" in welcome.html


def test_invitations_are_emailed(client, supabase, email_on):
    owner = as_user(sub="owner", email="owner@example.org")
    workspace = client.get("/me", headers=owner).json()["workspaces"][0]["id"]
    client.get("/me", headers=as_user(sub="guest", email="guest@example.org"))
    mailer.wait()
    email_on.clear()  # the welcome emails

    newcomer = client.post(f"/workspaces/{workspace}/members", headers=owner, json={"email": "new@example.org"}).json()
    assert newcomer["message"].endswith("We've emailed them.")
    client.post(f"/workspaces/{workspace}/members", headers=owner, json={"email": "guest@example.org"})
    invite, added = sent(email_on)
    assert invite.to == "new@example.org" and "Owner invited you to My documents" in invite.subject
    assert "https://afrisearch.example.org/signin" in invite.text
    assert added.to == "guest@example.org" and "added you" in added.subject
    assert "<script" not in invite.html


def test_names_are_escaped_in_html(email_on):
    email = mailer.invitation("a@example.org", "<b>Eve</b>", "Farm & Co", has_account=True)
    assert "&lt;b&gt;Eve&lt;/b&gt;" in email.html and "Farm &amp; Co" in email.html
    assert "<b>Eve</b>" in email.text  # plain text stays as typed


def test_long_indexing_jobs_email_whoever_started_them(client, supabase, email_on, monkeypatch):
    user = as_user()
    client.get("/me", headers=user)
    mailer.wait()
    email_on.clear()
    client.post("/documents/upload", headers=user, files=[("files", ("guide.txt", SOLAR_GUIDE, "text/plain"))])

    monkeypatch.setattr(config, "EMAIL_INDEXING_AFTER_SECONDS", 3600)  # quick jobs: no email
    jobs.wait(client.post("/documents/index?wait=false", headers=user).json()["job"]["id"])
    assert sent(email_on) == []

    client.post("/documents/upload", headers=user, files=[("files", ("more.txt", b"Batteries last ten years.", "text/plain"))])
    monkeypatch.setattr(config, "EMAIL_INDEXING_AFTER_SECONDS", 1e-9)
    jobs.wait(client.post("/documents/index?wait=false", headers=user).json()["job"]["id"])
    [done] = sent(email_on)
    assert done.subject == "Your documents are ready" and "(1 indexed)" in done.text


def test_resend_back_end(monkeypatch):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append({"path": self.path, "auth": self.headers["Authorization"],
                             "body": json.loads(self.rfile.read(int(self.headers["Content-Length"])))})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"id": "1"}')

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(config, "EMAIL_BACKEND", "resend")
    monkeypatch.setattr(config, "RESEND_API_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr(config, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(config, "EMAIL_FROM", "AfriSearch <hello@example.org>")
    try:
        mailer.send(mailer.welcome("amina@example.org", "Amina"))
        mailer.wait()
    finally:
        server.shutdown()
    [request] = received
    assert request["path"] == "/emails" and request["auth"] == "Bearer re_test"
    assert request["body"]["to"] == ["amina@example.org"]
    assert request["body"]["from"] == "AfriSearch <hello@example.org>"
    assert request["body"]["html"] and request["body"]["text"]


def test_smtp_back_end(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, message):
            calls.append(("send", message["To"], message["Subject"], message.is_multipart()))

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    for name, value in {"EMAIL_BACKEND": "smtp", "SMTP_HOST": "smtp.example.org", "SMTP_PORT": 587,
                        "SMTP_USER": "user", "SMTP_PASSWORD": "pw"}.items():
        monkeypatch.setattr(config, name, value)
    mailer.send(mailer.welcome("amina@example.org", "Amina"))
    mailer.wait()
    assert calls == [("connect", "smtp.example.org", 587), ("starttls",), ("login", "user", "pw"),
                     ("send", "amina@example.org", "Welcome to AfriSearch", True)]


def test_send_failures_are_logged_not_raised(monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(mailer.smtplib, "SMTP", broken)
    monkeypatch.setattr(config, "EMAIL_BACKEND", "smtp")
    mailer.send(mailer.welcome("amina@example.org", "Amina"))
    mailer.wait()
    assert "Couldn't send email" in caplog.text
