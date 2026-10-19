# Security policy

## Current status

AfriSearch 0.2 has two modes:

- **Local mode** (`AFRISEARCH_AUTH=none`, the default): no sign-in; anyone who can reach the server can read, upload and delete every document. Docker therefore only listens on `127.0.0.1`. Use it on your own computer only.
- **Accounts** (`AFRISEARCH_AUTH=supabase`): every API request needs a valid Supabase access token, checked against the project's published signing keys (audience `authenticated`, expiry enforced). Each workspace's documents, chats and feedback are only available to its members.

In place:
- Uploads are read in pieces and stopped at 15 MB, at most 20 files per request, and checked by **content** (PDF header, images must decode, text must not be binary).
- **Rate limits** per user (questions per minute and per day, uploaded files per hour) and a **storage quota** per workspace.
- **Security headers**: a Content-Security-Policy that allows only the app's own scripts, `X-Content-Type-Options: nosniff` (uploaded text is never run as HTML), and no framing. Caddy adds HSTS in production.
- Ratings can only be attached to messages in your own chats.

Before opening a server to the internet:
- Put it behind HTTPS ([docs/deploy.md](docs/deploy.md)). Tokens must never travel over plain HTTP.
- Keep **Confirm email** on in Supabase. Members are added by email, so an unverified email could let someone claim a colleague's address.
- Files, the index and the database are stored unencrypted in the data volume; protect the server, and keep backups off it.
- Rate limits are counted per process; behind several API processes each counts separately.

Also keep in mind:
- Questions and the matching passages are sent to the provider when you use Claude, ChatGPT or Gemini.
- Text inside documents can try to steer the answer model (prompt injection). Answers are instructed to rely only on the passages, but treat answers from untrusted documents with care.

## Reporting a vulnerability

Please report security problems privately, not in a public issue: use GitHub's **Security → Report a vulnerability** on this repository. Include the steps to reproduce and the version (`GET /api/health` shows it). You should get a reply within a week.

## Supported versions

Only the latest release receives fixes.
