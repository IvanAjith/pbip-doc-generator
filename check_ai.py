"""Checks that the optional AI mode works from this computer.

    python check_ai.py gemini          (or: anthropic, openai)
"""
import sys
from ai_draft import AIDrafter, PROVIDERS, key_from_env

provider = sys.argv[1] if len(sys.argv) > 1 else "anthropic"
if provider not in PROVIDERS:
    print("Choose one of:", ", ".join(PROVIDERS)); sys.exit(1)
if not key_from_env(provider):
    print(f"No key found. Set {' or '.join(PROVIDERS[provider]['env'])} first (see README)."); sys.exit(1)
d = AIDrafter(provider, report_context="Casino analytics report; pages: Slots, Tables")
r = d.draft("Theoretical Win", calc="Turnover multiplied by Hold %", page="Slots")
print("PROVIDER:", provider, "| MODEL:", d.model)
print("RESULT:", r["text"] if r else "no result")
print("Switched off:", d.dead, d.dead_reason)
print("OK -- AI mode works." if r else "NOT working -- send me this whole output.")
