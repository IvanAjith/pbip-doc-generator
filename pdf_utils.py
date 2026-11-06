"""
pdf_utils.py -- best-effort docx->PDF conversion and heading page-lookup,
used to give the Word manual's INDEX real, populated page numbers instead
of a "press F9" field. Every part of this is optional: if no converter is
available, run.py falls back to the dynamic Word TOC field automatically
-- this module never raises past its public functions; it returns None to
signal "couldn't do it."
"""
import shutil
import subprocess
from pathlib import Path


def convert_to_pdf(docx_path: Path, pdf_dir: Path, timeout=90):
    """Try, in order: Microsoft Word (via docx2pdf, Windows/macOS with Word
    installed) then LibreOffice/OpenOffice (soffice, any platform, if on
    PATH). Returns the produced PDF path, or None if neither is available
    or conversion failed."""
    pdf_dir.mkdir(parents=True, exist_ok=True)

    try:
        from docx2pdf import convert as _docx2pdf_convert
        target = pdf_dir / (docx_path.stem + ".pdf")
        _docx2pdf_convert(str(docx_path), str(target))
        if target.exists() and target.stat().st_size > 0:
            return target
    except Exception:
        pass  # Word not installed / not on Windows or macOS / conversion failed

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        try:
            subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(pdf_dir), str(docx_path)],
                capture_output=True, timeout=timeout, check=False,
            )
            target = pdf_dir / (docx_path.stem + ".pdf")
            if target.exists() and target.stat().st_size > 0:
                return target
        except Exception:
            pass

    return None


def find_heading_pages(pdf_path: Path, headings: list, start_after_text: str = None) -> dict:
    """Return {heading_text: 1-based_page_number} for every heading found
    verbatim on some page of the PDF. Uses pypdf, a pure-Python dependency
    -- no system PDF tool required. Whitespace is normalized on both sides
    before matching, since PDF text extraction doesn't always preserve
    exact run spacing.

    If start_after_text is given, pages up to and including the first page
    containing it are skipped entirely before matching begins. This
    matters because the INDEX table itself contains every heading's text
    (split across its own cells) -- without skipping past it, a heading is
    liable to "match" on the INDEX's own page rather than where it
    actually appears in the body.

    Returns {} if pypdf isn't installed or the PDF can't be read."""
    import re

    try:
        from pypdf import PdfReader
    except Exception:
        return {}

    try:
        reader = PdfReader(str(pdf_path))
    except Exception:
        return {}

    def norm(s):
        return re.sub(r"\s+", " ", s).strip()

    headings_norm = list(dict.fromkeys(norm(h) for h in headings))  # de-dup, preserve order
    orig_by_norm = {}
    for h in headings:
        orig_by_norm.setdefault(norm(h), h)

    start_marker = norm(start_after_text) if start_after_text else None
    past_marker = start_marker is None

    result = {}
    remaining = list(headings_norm)
    for page_no, page in enumerate(reader.pages, start=1):
        if not remaining:
            break
        try:
            text = norm(page.extract_text() or "")
        except Exception:
            continue
        if not past_marker:
            if start_marker in text:
                past_marker = True
            continue
        still_missing = []
        for h in remaining:
            if h in text and orig_by_norm[h] not in result:
                result[orig_by_norm[h]] = page_no
            else:
                still_missing.append(h)
        remaining = still_missing
    return result
