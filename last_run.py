"""last_run.py -- remembers which mode the previous run used, so that `python run.py` can carry on in the same mode while
clarification questions are still waiting, and ask again only when everything is finished.

The note is a small file next to the glossary file (last_run.json). It never holds a key."""
import json
from datetime import datetime
from pathlib import Path

NAME = "last_run.json"


def path_for(glossary_file):
    return Path(glossary_file).parent / NAME


def write(path, mode, provider="", pending=0):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({"mode": mode, "provider": provider or "", "pending": int(pending or 0),
                                          "when": datetime.now().strftime("%d/%m/%Y %H:%M")}, indent=1), encoding="utf-8")
    except OSError:
        pass


def read(path):
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return d if d.get("mode") in ("offline", "ai") else None
    except (OSError, ValueError):
        return None


def resume(path):
    """-> {'mode', 'provider', 'pending', 'when'} when the last run left questions waiting, else None (ask the mode again)."""
    d = read(path)
    return d if d and d.get("pending", 0) > 0 else None
