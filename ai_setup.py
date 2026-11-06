"""Guided setup of the optional AI mode.

  python run.py --setup-ai      one-time setup on its own
  python run.py                 asks "1. AI mode / 2. Offline mode" (see choose_mode)

You paste the key; the tool recognises the service from how the key starts (or asks, and supports "Other":
any service that speaks the OpenAI chat format), makes one small test request, and only then offers to save it.
"""
import getpass
import urllib.parse

import secrets_store
from ai_draft import AIDrafter, PROVIDERS, clean_base_url, detect_provider

LABELS = {"anthropic": "Anthropic (Claude)", "gemini": "Google Gemini", "openai": "OpenAI (ChatGPT API)",
          "custom": "Other (OpenAI-compatible service)"}
ORDER = ["anthropic", "gemini", "openai", "custom"]
SAMPLE = dict(calc="Turnover multiplied by Hold %", page="Floor")


def _label(p):
    return LABELS.get(p, p)


def _ask_service(ask, out, detected):
    """-> provider name or None. Enter accepts the detected service."""
    if detected:
        out(f"\nThis key looks like a {_label(detected)} key.")
        c = ask("Press Enter if that is right, or type 1-4 to choose another (1 Anthropic, 2 Gemini, 3 OpenAI, 4 Other): ").strip()
        if c == "":
            return detected
    else:
        out("\nWhich service is this key for?")
        for i, n in enumerate(ORDER, 1):
            out(f"  {i}. {_label(n)}")
        out("  (Not in the list? Choose 4. Any service that works like OpenAI's will do - ask IT for its web address and model name.)")
        c = ask("Type 1, 2, 3 or 4: ").strip()
    return ORDER[int(c) - 1] if c.isdigit() and 1 <= int(c) <= len(ORDER) else None


def _ask_custom_settings(ask, out):
    out("\nFor an 'Other' service, ask IT for two things:")
    out("  - its web address, e.g.  https://api.groq.com/openai/v1  (or the full .../chat/completions address)")
    out("  - the model name, e.g.  llama-3.3-70b-versatile")
    url = ask("Web address: ").strip()
    if not clean_base_url(url):
        out("That is not a usable web address. It must start with https:// (http:// is accepted only for this computer).")
        return None
    model = ask("Model name: ").strip()
    if not model or " " in model:
        out("The model name is missing or contains spaces.")
        return None
    return {"base_url": url, "model": model}


def _acquire(provider, ask, ask_secret, post, out, attempts=3):
    """Paste + recognise + test. -> {"provider","key","settings"} or None. Never prints the key."""
    for _ in range(attempts):
        out(f"\nPaste your API key. It will NOT appear on screen while you type or paste.")
        out("(Right-click pastes in most Windows consoles. Press Enter when done.)")
        key = ask_secret("Key: ").strip().strip('"').strip("'")
        if len(key) < 20 or " " in key:
            out("That does not look like an API key (too short, or it contains spaces).")
            continue
        prov = provider or _ask_service(ask, out, detect_provider(key))
        if prov is None:
            out("That was not a valid choice.")
            continue
        settings = {}
        if prov == "custom":
            settings = _ask_custom_settings(ask, out) or {}
            if not settings:
                continue
        out("Testing the key with one small request ...")
        d = AIDrafter(prov, api_key=key, post=post, verbose=False, report_context="Casino analytics report; pages: Floor",
                      base_url=settings.get("base_url"), model=settings.get("model"))
        r = d.draft("Theoretical Win", **SAMPLE)
        if r:
            out("Key works. Sample definition:  " + r["text"])
            return {"provider": prov, "key": key, "settings": settings}
        out(f"The test did not work: {d.dead_reason or 'the service did not return a usable answer'}.")
        out("Check that the key, the service and (for Other) the web address and model name are right.")
        if ask("Type 1 to try again, or 2 to stop: ").strip() == "2":
            return None
    return None


def _save(res, out):
    where = secrets_store.save_key(res["provider"], res["key"])
    if res["settings"]:
        secrets_store.save_settings(res["provider"], **res["settings"])
    out(f"Saved in {where}.")
    out("It is outside the project folder, so it can never be committed to GitHub.")


def setup(provider=None, ask=None, ask_secret=None, post=None, out=print):
    """One-time setup on its own. -> True when a working key was saved."""
    ask, ask_secret = ask or input, ask_secret or getpass.getpass
    res = _acquire(provider, ask, ask_secret, post, out)
    if not res:
        out("Nothing was saved.")
        return False
    _save(res, out)
    out("From now on, run:   python run.py")
    return True


def choose_mode(ask=None, ask_secret=None, post=None, out=print):
    """The question asked when run.py starts with no options.
    -> {"mode": "offline"} or {"mode": "ai", "provider", "key", "settings"}"""
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

    saved = secrets_store.status()
    if saved:
        dp = secrets_store.default_provider()
        prov, _src, masked = next((r for r in saved if r[0] == dp), saved[0])
        out(f"\nA saved {_label(prov)} key ({masked}) was found on this computer.")
        if ask("Press Enter to use it, or type N to use a different key: ").strip().lower() != "n":
            return {"mode": "ai", "provider": prov, "key": secrets_store.get_key(prov)[0],
                    "settings": secrets_store.get_settings(prov)}

    res = _acquire(None, ask, ask_secret, post, out)
    if not res:
        out("\nNo working key was entered, so this run continues in offline mode.")
        return {"mode": "offline"}
    a = ask("Save this key on this computer so you are not asked again? (Enter = yes, n = no, e.g. on a shared computer): ")
    if a.strip().lower() != "n":
        _save(res, out)
    else:
        out("Not saved. The key is used for this run only.")
    return {"mode": "ai", **res}


def show_status(out=print):
    rows = secrets_store.status()
    if not rows:
        out("No AI key is set up on this computer. Run:  python run.py --setup-ai")
        return
    dp = secrets_store.default_provider()
    for prov, src, masked in rows:
        extra = ""
        if prov == "custom":
            st = secrets_store.get_settings("custom")
            host = urllib.parse.urlparse(st.get("base_url", "")).hostname or "(web address not set)"
            extra = f", service {host}, model {st.get('model') or '(not set)'}"
        out(f"{_label(prov)}: key {masked} found in {src}{extra}" + ("   [default]" if prov == dp else ""))
    out("(Keys are never shown in full.)")


def forget(provider=None, out=print):
    targets = [provider] if provider else list(PROVIDERS)
    gone = [p for p in targets if secrets_store.delete_key(p)]
    out("Removed the saved key for: " + ", ".join(_label(p) for p in gone) if gone else "No saved key to remove.")
    if any(secrets_store.get_key(p)[0] for p in targets):
        out("Note: a key is still set through an environment variable; remove that in your system settings.")
