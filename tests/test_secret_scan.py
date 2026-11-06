"""Run:  python tests/test_secret_scan.py   Fails if anything that looks like an API key is in a file Git would publish."""
import re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = [r"sk-ant-[A-Za-z0-9_-]{20,}", r"sk-[A-Za-z0-9_-]{32,}", r"sk-proj-[A-Za-z0-9_-]{20,}",
            r"AIza[0-9A-Za-z_-]{30,}", r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{24,}['\"]"]
SKIP = {"test_secrets.py", "test_secret_scan.py", "test_menu.py"}       # these contain obviously fake sample keys


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.split("\n")
        return [ROOT / f for f in out if f]
    except Exception:
        return [p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]


bad = []
for f in tracked_files():
    if f.name in SKIP or f.suffix in {".docx", ".pdf", ".png", ".zip", ".pyc"} or not f.exists():
        continue
    try:
        text = f.read_text(encoding="utf-8")
    except Exception:
        continue
    for pat in PATTERNS:
        if re.search(pat, text):
            bad.append(f"{f.relative_to(ROOT)} matches {pat}")
assert not bad, "possible API key in the repository:\n" + "\n".join(bad)
# the git-ignore must keep key files and outputs out
gi = (ROOT / ".gitignore").read_text()
for need in (".env", "*.key", "source/*", "output/*", "glossary/*"):
    assert need in gi, f".gitignore is missing {need}"
print("SECRET SCAN PASSED")
