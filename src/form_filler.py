"""Fill detected form fields and handle simple UI annoyances."""

from __future__ import annotations

from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from .form_analyzer import FieldMatch, find_form_fields


async def dismiss_common_overlays(page: Page) -> None:
    """Best-effort close of cookie banners and simple modals."""
    selectors = [
        "button:has-text('Accept')",
        "button:has-text('Accept all')",
        "button:has-text('Accept All')",
        "button:has-text('I agree')",
        "button:has-text('Got it')",
        "button:has-text('OK')",
        "button:has-text('Close')",
        "[aria-label='Close']",
        "[aria-label='close']",
        ".cookie-accept",
        "#onetrust-accept-btn-handler",
        ".cc-btn.cc-dismiss",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click(timeout=2000)
                await page.wait_for_timeout(400)
        except Exception:
            continue


async def tick_required_checkboxes(page: Page) -> None:
    """Tick obvious required privacy / terms checkboxes."""
    try:
        boxes = page.locator("input[type='checkbox']")
        count = await boxes.count()
        for i in range(min(count, 10)):
            box = boxes.nth(i)
            try:
                if await box.is_checked():
                    continue
                label_text = await box.evaluate(
                    """el => {
                        if (el.labels && el.labels.length) return el.labels[0].textContent || '';
                        return el.parentElement ? el.parentElement.textContent || '' : '';
                    }"""
                )
                label_text = (label_text or "").lower()
                if any(k in label_text for k in ("privacy", "terms", "agree", "consent", "policy", "gdpr")):
                    await box.check(timeout=2000)
            except Exception:
                continue
    except Exception:
        pass


async def fill_form(
    page: Page,
    profile: dict[str, str],
    message: str,
) -> tuple[bool, str]:
    """Detect fields and fill them. Returns (success: bool, notes: str)"""
    await dismiss_common_overlays(page)

    fields = await find_form_fields(page)
    if not fields:
        return False, "no_fillable_fields_found"

    filled = []
    errors = []

    value_map = {
        "first_name": profile.get("first_name", ""),
        "last_name": profile.get("last_name", ""),
        "full_name": profile.get("full_name") or f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(),
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "company": profile.get("company", ""),
        "website": profile.get("website", ""),
        "job_title": profile.get("job_title", ""),
        "message": message,
        "subject": message.split("\n")[0][:80] if message else "Inquiry",
    }

    for field_type, match in fields.items():
        value = value_map.get(field_type, "")
        if not value:
            continue
        try:
            await match.locator.scroll_into_view_if_needed(timeout=3000)
            await match.locator.fill(value, timeout=5000)
            filled.append(field_type)
        except Exception as e:
            errors.append(f"{field_type}:{type(e).__name__}")

    await tick_required_checkboxes(page)

    if not filled:
        return False, "could_not_fill_any_fields: " + ",".join(errors)

    notes = "filled=" + ",".join(filled)
    if errors:
        notes += " | errors=" + ",".join(errors)
    return True, notes


async def submit_form(page: Page) -> tuple[bool, str]:
    """Attempt to click a submit button. Returns (clicked, notes)."""
    submit_selectors = [
        "form button[type='submit']",
        "form input[type='submit']",
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Submit')",
        "button:has-text('Send')",
        "button:has-text('Send message')",
        "button:has-text('Send Message')",
        "button:has-text('Contact us')",
        "button:has-text('Get in touch')",
        "[type='submit']",
    ]
    for sel in submit_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click(timeout=5000)
                await page.wait_for_timeout(1500)
                return True, f"clicked:{sel}"
        except Exception:
            continue
    return False, "no_submit_button_found"
