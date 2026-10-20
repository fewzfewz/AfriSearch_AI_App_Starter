"""Transactional email: invitations, welcome, and "your documents are ready".

Off unless AFRISEARCH_EMAIL is set:
    log     write emails to the server log instead of sending (development)
    resend  send with Resend (RESEND_API_KEY)
    smtp    send through any SMTP server (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD)
    memory  keep sent emails in `outbox` (tests)

Emails are sent on a background thread, so a slow or failing mail server never
delays a request; failures are logged.
"""
from __future__ import annotations

import html
import json
import logging
import smtplib
import ssl
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from email.message import EmailMessage

from backend import config

logger = logging.getLogger("afrisearch.mailer")

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mailer")
_pending: list[Future] = []
outbox: list["Email"] = []  # the "memory" backend


@dataclass
class Email:
    to: str
    subject: str
    text: str
    html: str


def enabled() -> bool:
    return config.EMAIL_BACKEND in {"log", "resend", "smtp", "memory"}


def send(email: Email) -> None:
    """Queue an email; does nothing when email is off."""
    if not enabled() or not email.to:
        return
    _pending[:] = [f for f in _pending if not f.done()]
    _pending.append(_executor.submit(_deliver, email))


def wait(timeout: float = 10) -> None:
    """Block until queued emails are handed over (tests)."""
    for future in list(_pending):
        future.result(timeout=timeout)


def _deliver(email: Email) -> None:
    try:
        backend = config.EMAIL_BACKEND
        if backend == "memory":
            outbox.append(email)
        elif backend == "log":
            logger.info("Email to %s: %s\n%s", email.to, email.subject, email.text)
        elif backend == "resend":
            _send_resend(email)
        elif backend == "smtp":
            _send_smtp(email)
    except Exception:
        logger.exception("Couldn't send email '%s' to %s", email.subject, email.to)


def _send_resend(email: Email) -> None:
    request = urllib.request.Request(
        f"{config.RESEND_API_URL}/emails",
        data=json.dumps({"from": config.EMAIL_FROM, "to": [email.to], "subject": email.subject,
                         "text": email.text, "html": email.html}).encode(),
        headers={"Authorization": f"Bearer {config.RESEND_API_KEY}", "Content-Type": "application/json",
                 "User-Agent": "AfriSearch"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()


def _send_smtp(email: Email) -> None:
    message = EmailMessage()
    message["From"] = config.EMAIL_FROM
    message["To"] = email.to
    message["Subject"] = email.subject
    message.set_content(email.text)
    message.add_alternative(email.html, subtype="html")
    context = ssl.create_default_context()
    if config.SMTP_PORT == 465:
        server: smtplib.SMTP = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=20, context=context)
    else:
        server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20)
    with server:
        if config.SMTP_PORT != 465 and config.SMTP_STARTTLS:
            server.starttls(context=context)
        if config.SMTP_USER:
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(message)


# --- the emails -------------------------------------------------------------------

def _link(path: str) -> str:
    return f"{config.APP_URL}{path}" if config.APP_URL else ""


def _compose(to: str, subject: str, paragraphs: list[str], button: tuple[str, str] | None = None) -> Email:
    """A plain-text and a simple HTML version of the same message."""
    text = "\n\n".join(paragraphs)
    action = ""
    if button and button[1]:
        text += f"\n\n{button[0]}: {button[1]}"
        action = (f'<p style="margin:28px 0"><a href="{html.escape(button[1])}" style="background:#c2410c;color:#fff;'
                  f'padding:12px 20px;border-radius:10px;text-decoration:none;font-weight:600">'
                  f"{html.escape(button[0])}</a></p>")
    text += "\n\n— AfriSearch"
    body = "".join(f'<p style="margin:0 0 14px">{html.escape(p)}</p>' for p in paragraphs)
    page = (
        '<div style="background:#fafaf9;padding:32px 16px;font-family:Inter,Segoe UI,Arial,sans-serif;color:#1c1917">'
        '<div style="max-width:520px;margin:0 auto;background:#fff;border:1px solid #e7e5e4;border-radius:16px;padding:32px">'
        '<p style="margin:0 0 24px;font-weight:700;font-size:18px;color:#c2410c">AfriSearch</p>'
        f'<div style="font-size:15px;line-height:1.6">{body}{action}</div>'
        '<p style="margin:24px 0 0;font-size:12px;color:#78716c">Answers from your own documents, with sources.</p>'
        "</div></div>"
    )
    return Email(to=to, subject=subject, text=text, html=page)


def invitation(to: str, inviter: str, workspace: str, has_account: bool) -> Email:
    if has_account:
        return _compose(to, f"{inviter} added you to {workspace} on AfriSearch", [
            f"{inviter} added you to the workspace “{workspace}”.",
            "You can now search its documents and ask questions about them.",
        ], ("Open AfriSearch", _link("/app")))
    return _compose(to, f"{inviter} invited you to {workspace} on AfriSearch", [
        f"{inviter} invited you to the workspace “{workspace}” on AfriSearch, where you can ask questions "
        "about your team's documents and get answers that cite their sources.",
        f"Sign up with this email address ({to}) and you'll join the workspace automatically.",
    ], ("Accept the invitation", _link("/signin")))


def welcome(to: str, name: str) -> Email:
    return _compose(to, "Welcome to AfriSearch", [
        f"Hi {name or 'there'},",
        "Your account is ready. Upload PDFs, Word or Excel files, or photos of pages to the Library, "
        "then ask questions in any language: every answer shows the passages it comes from.",
    ], ("Upload your first document", _link("/app/library")))


def indexing_done(to: str, workspace: str, documents: int, failed: int) -> Email:
    lines = [f"Your documents in “{workspace}” are ready to search ({documents} indexed)."]
    if failed:
        lines.append(f"{failed} file{'s' if failed != 1 else ''} couldn't be read; the Library shows why.")
    return _compose(to, "Your documents are ready", lines, ("Ask a question", _link("/app")))
