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


def _ask_list(ask, out):
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
        return None, "that is not a usable web address (it must start with https://; http:// is accepted only for this computer)"
    model = ask("Model name: ").strip()
    if not model or " " in model:
        return None, "the model name is missing or contains spaces"
    return {"base_url": url, "model": model}, ""


def _test(prov, key, settings, post):
    """One small request. -> (sample text or None, reason)"""
    d = AIDrafter(prov, api_key=key, post=post, verbose=False, report_context="Casino analytics report; pages: Floor",
                  base_url=settings.get("base_url"), model=settings.get("model"))
    r = d.draft("Theoretical Win", **SAMPLE)
    if r and prov != "custom" and d.model != PROVIDERS[prov]["model"]:
        settings["model"] = d.model            # a fallback model name was the one that worked: remember it
    return (r["text"] if r else None), (d.last_error or "the service did not return a usable answer")


def _acquire(provider, ask, ask_secret, post, out):
    """One attempt: paste the key, recognise the service, test. -> (result, reason). Never prints the key."""
    out("\nPaste your API key. It will NOT appear on screen while you type or paste.")
    out("(Right-click pastes in most Windows consoles. Press Enter when done.)")
    key = ask_secret("Key: ").strip().strip('"').strip("'")
    if len(key) < 20 or " " in key:
        return None, "that does not look like an API key (too short, or it contains spaces)"
    guess = None
    prov = provider
    if prov is None:
        guess = detect_provider(key)
        if guess:
            prov = guess
            out(f"\nRecognised as a {_label(prov)} key.")
        else:
            prov = _ask_list(ask, out)
            if prov is None:
                return None, "that was not a valid choice"
    settings = {}
    if prov == "custom":
        settings, why = _ask_custom_settings(ask, out)
        if not settings:
            return None, why
    out("Testing the key with one small request ...")
    sample, reason = _test(prov, key, settings, post)
    if sample is None and guess == "openai" and prov == "openai":
        # many other services also start their keys with "sk-": offer the 'Other' route before giving up
        out(f"The test did not work: {reason}.")
        if _yes_no(ask, "Could this key belong to a different service (for example Groq, DeepSeek, Azure)? (y/n): "):
            settings, why = _ask_custom_settings(ask, out)
            if not settings:
                return None, why
            prov = "custom"
            out("Testing the key with one small request ...")
            sample, reason = _test(prov, key, settings, post)
    if sample is None:
        return None, reason
    out("Key works. Sample definition:  " + sample)
    return {"provider": prov, "key": key, "settings": settings}, ""


def _yes_no(ask, prompt):
    while True:
        a = ask(prompt).strip().lower()
        if a in ("y", "yes"):
            return True
        if a in ("n", "no"):
            return False


def _save(res, out):
    where = secrets_store.save_key(res["provider"], res["key"])
    if res["settings"]:
        secrets_store.save_settings(res["provider"], **res["settings"])
    out(f"Saved in {where}.")
    out("It is outside the project folder, so it can never be committed to GitHub.")


def setup(provider=None, ask=None, ask_secret=None, post=None, out=print):
    """One-time setup on its own (python run.py --setup-ai). -> True when a working key was saved."""
    ask, ask_secret = ask or input, ask_secret or getpass.getpass
    for _ in range(3):
        res, reason = _acquire(provider, ask, ask_secret, post, out)
        if res:
            _save(res, out)
            out("From now on, run:   python run.py")
            return True
        out(f"\nThe API key was not accepted: {reason}.")
        if not _yes_no(ask, "Try again? (y/n): "):
            break
    out("Nothing was saved.")
    return False


def _offline_or_stop(ask, out, reason, saved_key=False):
    out(f"\nThe API key was not accepted: {reason}.")
    if _yes_no(ask, "Would you like to continue in offline mode instead (definitions drafted from the DAX formulas)? (y/n): "):
        return {"mode": "offline"}
    out("\nStopped. Invalid API key - no documents were generated.")
    out("Run  python run.py  again to try a new key" + (" (type N when asked about the saved key)." if saved_key else "."))
    return {"mode": "stop"}


def choose_mode(ask=None, ask_secret=None, post=None, out=print):
    """The question asked when run.py starts with no options.
    -> {"mode": "offline"} | {"mode": "stop"} | {"mode": "ai", "provider", "key", "settings"}"""
    ask, ask_secret = ask or input, ask_secret or getpass.getpass
    out("")
    out("Do you have an AI API key?")
    out("  1. Yes - AI mode      (paste the key; the AI helps write the definitions)")
    out("  2. No  - Offline mode (no key and no internet; definitions are drafted from each measure's DAX formula)")
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
            key, st = secrets_store.get_key(prov)[0], secrets_store.get_settings(prov)
            out("Testing the saved key with one small request ...")
            sample, reason = _test(prov, key, st, post)
            if sample is None:
                return _offline_or_stop(ask, out, reason, saved_key=True)
            return {"mode": "ai", "provider": prov, "key": key, "settings": st}

    res, reason = _acquire(None, ask, ask_secret, post, out)
    if not res:
        return _offline_or_stop(ask, out, reason)
    if _yes_no(ask, "Save this key on this computer so you are not asked again? (y/n - choose n on a shared computer): "):
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
