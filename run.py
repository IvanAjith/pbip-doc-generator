#!/usr/bin/env python3
"""
run.py -- PBIP Documentation Generator
=======================================
    python run.py
    python run.py --author "Jane Doe" --owner "Acme Corp"
    python run.py --offline            (no web lookups)

Put an unzipped Power BI project in source/ (a "<Name>.Report" folder and a
"<Name>.SemanticModel" folder side by side -- or just the two .zip files) and
run this. Three files are written to output/:

    <Name>_User_Manual.docx          business-user manual
    <Name>_KPI_Glossary.docx         plain-English KPI definitions
    <Name>_KPI_Documentation.html    technical interactive reference

Nothing about any particular business is built in. Definitions come from
glossary/glossary.json (yours), a small built-in seed list, and -- unless
--offline -- the web, saved back to glossary.json for you to review.
"""
import argparse
import urllib.parse
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def find_or_unzip_project(source_dir: Path):
    report_dirs = list(source_dir.glob("*.Report"))
    sm_dirs = list(source_dir.glob("*.SemanticModel"))
    if not report_dirs or not sm_dirs:
        zips = list(source_dir.glob("*.zip"))
        if zips:
            print(f"No unzipped project found -- unzipping {len(zips)} archive(s) from {source_dir} ...")
            for z in zips:
                try:
                    with zipfile.ZipFile(z) as zf:
                        zf.extractall(source_dir)
                    print(f"  extracted {z.name}")
                except zipfile.BadZipFile:
                    print(f"  WARNING: {z.name} is not a valid zip file -- skipped")
            report_dirs = list(source_dir.glob("*.Report"))
            sm_dirs = list(source_dir.glob("*.SemanticModel"))
    if not report_dirs or not sm_dirs:
        listing = "\n".join(f"  - {p.name}" for p in sorted(source_dir.iterdir())) if source_dir.exists() else "  (folder missing)"
        sys.exit("\nERROR: couldn't find a Power BI project in the source folder.\n\n"
                 "Expected a '<Name>.Report' folder AND a '<Name>.SemanticModel' folder side by side\n"
                 "(or the .zip files for them). Currently there:\n" + listing)
    if len(report_dirs) > 1 or len(sm_dirs) > 1:
        sys.exit("ERROR: more than one project found in the source folder. This tool handles one project "
                 "per run -- keep a single Report + SemanticModel pair there.")
    return report_dirs[0], sm_dirs[0]


def build_manual_with_real_toc(manual_gen, project_name, analysis, page_items, docx_path, meta):
    """Pass 1 builds the manual with a placeholder INDEX and finds where each
    heading lands (via a PDF render). Pass 2+ rebuild with a real INDEX table --
    whose own length shifts the pages -- until the numbers stop moving.
    Without Word/LibreOffice the manual keeps a Word TOC field that fills in
    when opened (press F9)."""
    import pdf_utils
    log = manual_gen.build_manual(project_name, analysis, page_items, docx_path, meta)
    pdf_dir = docx_path.parent / ".pdf_tmp"
    pdf = pdf_utils.convert_to_pdf(docx_path, pdf_dir)
    if not pdf:
        return log, False
    entries = [(lvl, txt) for lvl, txt in log]
    heads = [t for _, t in entries]
    pmap = pdf_utils.find_heading_pages(pdf, heads, start_after_text="Document Control")
    for _ in range(3):
        manual_gen.build_manual(project_name, analysis, page_items, docx_path, meta,
                                toc_page_map=pmap, toc_entries=entries)
        pdf = pdf_utils.convert_to_pdf(docx_path, pdf_dir)
        if not pdf:
            break
        new = pdf_utils.find_heading_pages(pdf, heads, start_after_text="Document Control")
        if new == pmap:
            break
        pmap = new
    else:
        manual_gen.build_manual(project_name, analysis, page_items, docx_path, meta,
                                toc_page_map=pmap, toc_entries=entries)
    try:
        for f in pdf_dir.glob("*"):
            f.unlink()
        pdf_dir.rmdir()
    except OSError:
        pass
    return log, True


