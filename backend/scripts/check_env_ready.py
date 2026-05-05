#!/usr/bin/env python3
"""
Dry-run: report missing configuration for the current APP_MODE.
Does not print secret values. Run from the backend directory:

  cd backend && python scripts/check_env_ready.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def main() -> int:
    from app.config import Settings, validate_startup_config

    s = Settings()
    mode = (s.app_mode or "").strip().upper()
    print(f"APP_MODE={mode or '(empty)'}")

    missing: list[str] = []

    if mode in {"WEBULL_PAPER", "WEBULL_LIVE"}:
        if not (s.webull_app_key or "").strip():
            missing.append("WEBULL_APP_KEY")
        if not (s.webull_app_secret or "").strip():
            missing.append("WEBULL_APP_SECRET")
        if not (s.webull_account_id or "").strip():
            missing.append("WEBULL_ACCOUNT_ID")
        if not (s.option_watchlist or "").strip():
            missing.append("OPTION_WATCHLIST")

    if s.require_api_key and not (s.api_admin_key or "").strip():
        missing.append("API_ADMIN_KEY (required when REQUIRE_API_KEY=true)")

    if missing:
        print("Missing:", ", ".join(missing))
        return 1

    if s.min_entry_confidence > 0 and not (s.claude_api_key or "").strip():
        print(
            "Note: MIN_ENTRY_CONFIDENCE>0 but CLAUDE_API_KEY is empty — "
            "entry confidence gating may not behave as intended."
        )

    try:
        validate_startup_config()
    except RuntimeError as exc:
        print("validate_startup_config failed:", exc)
        return 1

    print("OK: startup validation passes for this .env (process not started).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
