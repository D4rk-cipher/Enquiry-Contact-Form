"""Fill detected form fields and handle simple UI annoyances."""

from __future__ import annotations

from typing import Any

from playwright.async_api import Frame, Page, TimeoutError as PlaywrightTimeout

from .form_analyzer import FieldMatch, find_form_fields


# Cookie / consent selectors (buttons AND links)
COOKIE_SELECTORS = [
    "#hs-eu-confirmation-button",           # HubSpot
    "#hs-eu-cookie-confirmation-button",
    "a#hs-eu-confirmation-button",
    "button:has-text('Accept')",
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
    "button:has-text('Accept Cookies')",
    "button:has-text('I agree')",
    "button:has-text('I Agree')",
    "button:has-text('Got it')",
    "button:has-text('OK')",
    "button:has-text('Allow')",
    "button:has-text('Allow all')",
    "button:has-text('Allow All')",
    "a:has-text('Accept')",
    "a:has-text('Accept all')",
    "a:has-text('Accept All')",
    "[aria-label='Accept']",
    "[aria-label='Close']",
    "[aria-label='close']",
    ".cookie-accept",
    "#onetrust-accept-btn-handler",
    ".cc-btn.cc-dismiss",
    ".cc-allow",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "button[id*='accept' i]",
    "a[id*='accept' i]",
]


async def dismiss_common_overlays(page: Page) -> int:
    """Best-effort close of cookie banners and simple modals. Returns clicks made."""
    clicks = 0
    for sel in COOKIE_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible(timeout=800):
                await loc.click(timeout=2500)
                clicks += 1
                await page.wait_for_timeout(600)
        except Exception:
            continue
    if clicks:
        await page.wait_for_timeout(800)
    return clicks


async def tick_required_checkboxes(target: Page | Frame) -> None:
    """Tick obvious required privacy / terms checkboxes."""
    try:
        boxes = target.locator("input[type='checkbox']")
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
                if any(
                    k in label_text
                    for k in ("privacy", "terms", "agree", "consent", "policy", "gdpr")
                ):
                    await box.check(timeout=2000)
            except Exception:
                continue
    except Exception:
        pass


async def _fill_on_target(
    target: Page | Frame,
    profile: dict[str, str],
    message: str,
) -> tuple[bool, str]:
    """Run field detection + fill on a Page or Frame."""
    fields = await find_form_fields(target)  # type: ignore[arg-type]
    if not fields:
        return False, "no_fillable_fields_found"

    filled: list[str] = []
    errors: list[str] = []

    value_map = {
        "first_name": profile.get("first_name", ""),
        "last_name": profile.get("last_name", ""),
        "full_name": profile.get("full_name")
        or f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(),
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
            await match.locator.click(timeout=2000)
            await match.locator.fill(value, timeout=5000)
            filled.append(field_type)
            await target.wait_for_timeout(150)
        except Exception as e:
            errors.append(f"{field_type}:{type(e).__name__}")

    await tick_required_checkboxes(target)

    if not filled:
        return False, "could_not_fill_any_fields: " + ",".join(errors)

    notes = "filled=" + ",".join(filled)
    if errors:
        notes += " | errors=" + ",".join(errors)
    return True, notes


async def fill_form(
    page: Page,
    profile: dict[str, str],
    message: str,
) -> tuple[bool, str]:
    """
    Detect fields and fill them.
    Tries main page first, then HubSpot / embed iframes.
    Returns (success: bool, notes: str)
    """
    await page.wait_for_timeout(800)
    await dismiss_common_overlays(page)
    await page.wait_for_timeout(500)

    ok, notes = await _fill_on_target(page, profile, message)
    if ok:
        return True, notes

    try:
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                url = (frame.url or "").lower()
                if any(x in url for x in ("google.com/maps", "facebook", "doubleclick", "analytics")):
                    continue
                ok, frame_notes = await _fill_on_target(frame, profile, message)
                if ok:
                    return True, f"iframe:{frame_notes}"
            except Exception:
                continue
    except Exception:
        pass

    return False, notes


async def submit_form(page: Page) -> tuple[bool, str]:
    """Attempt to click a submit button on page or in iframes."""
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
        "input[value='Submit']",
        "input[value='Send']",
        "[type='submit']",
    ]

    async def try_submit(target: Page | Frame) -> tuple[bool, str]:
        for sel in submit_selectors:
            try:
                loc = target.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible(timeout=1000):
                    await loc.click(timeout=5000)
                    await page.wait_for_timeout(1500)
                    return True, f"clicked:{sel}"
            except Exception:
                continue
        return False, "no_submit_button_found"

    ok, notes = await try_submit(page)
    if ok:
        return ok, notes

    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            ok, notes = await try_submit(frame)
            if ok:
                return True, f"iframe:{notes}"
        except Exception:
            continue

    return False, "no_submit_button_found"
