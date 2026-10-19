# Changelog

All notable changes to AfriSearch are listed here. The project uses [semantic versioning](https://semver.org/): until 1.0, minor versions may change the API or the index format.

## [0.1.0] — 2026-10-19

First public release.

### Documents
- Upload PDF, TXT and images of pages (PNG, JPG, TIFF, WebP, BMP); exact duplicates are rejected.
- OCR for scanned PDFs and photos with Tesseract (English, Amharic and Swahili by default), page by page, so mixed PDFs work.
- Sentence-aware chunks that can span pages; Amharic sentences end at `።`, `፧` or `፡፡`.
- Incremental indexing, deletion, and automatic re-indexing prompts when the search model changes.

### Search and answers
- Multilingual search with `intfloat/multilingual-e5-small` (94 languages, cross-language matching).
- Multilingual reranker (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`), on by default and switchable per question.
- Relevance cutoff tuned per search model.
- Answers from Claude, ChatGPT, Gemini or local models (Qwen, Gemma, gpt-oss, Qwen 2.5 0.5B on CPU), with `[S1]` citations; invalid citations are removed.
- Streaming answers for local models (`POST /ask/stream`).
- Search limited to chosen documents (`source_ids`), and a passages-only mode.

### Interface
- Streamlit UI with light and dark themes and a phone-friendly layout.
- Ask tab: settings panel, document scope, streamed answers, citations that jump to their source, ratings, Markdown export of an answer or the whole session.
- Library tab: document table (type, pages, passages, OCR, size, date), passage viewer, delete with confirmation.
- Insights tab: library, session and feedback statistics.

### Quality and release
- Evaluation set of 45 questions in six languages, with a scoring script for search and answer models.
- 93 automated tests; GitHub Actions runs them on every push.
- Docker image with Tesseract included, and `docker compose up` for the API and UI.
- MIT license, contributor guide, security policy and roadmap.
