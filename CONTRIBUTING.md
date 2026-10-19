# Contributing to AfriSearch

Thanks for helping. Bug reports, documents and questions in African languages for the evaluation set, translations and code are all welcome.

## Reporting a problem

Open a GitHub issue with:
- what you did, what you expected, and what happened instead;
- the language of the question and the documents;
- the answer model and search settings (Settings panel), and your operating system;
- for security problems, see [SECURITY.md](SECURITY.md) instead of opening a public issue.

Please don't attach private documents. A short made-up example that shows the problem is best.

## Setting up for development

Follow the setup in the [README](README.md), then install the test tools:

```bash
pip install -r requirements-dev.txt
pytest -q
```

The tests use fake models, fake OCR and a temporary data folder, so they need no downloads, keys or GPU and run in under a minute.

For the web app (`web/`, React + TypeScript + Tailwind):

```bash
cd web
npm install
npm run dev        # http://localhost:5173, with /api forwarded to the API on :8000
npm run typecheck
npm test
```

## Making a change

1. Create a branch from `main`.
2. Keep the change focused; one pull request per fix or feature.
3. Add or update tests for what you changed (`tests/`, `web/src/**/*.test.ts`), and run `pytest -q` (and `npm test` and `npm run typecheck` in `web/`).
4. If the change affects search or answers, run the evaluation and put the before/after numbers in the pull request:
   ```bash
   python evaluation/run_eval.py --retrieval-only --modes semantic rerank
   ```
5. Update the README if behaviour, settings or the API changed, and add a line to `CHANGELOG.md` under an "Unreleased" heading.
6. Open a pull request describing what changed and why. GitHub Actions runs the tests automatically.

## Code style

- Match the surrounding code: type hints, short docstrings that say *why*, and comments only where the code isn't obvious.
- User-facing text should be plain and specific: say what happened and what to do next.
- Don't add a dependency for something a few lines of code can do.

## Adding evaluation questions

Questions in Amharic, Swahili, Somali, Afaan Oromo, Hausa and other languages are especially valuable. Add documents to `evaluation/corpus/` (only text you have the right to share) and questions to `evaluation/questions.json`; the README explains the format.
