# TODO

The working task list. [ROADMAP.md](ROADMAP.md) has the bigger picture; this file has the concrete next steps, in priority order.

Sizes: **S** = a few hours, **M** = a few days, **L** = a week or more. 👤 = needs something only you can do (an account, a server, a decision).

---

## 🔴 P0 — before anyone outside the team uses it

### Accounts and security
- [ ] 👤 **Test Supabase sign-in end to end with a real project** (S): sign-up, email confirmation, sign-in, password reset, Google. So far it's only tested with tokens signed in the tests. *(README → Accounts and workspaces)*
- [x] **Run a security review** of the 0.2 changes (S) — done: 7 findings fixed or documented (see SECURITY.md): `/security-review`, plus a manual check that every `/api` route uses `current_workspace` or `current_user`. *(backend/main.py)*
- [x] **Rate limits** on `/api/ask`, `/api/ask/stream` and uploads, per user and per IP (M): one person shouldn't be able to run up the cloud-model bill or fill the disk.
- [x] **Check uploads by content, not just extension** (S): verify the PDF header, that images decode, and that TXT is valid UTF-8; reject the rest with a clear message. *(backend/store.py → `save_uploads`)*
- [x] **Storage quota per workspace** (S): reject uploads above a limit, and show usage in Settings.

### Deployment
- [ ] 👤 **Deploy to one cloud VM** behind Caddy with HTTPS (M): the guide (`docs/deploy.md`), `deploy/Caddyfile` and `deploy/docker-compose.prod.yml` are ready and validated; needs a server and a domain.
- [x] **Backups** (S): `python -m backend.backup create|restore`, restore tested. 👤 Set up the nightly cron job and an off-server copy when deploying.
- [x] **Error tracking** (S): Sentry for the API and the web app. 👤 Create the Sentry projects and set the DSNs.
- [ ] 👤 **Uptime monitoring** of `/api/health` (S): the health check now returns 503 on database or disk problems; add a monitor (UptimeRobot, Better Stack) after deploying.

### Legal and trust
- [x] **Privacy notice and terms pages** (M) — template pages, consent at sign-up. 👤 Have a lawyer review them and fill in the governing law.: `/privacy` and `/terms` in the web app, linked from the footer and the sign-up form. Say what is stored, where, and which passages go to which AI provider. Check against Ethiopia's Personal Data Protection Proclamation (2024) and Kenya's Data Protection Act (2019).
- [x] **Account deletion and data export** (M): a user can delete their account and download their documents and chats.

### Answer quality
- [ ] **Pick the default answer model** (S): run `python evaluation/run_eval.py --providers qwen-small claude chatgpt gemini` and compare correctness per language. Qwen 2.5 0.5B gets Amharic answers wrong and often skips citations.
- [x] **"Not covered" message in the question's language** (S) — Amharic and Swahili; 👤 have native speakers check the wording: it's English-only today. *(backend/answers.py → `NOT_COVERED_ANSWER`)*

---

## 🟠 P1 — for the pilot (2–5 organisations)

### Answers and search
- [ ] **More evaluation questions** in Somali, Afaan Oromo and Hausa (M): there's only one each, which is too few to judge. Ask pilot users for real questions and documents.
- [ ] **Check the reranker on Amharic** (S): one case where it ranked the wrong document first. Compare `--modes semantic rerank` on Amharic questions only, and turn reranking off for Ethiopic script if it hurts.
- [ ] **Tune the "not covered" threshold** (S) from real feedback: −4 stopped more off-topic questions on the test set but sits closer to real answers. *(`AFRISEARCH_MIN_RERANK_SCORE`)*
- [ ] **Stream answers from Claude, ChatGPT and Gemini** (M): today only local models stream. *(backend/llm.py: add a `stream` function per provider)*
- [ ] **Flag answers without citations** (S): show a "no source cited" warning when the model didn't cite anything.
- [ ] **"Try again with another model"** button on an answer (S).
- [ ] **Load the search model and reranker at startup** (S, optional setting): the first question currently waits about 10 s while they load.

### Team features
- [ ] **Invite people who haven't signed up yet** (M): an email invitation link, instead of "ask them to sign up first". Needs transactional email (below).
- [ ] **Share a chat** with the rest of the workspace (S, read-only).
- [ ] **Rename chats automatically** from the first answer, instead of the truncated question (S).

