"""Where API keys live. Never inside the project folder, so a key can never be committed to Git.

Lookup order for a provider's key:
  1. the provider's environment variable (ANTHROPIC_API_KEY / GEMINI_API_KEY / OPENAI_API_KEY)
  2. the operating system's secure store (Windows Credential Manager, macOS Keychain, Linux Secret Service),
     if the optional `keyring` package is installed
  3. a private file in your own user folder:  ~/.pbip_doc_generator/config.json  (readable only by you on
     macOS/Linux; on Windows it sits in your user profile, which other users cannot open)

Keys are never printed, logged or written anywhere else.
"""
import json
import os
import stat
from pathlib import Path

SERVICE = "pbip-doc-generator"
ENV_NAMES = {
    "anthropic": ["ANTHROPIC_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
}


def home_dir():
    base = os.environ.get("PBIP_DOC_GENERATOR_HOME")
    return Path(base) if base else Path.home() / ".pbip_doc_generator"


def _config_path():
    return home_dir() / "config.json"


def _keyring():
    if os.environ.get("PBIP_DOC_GENERATOR_NO_KEYRING"):
        return None
    try:
        import keyring
        keyring.get_keyring()
        return keyring
    except Exception:
        return None


def _read_config():
    try:
        return json.loads(_config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_config(cfg):
    d = home_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, stat.S_IRWXU)
    except OSError:
        pass
    path = _config_path()
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)     # created private from the start
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def get_key(provider):
    """-> (key, source) where source is 'environment' | 'secure store' | 'private file' | None."""
    for name in ENV_NAMES.get(provider, []):
        if os.environ.get(name):
            return os.environ[name].strip(), "environment variable " + name
    kr = _keyring()
    if kr is not None:
        try:
            k = kr.get_password(SERVICE, provider)
            if k:
                return k, "your computer's secure store"
        except Exception:
            pass
    k = _read_config().get("keys", {}).get(provider)
    if k:
        return k, f"private file {_config_path()}"
    return "", None


def save_key(provider, key, make_default=True):
    """-> where it was stored."""
    key = key.strip()
    where = None
    kr = _keyring()
    if kr is not None:
        try:
            kr.set_password(SERVICE, provider, key)
            where = "your computer's secure store"
        except Exception:
            where = None
    cfg = _read_config()
    if where is None:
        cfg.setdefault("keys", {})[provider] = key
        where = f"a private file in your user folder ({_config_path()})"
    else:
        cfg.get("keys", {}).pop(provider, None)
    if make_default:
        cfg["default_provider"] = provider
    _write_config(cfg)
    return where


def delete_key(provider):
    removed = False
    kr = _keyring()
    if kr is not None:
        try:
            kr.delete_password(SERVICE, provider)
            removed = True
        except Exception:
            pass
    cfg = _read_config()
    if cfg.get("keys", {}).pop(provider, None):
        removed = True
    if cfg.get("default_provider") == provider:
        cfg.pop("default_provider")
    if removed or cfg:
        _write_config(cfg)
    return removed


def default_provider():
    return _read_config().get("default_provider")


def mask(key):
    return ("..." + key[-4:]) if key and len(key) >= 8 else "(set)"


def status():
    """[(provider, source, masked key)] for every provider that has a key."""
    out = []
    for p in ENV_NAMES:
        k, src = get_key(p)
        if k:
            out.append((p, src, mask(k)))
    return out
