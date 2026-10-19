# Roadmap

AfriSearch is heading towards a hosted product (SaaS) for organisations that work with documents in African languages. This roadmap lists what is done and what is still needed, in the order that lets real users shape the later steps.

## Release types

| Release type | Who uses it | Status |
|---|---|---|
| **A. Open-source, self-hosted** | Developers and organisations run it themselves | ✅ v0.1 |
| **B. Hosted pilot** | A few invited organisations on one server | 🟡 v0.2 has accounts, workspaces and the web app; HTTPS, backups and privacy notice remain |
| **C. Paid service** | Anyone can sign up and pay | ⬜ after the pilot |

## Stage 1: open-source release (v0.1) ✅

- [x] MIT license, contributor guide, security policy, changelog
- [x] Docker image and `docker compose up`, with Tesseract OCR included
- [x] GitHub Actions: tests and Docker build on every push
- [x] Answer feedback (👍/👎 with comments)

## Stage 2: reliability and answer quality (v0.2) ✅ mostly

- [x] **Background indexing with progress**: uploads return at once; the Library shows file, page and stage
- [x] **Questions the documents don't cover**: a reranker-score rule stops 3 of 6 off-topic test questions before they reach the model (2 before), with no answerable ones lost
- [x] **Answers in the question's language**, with an explicit instruction for Amharic
- [x] **Follow-up questions** in a chat use the previous question and answers
- [ ] **Measure answer quality** per model and language with `evaluation/run_eval.py --providers ...`, and choose the default model for the hosted service from the results
- [ ] Check whether the reranker hurts Amharic questions (one case seen in testing)

## Stage 3: hosted pilot (v0.2 → v0.3) 🟡

- [x] **Accounts** with Supabase Auth (email and password, Google, reset, confirmation)
- [x] **Workspaces** with separate documents, chats and feedback; owners add members
- [x] **Web app**: landing page, sign-in, chat, library, insights, settings, dark mode, phone layout
- [ ] **HTTPS** behind a reverse proxy (Caddy), and a deployment guide for one cloud VM
- [ ] **Backups** of the data volume, and a tested restore
- [ ] **Privacy notice and terms**: what is stored, which passages go to which AI provider. Ethiopia's Personal Data Protection Proclamation (2024) and Kenya's Data Protection Act (2019) require telling users and having a legal basis.
- [ ] **Rate limits and upload checks** on file content (not only the extension)
- [ ] **Error tracking and logs** (for example Sentry) and uptime monitoring
- [ ] **Invitations by email** for people who haven't signed up yet

## Stage 4: pilot with real users

- [ ] Run with 2–5 organisations and 20–50 users for a few weeks
- [ ] Review the Insights tab and feedback: failing questions, languages, missing documents
- [ ] Fix the most common failures; decide on pricing from what users value and what it costs to run

## Stage 5: paid service (v1.0)

- [ ] **Billing** (for example Stripe, or Flutterwave / Paystack / Chapa for African payment methods): plans, trials, invoices
- [ ] **Usage limits per plan**: documents, storage, questions per month; metering of cloud-model cost per workspace
- [ ] **PostgreSQL with pgvector** instead of SQLite and per-workspace NumPy files, and object storage (S3-compatible) for uploads, so several API servers can share the load
- [ ] **A job queue** (for example Redis + workers) instead of the in-process indexing thread
- [ ] **Admin dashboard**: workspaces, usage, errors, support
- [ ] **Transactional email**: welcome, invitations, usage warnings
- [ ] **Data export and account deletion** for users (also a legal requirement in many countries)
- [ ] Security review / penetration test before opening public sign-up

## Later ideas

- Word, Excel and PowerPoint documents
- Streaming answers for Claude, ChatGPT and Gemini
- An interface in Amharic and Swahili (needs reviewed translations, not machine translation)
- WhatsApp or Telegram bot for asking questions from a phone
- Uploading straight from the phone camera
