"""Run:  python tests/test_compare_modes.py   -- two runs side by side (offline vs AI)."""
import sys, csv, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import compare_modes as CM
H = ["Term", "Your definition (type here)", "Suggested definition", "Where the suggestion came from", "Page", "Report formula (for reference)"]
def make(folder, rows):
    folder.mkdir()
    with open(folder / CM.CSV_NAME, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(H); w.writerows(rows)
t = Path(tempfile.mkdtemp())
make(t / "a", [["NPS", "", "Built-in text.", "Built-in glossary", "P1", ""], ["Hold", "", "From formula.", "Draft built from the formula", "P1", "x"],
               ["Only A", "", "Text.", "Built-in glossary", "P2", ""]])
make(t / "b", [["NPS", "", "Built-in text.", "Built-in glossary", "P1", ""], ["Hold", "", "An AI sentence.", "AI draft (gemini)", "P1", "x"],
               ["Typed", "My words.", "", "", "P2", ""]])
rows, ca, cb = CM.compare(t / "a", t / "b")
by = {r["term"]: r for r in rows}
assert len(rows) == 4 and by["NPS"]["same"] and not by["Hold"]["same"]
assert by["Hold"]["a_kind"] == "Draft from the formula" and by["Hold"]["b_kind"] == "AI draft"
assert by["Only A"]["b_kind"] == "(not in this run)" and by["Typed"]["b_kind"] == "Your own"
path, n, changed = CM.write(t / "a", t / "b", str(t / "x.xlsx"))
assert n == 4 and changed == 3 and Path(path).exists()
print("compare modes tests passed")
