# Roadmap

AfriSearch is a working prototype: it runs well for one person on one machine. This roadmap is the plan for turning it into something other people and organizations can rely on. It is ordered so that each stage is useful on its own, and so that real users shape the later stages.

## Who it is for

| Release type | Who uses it | Effort | Adds |
|---|---|---|---|
| **A. Open-source, self-hosted** | Developers and organizations run it on their own machine or server | ~1–2 weeks | License, Docker, automated tests, versioned releases |
| **B. Hosted for one organization** (NGO, company, university) | A team shares one server | ~1–2 months | A + logins, separate document spaces, HTTPS, backups, background processing |
| **C. Public service** | Anyone on the internet | ~3–6 months+ | B + sign-up, payments, abuse protection, privacy-law compliance, scaling, running costs |

The plan is **A first, then B as a pilot with one real group of users** (a cooperative, an NGO, a clinic), and to decide on C only after the pilot.

## Stage 1 — Open-source release (A) · week 1 · ✅ done in v0.1.0

- [x] MIT license
- [x] Docker image and `docker compose up` for the API and the UI, with Tesseract OCR included
- [x] GitHub Actions running the tests (and building the Docker image) on every push and pull request
- [x] Version number, `CHANGELOG.md`, contributor guide and security policy
- [x] Answer feedback (👍/👎 with comments) saved on the server, to measure quality during the pilot

## Stage 2 — Reliability and answer quality · weeks 2–3

- [ ] **Background indexing with progress.** OCR takes about 3–7 s per page, so a 100-page scan currently holds the request open for over 10 minutes. Index in a background job and show progress in the UI.
- [ ] **Measure answer quality** with `evaluation/run_eval.py --providers ...`, especially for Amharic and Swahili questions, and choose the default answer model from the results. Qwen 2.5 0.5B is too weak for real users; the realistic options are a cloud model (about $0.01 per question) or a GPU server.
- [ ] **Stricter handling of questions the documents can't answer.** Only 2 of 6 off-topic test questions are stopped before reaching the model, and small models tend to invent answers.
- [ ] **Answer in the question's language**, with evaluation questions to check it.
- [ ] Check that the reranker doesn't hurt Amharic questions (one case seen in testing) and turn it off per language if it does.

## Stage 3 — Hosted pilot (B) · weeks 4–8

- [ ] **Logins.** Anyone who can reach the API can currently read and delete every document.
- [ ] **Separate document spaces** per user or team.
- [ ] **PostgreSQL with pgvector** instead of `index.json` + `embeddings.npy`, so the index scales past a few thousand documents and survives concurrent writes.
- [ ] **HTTPS** behind a reverse proxy (for example Caddy), rate limits, and upload checks on file content rather than only the extension.
- [ ] **Backups** of documents, index and feedback; logs and basic monitoring.
- [ ] **Privacy notice and a local-only mode.** Passages sent to Claude, ChatGPT or Gemini leave the country; Ethiopia's Personal Data Protection Proclamation (2024) and Kenya's Data Protection Act (2019) require telling users and having a legal basis.

## Stage 4 — Pilot with real users

- [ ] Run with 5–20 users for a few weeks.
- [ ] Review the feedback log (Insights tab, `data/feedback.jsonl`): which questions fail, in which languages, with which documents.
- [ ] Fix the most common failures, then decide whether a public service (C) is worth building.

## Later ideas

- Follow-up questions that use the earlier conversation ("and the SB-500?")
- Streaming answers for Claude, ChatGPT and Gemini
- Word and Excel documents
- An interface in Amharic and Swahili (needs reviewed translations, not machine translation)
- Mobile-friendly upload straight from the phone camera
