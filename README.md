# PBIP Documentation Generator

Reads an unzipped Power BI project (`<Name>.Report` + `<Name>.SemanticModel`) and writes three files to `output/`:

| File | Audience |
|---|---|
| `<Name>_User_Manual.docx` | business users: what each page shows, how to use it, what the figures mean |
| `<Name>_KPI_Glossary.docx` | every indicator the report displays: definition, formula, where the definition came from |
| `<Name>_KPI_Documentation.html` | technical reference: measures, DAX, pages, flags |

It works for any business (revenue, inventory, HR, gaming, streaming, insurance ...). Nothing about a business is written into the code: pages, measures, filters, colour rules and formulas are all read from the project.

## Quick start
```
pip install -r requirements.txt
# put the Report + SemanticModel folders (or their .zip files) in source/
python run.py --author "Your Name" --owner "Client"
```
Useful options: `--offline` (no web), `--name`, `--project-code --version --date-issued --document-id --location`, `--skip-html --skip-docx --skip-glossary`, `--version-info`.

## Two modes

| | Command | Needs | Glossary definitions |
|---|---|---|---|
| **Offline** (default) | `python run.py` | nothing | built-in standard terms, then a draft rephrased from each measure's own formula, e.g. "Turnover multiplied by Hold %". Marked *Draft from the formula – please verify*. |
| **AI** | `python run.py --ai gemini` (or `anthropic`, `openai`) | an API key | an AI writes a one-sentence business definition from the indicator's name, formula wording and page. Marked *AI draft – please verify*. Anything the AI cannot answer falls back to the formula draft. |

Set the key up once per computer (see **Team setup** below), then run `python run.py --ai`.
Only indicator names, formula wording, page names and the report's name/page names are sent – never report data. `--ai-send-dax` also sends the measure's DAX (more accurate; confirm your client allows it). `--ai-model <name>` overrides the default model if a provider retires one. Free keys may let the provider use what you send; check the provider's terms against your client's rules.

## Team setup (once per computer)
Anyone can use the tool on their own computer with their own key. Nothing about a key is ever stored in this repository.

1. **Get a key.** Ask IT for an API key for the AI service your company allows (Anthropic, Google Gemini or OpenAI). Skip this for offline mode: `python run.py` works with no key.
2. **Install Python 3.10 or newer** (python.org; on Windows tick *Add Python to PATH*).
3. **Get the tool.** `git clone https://github.com/IvanAjith/pbip-doc-generator` (or download the ZIP from GitHub and unzip it), then open a terminal in that folder.
4. **Install the helpers.** `pip install -r requirements.txt`
5. **Save the key – one time.** `python run.py --setup-ai`
   * Choose the service (1, 2 or 3), paste the key when asked. **Nothing appears on screen while you paste** – that is normal. Press Enter.
   * The tool makes one small test request and only saves the key if it works.
6. **Every report after that.** Put the report's `.Report` and `.SemanticModel` folders (or their `.zip` files) in `source/`, then run `python run.py --ai` (or just `python run.py` for offline mode). The three files appear in `output/`.

On Windows you can also double-click `run_windows.bat`; it runs the tool and keeps the window open.

