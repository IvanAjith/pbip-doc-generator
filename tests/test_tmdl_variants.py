"""Run:  python tests/test_tmdl_variants.py
Real Power BI / editor-saved TMDL files differ from tidy ones: byte-order mark, Windows line endings, descriptions ('///')
above the table line, quoted names. None of that may crash the reader or lose a table."""
import subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import app
from run import find_or_unzip_project

tmp = Path(tempfile.mkdtemp())
subprocess.run([sys.executable, str(ROOT / "tests/make_synthetic_projects.py"), str(tmp / "s")], check=True, capture_output=True)
proj = tmp / "s" / "gaming"
rd, sm = find_or_unzip_project(proj)
before = app.analyze_project(rd, sm)
names_before = sorted(t["name"] for t in before["realTables"])
measures_before = sorted(m["name"] for m in before["allMeasures"])

files = sorted((sm / "definition" / "tables").glob("*.tmdl"))
# 1 byte-order mark + Windows line endings on one file
t = files[0].read_text(encoding="utf-8")
files[0].write_bytes(b"\xef\xbb\xbf" + t.replace("\n", "\r\n").encode("utf-8"))
# 2 description lines and a blank line before the table line
files[1].write_text("/// Describes the table\n/// second line\n\n" + files[1].read_text(encoding="utf-8"), encoding="utf-8")
# 3 a name with a space written in quotes, in a copy of a table
extra = (sm / "definition" / "tables" / "Net Promoter Score.tmdl")
extra.write_text("﻿/// survey\ntable 'Net Promoter Score'\n\tlineageTag: x\n\n\tcolumn Score\n\t\tdataType: int64\n\t\tsourceColumn: Score\n", encoding="utf-8")
# 4 a file where the table line cannot be read at all: the file name is used, never None
(sm / "definition" / "tables" / "Odd.tmdl").write_text("\tcolumn A\n\t\tdataType: string\n", encoding="utf-8")

after = app.analyze_project(rd, sm)
names = [t["name"] for t in after["realTables"]]
assert all(isinstance(n, str) and n for n in names), names
assert set(names_before) <= set(names) and "Net Promoter Score" in names and "Odd" in names, names
assert sorted(m["name"] for m in after["allMeasures"]) == measures_before
print("ALL TMDL VARIANT TESTS PASSED")