def _console_safe():
    """Never crash on a character the console cannot show (older Windows consoles)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


def main():
    _console_safe()
    ap = argparse.ArgumentParser(description="Generate a user manual, KPI glossary and HTML reference from a PBIP project.")
    ap.add_argument("--version-info", action="version", version="pbip-doc-generator " + (((HERE / "VERSION").read_text().strip()) if (HERE / "VERSION").exists() else "dev"))
    ap.add_argument("--source", default=str(HERE / "source"))
    ap.add_argument("--output", default=str(HERE / "output"))
    ap.add_argument("--glossary", default=str(HERE / "glossary" / "glossary.json"),
                    help="editable definitions file (created/updated by each run)")
    ap.add_argument("--author", default=""); ap.add_argument("--owner", default="")
    ap.add_argument("--project-code", default=""); ap.add_argument("--version", default="")
    ap.add_argument("--date-issued", default=""); ap.add_argument("--document-id", default="")
    ap.add_argument("--location", default=""); ap.add_argument("--name", default="", help="override the project name")
    ap.add_argument("--offline", action="store_true", help="do not look anything up on the web")
    ap.add_argument("--max-web-lookups", type=int, default=80)
    ap.add_argument("--ai", nargs="?", const="default", choices=["default", "anthropic", "gemini", "openai", "custom"], default=None,
                    help="optional AI mode: an AI writes the definitions nothing else could supply. Set the key up once "
                         "with --setup-ai. Only names and formula wording are sent, never report data. "
                         "Without it, definitions are drafted from the formula (offline).")
    ap.add_argument("--setup-ai", nargs="?", const="ask", choices=["ask", "anthropic", "gemini", "openai", "custom"], default=None,
                    help="one-time guided setup: paste your API key (hidden), it is tested and stored safely outside the project")
    ap.add_argument("--no-prompt", action="store_true",
                    help="do not ask which mode to use (the default when run without a keyboard, e.g. in automation)")
    ap.add_argument("--ai-status", action="store_true", help="show which AI keys are set up on this computer (masked)")
    ap.add_argument("--forget-ai-key", nargs="?", const="all", choices=["all", "anthropic", "gemini", "openai", "custom"], default=None,
                    help="remove the saved AI key from this computer")
    ap.add_argument("--ai-model", default=None, help="override the provider's default model name")
    ap.add_argument("--ai-url", default=None, help="web address of an 'other' (OpenAI-compatible) AI service; with --ai custom")
    ap.add_argument("--context", default=None,
                    help="optional text file telling the AI and the tool's checks what your company's abbreviations "
                         "mean (default: context.txt next to the glossary file; created for you when the AI had to guess)")
    ap.add_argument("--ai-send-dax", action="store_true",
                    help="also send each measure's DAX text to the AI (more accurate; check your client allows it)")
    ap.add_argument("--skip-html", action="store_true"); ap.add_argument("--skip-docx", action="store_true")
    ap.add_argument("--skip-glossary", action="store_true")
    args = ap.parse_args()

    if args.setup_ai or args.ai_status or args.forget_ai_key:
        import ai_setup
        if args.setup_ai:
            ok = ai_setup.setup(None if args.setup_ai == "ask" else args.setup_ai)
            sys.exit(0 if ok else 1)
        if args.forget_ai_key:
            ai_setup.forget(None if args.forget_ai_key == "all" else args.forget_ai_key)
            return
        ai_setup.show_status()
        return

    # Started with no mode option on a normal keyboard session: ask once which mode to use.
    session_key, session_cfg = None, {}
    if args.ai is None and not args.offline and not args.no_prompt and sys.stdin.isatty():
        import ai_setup
        choice = ai_setup.choose_mode()
        if choice["mode"] == "stop":
            sys.exit(1)
        if choice["mode"] == "ai":
            args.ai, session_key, session_cfg = choice["provider"], choice["key"], choice.get("settings", {})
        else:
            args.offline = True
            print("  Offline mode: nothing is sent anywhere; definitions come from built-in terms and each measure's formula.")

    source, output = Path(args.source), Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    report_dir, sm_dir = find_or_unzip_project(source)

    import app
    from glossary import Glossary
    from web_lookup import WebLookup
    import kpis, html_gen, manual_gen, glossary_doc_gen

    print(f"Reading {report_dir.name} + {sm_dir.name} ...")
    analysis = app.analyze_project(report_dir, sm_dir)
    project_name = args.name or app.project_name_from_dirs(report_dir, sm_dir)
    primary = [p for p in analysis["pages"] if p.get("mainNav")]
    print(f"  {len(analysis['pages'])} pages ({len(primary)} in the main navigation), "
          f"{len(analysis['allMeasures'])} measures, {len(analysis['realTables'])} tables")
    for p in analysis["pages"]:
        if not p.get("mainNav"):
            print(f"    left out of the manual: {p['displayName'].strip()!r} -- {p['nonprodFlag']}")

    import checks
    context = checks.Context(args.context or (Path(args.glossary).parent / checks.CONTEXT_NAME))
    context.learn_from_report(m.get("expression") or "" for m in analysis["measuresByName"].values())
    checker = checks.Checker(context)

    web = None
    if not args.offline:
        web = WebLookup(cache_path=Path(args.glossary).parent / "web_cache.json",
                        max_lookups=args.max_web_lookups, verbose=True)
    ai = None
    if args.ai:
        from ai_draft import AIDrafter, PROVIDERS
        import secrets_store
        if args.ai == "default":
            args.ai = secrets_store.default_provider() or next((p for p, _, _ in secrets_store.status()), None)
            if not args.ai:
                print("  --ai was given but no AI key is set up on this computer.\n"
                      "  Run once:  python run.py --setup-ai      (definitions are drafted from the formulas meanwhile)")
        ctx = f"{project_name}; pages: " + ", ".join(p["displayName"].strip() for p in primary)
        ai = AIDrafter(args.ai, api_key=session_key, model=args.ai_model or session_cfg.get("model"),
                       base_url=args.ai_url or session_cfg.get("base_url"), verbose=True, report_context=ctx, send_dax=args.ai_send_dax) \
            if args.ai else None
        if ai is not None and args.ai == "custom" and not ai.usable and ai.api_key:
            print("  --ai custom needs the service's web address and model name. Run once:  python run.py --setup-ai custom")
            ai = None
        elif ai is not None and not ai.api_key:
            print(f"  --ai {args.ai} was given but no key is set up for it, so AI drafts are skipped "
                  "(definitions are drafted from the formulas instead). Run once:  python run.py --setup-ai")
            ai = None
        elif ai is None:
            pass
        else:
            where = (" at " + urllib.parse.urlparse(ai.base_url).hostname) if args.ai == "custom" else ""
            print(f"  AI mode on ({args.ai}{where}, model {ai.model}): only names, formula wording and page names are sent"
                  + (" plus DAX text" if args.ai_send_dax else "") + " -- no report data.")
    Path(args.glossary).parent.mkdir(parents=True, exist_ok=True)
    if ai is not None:
        ai.checker = checker
    glossary = Glossary(args.glossary, web=web, ai=ai, checker=checker)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_name.replace(" ", "_"))
    glossary_docx = output / f"{safe}_KPI_Glossary.docx"
    try:
        n_edits = glossary.absorb_word_edits(glossary_docx)
    except Exception:
        n_edits = 0
    if n_edits:
        print(f"  picked up {n_edits} definition(s) you edited in the previous glossary document")
    print("Building page content" + (" (web lookups on)" if web else " (offline)") + " ...")
    page_items = kpis.build_all_items(analysis, glossary, primary)
    page_items["_extra"] = kpis.build_extra_items(analysis, glossary, primary, page_items)
    glossary.save()
    if web is not None:
        web.write_log(Path(args.glossary).parent / "web_log.txt")

    meta = {"author": args.author, "owner": args.owner, "project_code": args.project_code, "version": args.version,
            "date_issued": args.date_issued, "document_id": args.document_id, "location": args.location}

    if not args.skip_docx:
        path = output / f"{safe}_User_Manual.docx"
        _, real = build_manual_with_real_toc(manual_gen, project_name, analysis, page_items, path, meta)
        print(f"  wrote {path.name}" + ("" if real else "  (no Word/LibreOffice found: INDEX fills in when opened -- press F9)"))
    if not args.skip_glossary:
        path = output / f"{safe}_KPI_Glossary.docx"
        try:
            glossary_doc_gen.build_glossary_doc(project_name, analysis, page_items, path, meta, glossary=glossary)
            print(f"  wrote {path.name}")
        except PermissionError:
            print(f"  could NOT write {path.name} -- it is open in Word. Close it and run again.")
        glossary.save()
    if not args.skip_html:
        path = output / f"{safe}_KPI_Documentation.html"
        path.write_text(html_gen.build_html(project_name, analysis), encoding="utf-8")
        print(f"  wrote {path.name}")

    # ---- review notes: things worth a human look
    notes = []
    for p in primary:
        for it in page_items[p["id"]]:
            for var, val in it.get("fixed", []) or []:
                notes.append(f"{p['displayName'].strip()} / {it['display']}: the measure contains a fixed number written "
                             f"into it ({var.lstrip('_')} = {val:g}) rather than reading it from the data.")
    unresolved = []
    for it in [i for p in primary for i in page_items[p["id"]]] + page_items["_extra"]:
        if it["kind"] in ("card", "value") and not it.get("definition") and not it.get("also_shows") \
                and not it.get("label_logic") and it["display"] not in unresolved:
            unresolved.append(it["display"])
    all_items = [i for p in primary for i in page_items[p["id"]]] + page_items["_extra"]
    from collections import Counter
    src = Counter(i["definition"].source for i in all_items if i.get("definition"))
    n_rows = len(glossary.used)
    print(f"\nCoverage: {n_rows} indicators/measures have a row in {glossary.csv_path.name} "
          f"({len(page_items['_extra'])} of them are table/chart measures).")
    print("\nReview notes")
    print("------------")
    if web is not None:
        if web.dead:
            print(f"* Web lookup was unavailable ({web.dead_reason}); definitions found online: {web.found}.")
        else:
            print(f"* Web lookups: {web.lookups} terms searched, {web.found} definitions found "
                  "(saved to the glossary file as unverified).")
    drafts = src.get("draft", 0) + src.get("ai", 0) + src.get("web", 0)
    if drafts:
        print(f"* {drafts} definition(s) are drafts to verify (formula {src.get('draft', 0)}, AI {src.get('ai', 0)}, "
              f"web {src.get('web', 0)}) -- shaded pale yellow in the glossary.")
    if ai is not None:
        print(f"* AI drafts ({ai.provider}): {ai.drafted} written in {ai.calls} calls" + (f"; stopped: {ai.dead_reason}" if ai.dead else "")
              + ". Marked 'AI draft - please verify' in the documents.")
    if checker.rejected:
        print(f"* The tool's checks refused {len(checker.rejected)} AI draft(s); those keep the formula draft: "
              + ", ".join(t for t, _ in checker.rejected[:8]) + (" ..." if len(checker.rejected) > 8 else ""))
        why = {}
        for _, reasons in checker.rejected:
            for r in reasons:
                key = ("copied another measure's sentence" if r.startswith("almost the same") else r.split(":")[0])
                why[key] = why.get(key, 0) + 1
        print("  Reasons: " + "; ".join(f"{k} ({n})" for k, n in sorted(why.items(), key=lambda x: -x[1])) + ".")
    if checker.flagged:
        print(f"* {len(checker.flagged)} AI draft(s) contain words that are not in the report; the Source column says "
              "'Check:' with the words: " + ", ".join(t for t, _ in checker.flagged[:6]) + (" ..." if len(checker.flagged) > 6 else ""))
    if checker.guessed:
        made = context.write_template(checker.guessed)
        undefined = sorted(checker.guessed)
        print(f"* The AI had to guess what these abbreviations mean, so its drafts were refused: {', '.join(undefined)}.")
        if made:
            print(f"  I created {context.path} with them listed. Type each meaning after the = sign (for example "
                  "CB = chargeback), save, and run again.")
        else:
            print(f"  Add their meanings to {context.path} (one line each, like CB = chargeback) and run again.")
    if unresolved:
        print(f"* {len(unresolved)} indicator(s) have no definition yet: " + ", ".join(unresolved[:12]) +
              (" ..." if len(unresolved) > 12 else ""))
        print(f"  They are the yellow cells in {safe}_KPI_Glossary.docx. Type your definition over the yellow text in that")
        print("  file (replace the whole cell) and save it. Run the tool again only if you also want the wording in the")
        print("  manual and the HTML reference; it is read back from that file and kept for later runs.")
    for n in notes:
        print("* " + n)
    if not notes and not unresolved:
        print("* Nothing needs attention.")


if __name__ == "__main__":
    main()
