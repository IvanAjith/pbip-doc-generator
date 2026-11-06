"""Guided one-time setup of the optional AI mode:  python run.py --setup-ai"""
import getpass
import sys

import secrets_store
from ai_draft import AIDrafter, PROVIDERS

LABELS = {"anthropic": "Anthropic (Claude)", "gemini": "Google Gemini", "openai": "OpenAI (ChatGPT API)"}
SAMPLE = dict(calc="Turnover multiplied by Hold %", page="Floor")


def setup(provider=None, ask=input, ask_secret=getpass.getpass, post=None, out=print):
    """-> True when a working key was saved."""
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
