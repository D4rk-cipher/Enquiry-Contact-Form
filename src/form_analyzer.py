"""Heuristic form field detection and mapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playwright.async_api import Locator, Page


@dataclass
class FieldMatch:
    locator: Locator
    field_type: str
    score: float
    reason: str


FIELD_KEYWORDS: dict[str, list[str]] = {
    "first_name": ["first name", "firstname", "first_name", "fname", "given name", "forename"],
    "last_name": ["last name", "lastname", "last_name", "lname", "surname", "family name"],
    "full_name": ["full name", "your name", "name", "contact name", "fullname"],
    "email": ["email", "e-mail", "email address", "e-mail address", "mail"],
    "phone": ["phone", "telephone", "mobile", "cell", "tel", "phone number", "contact number"],
    "company": ["company", "organization", "organisation", "business", "company name", "firm"],
    "website": ["website", "url", "web site", "homepage", "site"],
    "job_title": ["job title", "title", "position", "role"],
    "message": ["message", "comment", "comments", "inquiry", "enquiry", "question", "details", "how can we help", "description", "body"],
    "subject": ["subject", "topic", "regarding"],
}


async def _get_field_signals(loc: Locator) -> str:
    parts: list[str] = []
    for attr in ("name", "id", "placeholder", "aria-label", "aria-labelledby"):
        try:
            val = await loc.get_attribute(attr)
            if val:
                parts.append(val)
        except Exception:
            pass
    try:
        label = await loc.evaluate(
            """el => {
                if (el.labels && el.labels.length) return el.labels[0].textContent;
                const id = el.id;
                if (id) {
                    const l = document.querySelector('label[for="'+id+'"]');
                    if (l) return l.textContent;
                }
                return '';
            }"""
        )
        if label:
            parts.append(str(label))
    except Exception:
        pass
    return " ".join(parts).lower()


def _score_field(signals: str, field_type: str) -> float:
    keywords = FIELD_KEYWORDS.get(field_type, [])
    score = 0.0
    for kw in keywords:
        if kw in signals:
            score += 1.0 + (len(kw) / 20.0)
    return score


async def find_form_fields(page: Page) -> dict[str, FieldMatch]:
    candidates: dict[str, list[FieldMatch]] = {k: [] for k in FIELD_KEYWORDS}

    inputs = page.locator("form input, form textarea, form select, input, textarea, select")
    count = await inputs.count()
    count = min(count, 60)

    for i in range(count):
        loc = inputs.nth(i)
        try:
            tag = await loc.evaluate("el => el.tagName.toLowerCase()")
            input_type = (await loc.get_attribute("type") or "").lower()
            if input_type in ("hidden", "submit", "button", "image", "file", "checkbox", "radio"):
                continue

            signals = await _get_field_signals(loc)
            if not signals.strip():
                continue

            for field_type in FIELD_KEYWORDS:
                sc = _score_field(signals, field_type)
                if sc > 0:
                    candidates[field_type].append(
                        FieldMatch(locator=loc, field_type=field_type, score=sc, reason=signals[:80])
                    )
        except Exception:
            continue

    best: dict[str, FieldMatch] = {}
    used_selectors: set[str] = set()

    priority = [
        "email", "message", "first_name", "last_name", "full_name",
        "phone", "company", "website", "job_title", "subject",
    ]
    for ft in priority:
        matches = sorted(candidates.get(ft, []), key=lambda m: m.score, reverse=True)
        for m in matches:
            try:
                key = await m.locator.evaluate(
                    "el => (el.name || '') + '|' + (el.id || '') + '|' + (el.placeholder || '')"
                )
                if key in used_selectors:
                    continue
                best[ft] = m
                used_selectors.add(key)
                break
            except Exception:
                continue

    return best
