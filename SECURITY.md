# Security policy

## Current status

AfriSearch 0.2 has two modes:

- **Local mode** (`AFRISEARCH_AUTH=none`, the default): no sign-in; anyone who can reach the server can read, upload and delete every document. Docker therefore only listens on `127.0.0.1`. Use it on your own computer only.
- **Accounts** (`AFRISEARCH_AUTH=supabase`): every API request needs a valid Supabase access token, checked against the project's published signing keys (audience `authenticated`, expiry enforced). Each workspace's documents, chats and feedback are only available to its members.

Before opening a server to the internet, even with accounts on:
- Put it behind HTTPS (see the README's *Running in production*). Tokens must never travel over plain HTTP.
- There is no rate limiting or per-user quota yet; anyone with an account can upload and ask without limit.
- Uploads are checked by extension and size, not by content.
- Files, the index and the database are stored unencrypted in the data volume; protect and back up the server accordingly.

Also keep in mind:
- Questions and the matching passages are sent to the provider when you use Claude, ChatGPT or Gemini.
- Text inside documents can try to steer the answer model (prompt injection). Answers are instructed to rely only on the passages, but treat answers from untrusted documents with care.

## Reporting a vulnerability

Please report security problems privately, not in a public issue: use GitHub's **Security → Report a vulnerability** on this repository. Include the steps to reproduce and the version (`GET /api/health` shows it). You should get a reply within a week.

## Supported versions

Only the latest release receives fixes.
