"""compare_test.py -- TEMPORARY, for testing only.  One command does everything:

    python compare_test.py

  1. runs the tool in offline mode  -> compare_test\\offline\\output   (its own glossary in compare_test\\offline\\glossary)
  2. runs the tool in AI mode       -> compare_test\\ai\\output        (its own glossary in compare_test\\ai\\glossary)
  3. writes the comparison          -> compare_test\\Offline_vs_AI.docx (and .xlsx / .csv)

Each run writes its own Needs_Your_Clarification.txt. Answer in either file (or both), save, and run the same command again:
an answer typed in one file is used by both runs, so nothing has to be typed twice. Nothing here is part of the normal tool.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=str(HERE / "source"), help="folder with the PBIP project (default: source)")
    ap.add_argument("--folder", default=str(HERE / "compare_test"), help="where everything is stored (default: compare_test)")
    args = ap.parse_args()
    import clarify
    import compare_modes

    root = Path(args.folder).resolve()
    runs = {k: {"out": root / k / "output", "gl": root / k / "glossary"} for k in ("offline", "ai")}
    for r in runs.values():
        r["out"].mkdir(parents=True, exist_ok=True)
        r["gl"].mkdir(parents=True, exist_ok=True)

    # keep a copy of what was typed in both clarification files BEFORE the first run rewrites them
    snap = {}
    for k, r in runs.items():
        f = r["out"] / clarify.NAME
        if f.exists():
            snap[k] = root / f"_answers_{k}.txt"
            shutil.copyfile(f, snap[k])
    answers = [str(p) for p in snap.values()]

    for k, flags in (("offline", ["--no-prompt", "--offline"]), ("ai", ["--ai", "--offline"])):
        r = runs[k]
        print("\n" + "=" * 78 + f"\n  {k.upper()} RUN\n" + "=" * 78, flush=True)
        cmd = [sys.executable, str(HERE / "run.py"), *flags, "--source", args.source, "--output", str(r["out"]),
               "--glossary", str(r["gl"] / "glossary.json")]
        if answers:
            cmd += ["--answers", *answers]
        code = subprocess.call(cmd)
        if code != 0:
            sys.exit(f"\nThe {k} run stopped (exit code {code}). Fix that first, then run  python compare_test.py  again.")

    print("\n" + "=" * 78 + "\n  COMPARISON\n" + "=" * 78)
    paths, n, changed = compare_modes.write_all(runs["offline"]["gl"], runs["ai"]["gl"], str(root / "Offline_vs_AI"))
    print(f"Compared {n} KPIs: {n - changed} read the same, {changed} differ.")
    print("\nOpen this first:")
    print(f"  {Path(paths[0]).resolve()}")
    print(f"(also {Path(paths[1]).resolve()})")

    todo = []
    for k, r in runs.items():
        f = r["out"] / clarify.NAME
        if f.exists() and "NO CLARIFICATION NEEDED" not in f.read_text(encoding="utf-8", errors="ignore"):
            todo.append(f)
    print()
    if todo:
        print("CLARIFICATION NEEDED. Answer on the lines that start with >>> in:")
        for f in todo:
            print(f"  {f}")
        print("Save, then run  python compare_test.py  again. An answer typed in one file is used by both runs.")
    else:
        print("No clarification needed in either run. The three documents of each run are in:")
        for r in runs.values():
            print(f"  {r['out']}")


if __name__ == "__main__":
    main()
