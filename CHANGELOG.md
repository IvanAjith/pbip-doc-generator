# Changelog

## 1.1.0
Safe, per-computer API keys for team use.
- New `python run.py --setup-ai`: guided one-time setup. Choose Anthropic / Gemini / OpenAI, paste the key (hidden), one test request, saved only if it works.
- Keys are stored outside the project (OS secure store if `keyring` is installed, otherwise a private file in the user's home folder, owner-only). Never printed (only the last four characters), never logged.
- `python run.py --ai` (no name) uses the saved default provider. New `--ai-status` and `--forget-ai-key`.
- Environment variables still override the saved key.
- Secret-scan test (also in CI) fails if a key-like string is in a file Git would publish.
- Console output no longer crashes on characters an older Windows console cannot show.
- `run_windows.bat` launcher; README team setup, network allow-list and platform notes.

## 1.0.0
First version kept in Git.
- Reads an unzipped PBIP (`*.Report` + `*.SemanticModel`) and writes a User Manual (.docx), KPI Glossary (.docx) and KPI Documentation (.html).
- Page classification from the navigation graph; colour/threshold text only where the visual JSON or DAX defines it.
- Glossary definitions: your own > built-in standard terms > web (Wikipedia / search) > AI draft (optional) > draft rephrased from the formula > "needs your definition".
- Offline mode: every indicator gets a draft built from its own formula, marked "please verify".
- Optional AI mode: `--ai anthropic|gemini|openai`.
- Edit definitions directly in the glossary Word file; the next run reads them back.
- Every measure displayed in the report has a glossary row (cards, tables, charts).
- Tests on made-up inventory, streaming, HR and gaming projects.