### Library
- [ ] **Word, Excel, PowerPoint, HTML and Markdown** documents (M): `python-docx`, `openpyxl`, `python-pptx`. *(backend/extract.py)*
- [ ] **Replace a document with a new version** (S): keep the name, re-index, and leave old chats readable.
- [ ] **Folders or tags**, and **bulk delete** (M).
- [ ] **Email when a long indexing job finishes** (S): needs transactional email.
- [ ] **Upload from the phone camera** (S): `<input capture="environment">` on mobile.

### Web app
- [ ] **End-to-end browser tests in the repo** (M): turn the Playwright journey used for 0.2 (upload → OCR → chat → citations → insights) into `web/e2e/`, and run it in CI.
- [ ] **Accessibility pass** (M): keyboard focus inside popovers and dialogs (focus trap), screen-reader labels, contrast in dark mode.
- [ ] **Pagination** for long chat lists (capped at 100) and big libraries (S).

---

## 🟡 P2 — turning it into a paid service

### Billing and plans
- [ ] **Decide pricing** with pilot users (S): what they value, and what each workspace costs to run (AI tokens, storage, CPU).
- [ ] **Plans and limits in the database** (M): documents, storage and questions per month per plan; enforce them in the API and show them in Settings.
- [ ] **Payments** (L): Stripe for cards; Chapa, Paystack or Flutterwave for local payment methods (Telebirr, M-Pesa…). Trials, invoices, and handling of webhooks.
- [ ] **Track cloud-model cost per workspace** (M): log the tokens used for each answer.
- [ ] **Pricing section** on the landing page, once prices are decided (S).

### Operations
- [ ] **Transactional email** (S): welcome, invitations, password reset branding, usage warnings (Resend, Postmark or SES).
- [ ] **Admin dashboard** (M): workspaces, users, usage, errors, and a way to help users.
- [ ] **Staging environment** and **deploy on tag** from GitHub Actions (M).
- [ ] **Audit log** (M): who uploaded, deleted or shared what.

### Scaling (when one server isn't enough)
- [ ] **PostgreSQL + pgvector** instead of SQLite and per-workspace NumPy files (L). *(backend/db.py, backend/store.py)*
- [ ] **Object storage** (S3-compatible) for uploads (M).
- [ ] **Job queue** (Redis + workers) instead of the in-process indexing thread, so several API servers can share work (M). *(backend/jobs.py)*
- [ ] **Separate model service** (embeddings, reranker, local LLM) on a GPU machine (L).

---

## 🟢 P3 — ideas for later

- [ ] **Interface in Amharic and Swahili** (M): add i18n to the web app, with translations reviewed by native speakers (not machine translation).
- [ ] **WhatsApp or Telegram bot** for asking questions from a phone (L).
- [ ] **Short summary of each document** after upload (M).
- [ ] **Suggested follow-up questions** under answers (S).
- [ ] **Public API keys** so organisations can connect their own tools (M).
- [ ] **Offline desktop package** for places with poor internet (L).

---

## 🧹 Housekeeping

- [ ] **Run the 6 skipped tests locally** (S): install `anthropic`, `openai` and `google-genai` in the dev environment. They already run in CI.
- [ ] **Dependabot** for pip, npm and GitHub Actions updates (S).
- [ ] **Pin the Docker base images** to exact versions or digests (S).
- [ ] **Smaller Docker image** (M): it's 2 GB, mostly PyTorch.
- [ ] **Remove the 0.1 data migration** in a later version, after users have upgraded (S). *(backend/main.py → `import_legacy_data`)*
- [ ] **Code-split the answer renderer further** (S): `react-markdown` is a 164 KB chunk.
- [ ] **Publish the GitHub release** for v0.2.0 from the tag, with the changelog (S).
- [ ] **Turn on private vulnerability reporting** in the GitHub settings (S): `SECURITY.md` refers to it.

---

## 🏁 Launch (not code)

- [ ] Find 2–5 pilot organisations (a cooperative, an NGO, a clinic, a school) and agree on what they'll test.
- [ ] Domain name and email address for the product.
- [ ] Onboarding guide for pilot users (one page: upload, ask, check sources, give feedback).
- [ ] Support channel (email or WhatsApp group) and a weekly review of the feedback in Insights.
- [ ] Privacy-friendly analytics on the landing page (e.g. Plausible) to see where visitors drop off.
- [ ] Legal entity and a data-processing agreement template for organisations.
