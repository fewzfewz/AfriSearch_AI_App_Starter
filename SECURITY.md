# Security policy

## Current status

AfriSearch 0.1 is built for **local use by one person or a trusted team**. It has **no logins**: anyone who can reach the API or the UI can read, upload and delete every document and see all feedback. The Docker setup therefore only listens on `127.0.0.1` by default.

Do not expose it to the internet or an untrusted network until logins and separate document spaces exist (see [ROADMAP.md](ROADMAP.md), stage 3). If you must share it on a local network, put it behind a reverse proxy with authentication and HTTPS.

Also keep in mind:
- Questions and the matching passages are sent to the provider when you use Claude, ChatGPT or Gemini.
- Uploaded files, the index and feedback are stored unencrypted in `data/`.
- Text inside documents can try to steer the answer model (prompt injection). Answers are instructed to rely only on the passages, but treat answers from untrusted documents with care.

## Reporting a vulnerability

Please report security problems privately, not in a public issue: use GitHub's **Security → Report a vulnerability** on this repository. Include the steps to reproduce and the version (`GET /` shows it). You should get a reply within a week.

## Supported versions

Only the latest release receives fixes.
