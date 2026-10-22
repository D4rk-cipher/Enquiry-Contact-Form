"""Configuration loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # Ensure sane defaults
    profile = raw.get("profile") or {}
    if not profile.get("full_name") and (profile.get("first_name") or profile.get("last_name")):
        profile["full_name"] = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        raw["profile"] = profile

    settings = raw.get("settings") or {}
    settings.setdefault("headless", False)
    settings.setdefault("timeout_ms", 30_000)
    settings.setdefault("delay_between_domains_sec", 10.0)
    settings.setdefault("max_retries_per_domain", 1)
    settings.setdefault("screenshot_on_every_attempt", True)
    settings.setdefault("screenshot_on_failure_only", False)
    settings.setdefault("user_agent", None)
    raw["settings"] = settings

    raw.setdefault("default_message", "")
    raw.setdefault("message_templates", {})
    raw.setdefault("contact_paths", [
        "/contact", "/contact-us", "/contactus", "/get-in-touch",
        "/getintouch", "/about/contact", "/en/contact",
    ])
    raw.setdefault("contact_keywords", [
        "contact", "get in touch", "reach us", "reach out",
        "enquire", "inquiry", "talk to us",
    ])

    # Normalize paths
    raw["contact_paths"] = [
        p if str(p).startswith("/") else f"/{p}" for p in raw["contact_paths"]
    ]

    return raw


def get_message(config: dict[str, Any], industry: str | None = None) -> str:
    templates = config.get("message_templates") or {}
    if industry and industry in templates:
        return str(templates[industry]).strip()
    return str(config.get("default_message") or "").strip()


def get_profile(config: dict[str, Any]) -> dict[str, str]:
    return {k: str(v or "") for k, v in (config.get("profile") or {}).items()}
