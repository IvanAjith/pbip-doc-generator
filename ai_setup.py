"""Guided one-time setup of the optional AI mode:  python run.py --setup-ai"""
import getpass
import sys

import secrets_store
from ai_draft import AIDrafter, PROVIDERS

LABELS = {"anthropic": "Anthropic (Claude)", "gemini": "Google Gemini", "openai": "OpenAI (ChatGPT API)"}
SAMPLE = dict(calc="Turnover multiplied by Hold %", page="Floor")


def setup(provider=None, ask=None, ask_secret=None, post=None, out=print):
    """-> True when a working key was saved."""
    ask, ask_secret = ask or input, ask_secret or getpass.getpass
    names = list(PROVIDERS)
    if provider is None:
        out("Which AI service is your key for?")
        for i, n in enumerate(names, 1):
            out(f"  {i}. {LABELS[n]}")
        choice = ask("Type 1, 2 or 3: ").strip()
        if not choice.isdigit() or not (1 <= int(choice) <= len(names)):
            out("That was not 1, 2 or 3. Nothing was saved.")
            return False
        provider = names[int(choice) - 1]
    out(f"\nPaste your {LABELS[provider]} key. It will NOT appear on screen while you type or paste.")
    out("(Right-click pastes in most Windows consoles. Press Enter when done.)")
    key = ask_secret("Key: ").strip().strip('"').strip("'")
    if len(key) < 20 or " " in key:
        out("That does not look like an API key (too short, or it contains spaces). Nothing was saved.")
        return False
    out("Testing the key with one small request ...")
    d = AIDrafter(provider, api_key=key, post=post, verbose=False,
                  report_context="Casino analytics report; pages: Floor")
    r = d.draft("Theoretical Win", **SAMPLE)
    if not r:
        why = d.dead_reason or "the service did not return a usable answer"
        out(f"The test did not work: {why}.")
        if ask("Save the key anyway? (y/n): ").strip().lower() != "y":
            out("Nothing was saved.")
            return False
    else:
        out("Test definition received:  " + r["text"])
    where = secrets_store.save_key(provider, key)
    out(f"\nSaved in {where}.")
    out("It is outside the project folder, so it can never be committed to GitHub.")
    out("From now on, run:   python run.py --ai")
    return True


def show_status(out=print):
    rows = secrets_store.status()
    if not rows:
        out("No AI key is set up on this computer. Run:  python run.py --setup-ai")
        return
    dp = secrets_store.default_provider()
    for prov, src, masked in rows:
        out(f"{LABELS[prov]}: key {masked} found in {src}" + ("   [default]" if prov == dp else ""))
    out("(Keys are never shown in full.)")


def forget(provider=None, out=print):
    targets = [provider] if provider else list(PROVIDERS)
    gone = [p for p in targets if secrets_store.delete_key(p)]
    out("Removed the saved key for: " + ", ".join(LABELS[p] for p in gone) if gone else "No saved key to remove.")
    if any(secrets_store.get_key(p)[0] for p in targets):
        out("Note: a key is still set through an environment variable; remove that in your system settings.")


def _pick_provider(ask, out):
    names = list(PROVIDERS)
    out("Which AI service is your key for?")
    for i, n in enumerate(names, 1):
        out(f"  {i}. {LABELS[n]}")
    c = ask("Type 1, 2 or 3: ").strip()
    return names[int(c) - 1] if c.isdigit() and 1 <= int(c) <= len(names) else None


def choose_mode(ask=None, ask_secret=None, post=None, out=print):
    """The question asked when run.py starts with no options.
    -> {"mode": "offline"} or {"mode": "ai", "provider": ..., "key": ...}"""
    ask, ask_secret = ask or input, ask_secret or getpass.getpass
    out("")
    out("How should the glossary definitions be written?")
    out("  1. AI mode      (needs an API key - choose this if you have one)")
    out("  2. Offline mode (no key and no internet - definitions are drafted from each measure's DAX formula)")
    while True:
        c = ask("Type 1 or 2: ").strip()
        if c in ("1", "2"):
            break
        out("Please type 1 or 2.")
    if c == "2":
        return {"mode": "offline"}

    # --- AI mode: use a saved key if there is one
    saved = secrets_store.status()
    if saved:
        dp = secrets_store.default_provider()
        prov, src, masked = next((r for r in saved if r[0] == dp), saved[0])
        out(f"\nA saved {LABELS[prov]} key ({masked}) was found on this computer.")
        if ask("Press Enter to use it, or type N to use a different key: ").strip().lower() != "n":
            return {"mode": "ai", "provider": prov, "key": secrets_store.get_key(prov)[0]}

    for attempt in range(3):
        prov = _pick_provider(ask, out)
        if prov is None:
            out("That was not a valid choice.")
            continue
        out(f"\nPaste your {LABELS[prov]} key. It will NOT appear on screen while you type or paste.")
        out("(Right-click pastes in most Windows consoles. Press Enter when done.)")
        key = ask_secret("Key: ").strip().strip('"').strip("'")
        if len(key) < 20 or " " in key:
            out("That does not look like an API key (too short, or it contains spaces).")
            continue
        out("Testing the key with one small request ...")
        d = AIDrafter(prov, api_key=key, post=post, verbose=False, report_context="Casino analytics report; pages: Floor")
        r = d.draft("Theoretical Win", **SAMPLE)
        if not r:
            out(f"The test did not work: {d.dead_reason or 'the service did not return a usable answer'}.")
            if ask("Type 1 to try another key, or 2 to continue in offline mode: ").strip() == "2":
                return {"mode": "offline"}
            continue
        out("Key works. Sample definition:  " + r["text"])
        a = ask("Save this key on this computer so you are not asked again? (Enter = yes, n = no, e.g. on a shared computer): ")
        if a.strip().lower() != "n":
            out("Saved in " + secrets_store.save_key(prov, key) + ". It is outside the project folder, so it cannot reach GitHub.")
        else:
            out("Not saved. The key is used for this run only.")
        return {"mode": "ai", "provider": prov, "key": key}
    out("No working key was entered, so this run continues in offline mode.")
    return {"mode": "offline"}
