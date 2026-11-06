# Changelog

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
