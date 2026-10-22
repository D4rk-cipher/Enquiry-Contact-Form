"""Configuration loader and template helpers."""

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

    profile = raw.get("profile") or {}
    if not profile.get("full_name") and (profile.get("first_name") or profile.get("last_name")):
        profile["full_name"] = (
            f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        )
        raw["profile"] = profile

    settings = raw.get("settings") or {}
    settings.setdefault("headless", False)
    settings.setdefault("timeout_ms", 30_000)
    settings.setdefault("delay_between_domains_sec", 10.0)
    settings.setdefault("max_retries_per_domain", 1)
    settings.setdefault("screenshot_on_success_only", True)
    settings.setdefault("user_agent", None)
    raw["settings"] = settings

    raw.setdefault("default_message", "")
    raw.setdefault("message_templates", {})
    raw.setdefault(
        "contact_paths",
        [
            "/contact",
            "/contact-us",
            "/contactus",
            "/get-in-touch",
            "/getintouch",
            "/about/contact",
            "/en/contact",
        ],
    )
    raw.setdefault(
        "contact_keywords",
        [
            "contact",
            "get in touch",
            "reach us",
            "reach out",
            "enquire",
            "inquiry",
            "talk to us",
        ],
    )

    raw["contact_paths"] = [
        p if str(p).startswith("/") else f"/{p}" for p in raw["contact_paths"]
    ]

    return raw


def get_profile(config: dict[str, Any]) -> dict[str, str]:
    return {k: str(v or "") for k, v in (config.get("profile") or {}).items()}


def list_templates(templates_dir: str | Path = "data/templates") -> list[str]:
    d = Path(templates_dir)
    if not d.exists():
        return []
    names = [p.stem for p in d.glob("*.txt") if p.is_file()]
    return sorted(names)


def load_template(
    name: str,
    templates_dir: str | Path = "data/templates",
    fallback_message: str = "",
) -> str:
    path = Path(templates_dir) / f"{name}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return (fallback_message or "").strip()


def get_message(
    config: dict[str, Any],
    template_name: str | None = None,
    templates_dir: str | Path = "data/templates",
) -> str:
    if template_name:
        msg = load_template(template_name, templates_dir)
        if msg:
            return msg

    templates = config.get("message_templates") or {}
    if template_name and template_name in templates:
        return str(templates[template_name]).strip()

    return str(config.get("default_message") or "").strip()
