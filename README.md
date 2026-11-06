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

Keys are read from environment variables: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` (or `GOOGLE_API_KEY`), `OPENAI_API_KEY`.
```
set GEMINI_API_KEY=your-key          (Windows Command Prompt;  PowerShell: $env:GEMINI_API_KEY="your-key")
python check_ai.py gemini            # one test call; prints a sample definition
python run.py --ai gemini
```
Only indicator names, formula wording, page names and the report's name/page names are sent – never report data. `--ai-send-dax` also sends the measure's DAX (more accurate; confirm your client allows it). `--ai-model <name>` overrides the default model if a provider retires one. Free keys may let the provider use what you send; check the provider's terms against your client's rules.

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
```
`tests/make_synthetic_projects.py <folder>` writes those made-up projects so you can open them yourself. The AI providers and the web could not be reached while the tests were written, so those parts are tested with simulated replies; use `check_ai.py` and `check_web.py` on your own network.

## Keeping client data out of Git
`.gitignore` excludes `source/`, `output/` and `glossary/` (your reports, generated documents and definitions). Do not remove those lines, and do not put API keys in files.
