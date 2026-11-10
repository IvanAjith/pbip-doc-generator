# Changelog

## 1.4.1
- Fix: a crash ("TypeError ... NoneType" in `tables_referenced`) on semantic models whose table files start with a byte-order mark, Windows line endings or `///` description lines. The table name is now found anywhere in the file, quoted names with doubled quotes work, and a table that cannot be read takes its file name instead of no name.
- Byte-order marks are ignored when reading all TMDL and JSON files.
- New test `tests/test_tmdl_variants.py`.

## 1.4.0
Clearer start-up flow.
- First question is now "Do you have an AI API key? 1. Yes (AI mode) / 2. No (offline mode)".
- A recognised key (Anthropic / Gemini / OpenAI) is used straight away, with no confirmation step.
- A rejected or unreachable key (or a saved key that no longer works) shows the reason and asks "continue in offline mode? (y/n)": y generates the three documents offline; n stops with "Invalid API key" and exit code 1.
- An "sk-" key that fails as OpenAI offers the Other-service route before giving up.

## 1.3.0
Keys from any service.
- The service no longer has to be chosen first: paste the key and the tool recognises Anthropic / Gemini / OpenAI from its start and asks to confirm.
- New **Other (OpenAI-compatible)** option for Azure OpenAI, Mistral, Groq, DeepSeek, OpenRouter, company gateways, Ollama: asks once for the service's web address and model name (https only), stored with the key's other settings; `--ai custom --ai-url --ai-model`.
- `--ai-status` shows the host and model of an Other service, never the key.

## 1.2.0
One universal start: `python run.py`.
- Asks "1. AI mode (needs an API key) / 2. Offline mode (formula drafts)". AI mode takes the pasted key (hidden), tests it, offers to save it (outside the project), then generates the three documents; offline generates them straight away.
- A saved key is offered next time (Enter to use it).
- No question is asked when options are given (`--offline`, `--ai`) or when there is no keyboard (`--no-prompt`, automation).

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