### How the key is kept safe
* The key is **never inside the project folder**, so it cannot be committed to GitHub. It is stored in your Windows Credential Manager / macOS Keychain when the optional `keyring` package is installed (`pip install keyring`), otherwise in a private file in **your own user folder** (`~/.pbip_doc_generator/config.json`, readable only by you on macOS/Linux).
* It is never printed, logged, written to the documents, or sent anywhere except to the AI service you chose.
* Do not paste the key into chat, e-mail, a Word file or a file inside this folder. If one is ever exposed, ask IT to revoke it and issue a new one, then run `python run.py --setup-ai` again.
* `python run.py --ai-status` shows which keys exist (only the last four characters). `python run.py --forget-ai-key` removes the saved key from this computer (use this on a shared or borrowed computer when finished).
* Advanced: an environment variable (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY` / `GOOGLE_API_KEY`, `OPENAI_API_KEY`) overrides the saved key, which suits servers and CI.
* `python tests/test_secret_scan.py` fails if anything that looks like a key is in a file Git would publish; it also runs on every push.

### Network allow-list (ask IT if something is blocked)
* AI mode: `api.anthropic.com`, `generativelanguage.googleapis.com` or `api.openai.com` (only the one you chose).
* Web definitions (skipped with `--offline`): `en.wikipedia.org` and the search engines the `ddgs` package uses.
* Installing: `pypi.org`, `files.pythonhosted.org`, `github.com`.
If the AI cannot be reached the tool says so and carries on with formula drafts, so a run never fails because of the network.

### Platforms
The code uses only portable file handling and UTF-8 everywhere. The automated tests run on Linux (Python 3.10 and 3.12) on GitHub. Windows and macOS have not been tested by the author; if something misbehaves, send the console text and the tool version (`python run.py --version-info`).
The INDEX page numbers in the manual need Word or LibreOffice; without them the tool says so and the index updates when you press F9 in Word.

## Fixing definitions (no coding)
Open `output\<Name>_KPI_Glossary.docx`:
* **Strong yellow** = nothing could be built or found: type your definition over the text.
* **Pale yellow** = a draft (formula / AI / web): correct it if it is wrong, leave it if it is right.
* Edit the **What it means** cell, save and close the file, then run `python run.py` again. Your wording is read back from the Word file, replaces the draft in all three documents, and is kept on every later run (stored in `glossary/glossary.json`).

Alternatively edit `glossary/my_definitions.csv` in Excel (one row per indicator; type `ok` to accept a suggestion).

Definition order: your own → built-in standard terms (~180 across finance, sales, HR, safety, inventory, subscriptions, gaming, insurance) → web (Wikipedia, optional `ddgs`) → AI draft (if `--ai`) → formula draft → "needs your definition".

If definitions from the web are missing, open `glossary/web_log.txt`: it lists each term searched and why nothing was used.

## What is read from the project vs. assumed
* **Read from the PBIP (never assumed):** pages, navigation, filters, bookmarks, DAX meaning, thresholds, colour rules, data sources. Colour or threshold text appears only where the visual JSON or DAX defines it.
* **Main pages** are found from the navigation buttons between pages; hidden, tooltip, drill-through and unlinked pages are listed in the console and left out of the manual (the HTML covers all pages). Reports with three or fewer linked pages keep every linked page.
* **Naming conventions the code does assume:** measures whose names contain words like *header, title, banner, footer, legend, spacer* are page furniture, not indicators; words like *HTML, Card, Pill* are stripped from display names; with no navigation buttons at all, pages named like *test / duplicate / draft* are treated as scratch.
* The INDEX page numbers are real when LibreOffice or Word is available; otherwise press F9 in Word to update the index.

## Tests
```
python tests/test_formula_draft.py      # formula -> sentence
python tests/test_ai_providers.py       # request/response shapes for Anthropic, Gemini, OpenAI (simulated)
python tests/test_glossary_csv_ai.py    # my_definitions.csv + AI step
python tests/test_web_glossary.py       # web lookup + precedence (simulated network)
python tests/test_word_roundtrip.py     # edit the glossary in Word, run again
python tests/test_end_to_end.py         # made-up inventory / streaming / HR / gaming projects
python tests/test_secrets.py            # key storage, masking, guided setup
python tests/test_secret_scan.py        # no key-like text in files Git would publish
```
`tests/make_synthetic_projects.py <folder>` writes those made-up projects so you can open them yourself. The AI providers and the web could not be reached while the tests were written, so those parts are tested with simulated replies; use `check_ai.py` and `check_web.py` on your own network.

## Keeping client data out of Git
`.gitignore` excludes `source/`, `output/` and `glossary/` (your reports, generated documents and definitions). Do not remove those lines, and never put API keys in any file in this folder - use `python run.py --setup-ai`.
