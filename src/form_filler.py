"""
Fill contact forms: dismiss popups, reveal hidden sections, map fields, type values.
Supports main page and iframes (HubSpot, etc.).
Only fills required fields when they can be detected.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field

from playwright.async_api import Frame, Page

from .form_analyzer import FieldMatch, find_form_fields


@dataclass
class FillResult:
    filled: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    unknown_required: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def ok(self) -> bool:
        return len(self.filled) > 0


COOKIE_SELECTORS = [
    "#hs-eu-confirmation-button",
    "#hs-eu-cookie-confirmation-button",
    "a#hs-eu-confirmation-button",
    "#onetrust-accept-btn-handler",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
    "button:has-text('Accept Cookies')",
    "button:has-text('Accept')",
    "button:has-text('I agree')",
    "button:has-text('I Agree')",
    "button:has-text('Allow all')",
    "button:has-text('Allow All')",
    "button:has-text('Got it')",
    "button:has-text('OK')",
    "a:has-text('Accept all')",
    "a:has-text('Accept All')",
    "a:has-text('Accept')",
    "[aria-label='Accept']",
    ".cookie-accept",
    ".cc-btn.cc-dismiss",
    ".cc-allow",
    "button[id*='accept' i]",
    "a[id*='accept' i]",
]

CLOSE_SELECTORS = [
    ".pum-close", ".popmake-close", ".popup-close", ".modal-close",
    ".modal .close", "button.close", "[aria-label='Close']",
    "[aria-label='close']", ".fancybox-close", ".mfp-close",
]


async def dismiss_popups(page: Page) -> None:
    for sel in COOKIE_SELECTORS + CLOSE_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible(timeout=600):
                await loc.click(timeout=2000)
                await asyncio.sleep(0.4)
        except Exception:
            continue

    try:
        await page.evaluate(
            """() => {
                const sels = [
                    '#hs-eu-confirmation-button', '#onetrust-accept-btn-handler',
                    '.cookie-accept', '.cc-dismiss', '.pum-close', '.modal-close'
                ];
                for (const s of sels) {
                    const el = document.querySelector(s);
                    if (el) el.click();
                }
                document.querySelectorAll(
                    '.pum-overlay, .pum-active, .modal-backdrop, .popup-overlay'
                ).forEach(el => el.remove());
                document.body.style.overflow = '';
            }"""
        )
    except Exception:
        pass

    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass

    await asyncio.sleep(0.5)


async def click_contact_triggers(page: Page) -> None:
    try:
        clicked = await page.evaluate(
            """() => {
                const byData = document.querySelector('[data-type*="CONTACT" i], [data-action*="contact" i]');
                if (byData) { byData.click(); return 'data-type'; }
                const texts = ['contact us', 'get in touch', 'send a message', 'enquire', 'inquiry', 'message us'];
                const nodes = [...document.querySelectorAll('a, button, [role="button"], summary')];
                for (const el of nodes) {
                    const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                    if (texts.some(x => t === x || t.startsWith(x))) {
                        el.click();
                        return t;
                    }
                }
                return null;
            }"""
        )
        if clicked:
            await asyncio.sleep(0.8)
    except Exception:
        pass


async def human_type(locator, text: str) -> None:
    await locator.click(timeout=3000)
    await locator.fill("")
    for ch in text:
        await locator.type(ch, delay=random.randint(25, 70))


async def tick_required_checkboxes(target: Page | Frame) -> list[str]:
    done: list[str] = []
    try:
        boxes = target.locator("input[type='checkbox']")
        count = await boxes.count()
        for i in range(min(count, 12)):
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
                combined = (label_text or "").lower()
                if any(k in combined for k in ("newsletter", "subscribe", "marketing", "promotional")):
                    continue
                if any(
                    k in combined
                    for k in ("privacy", "terms", "agree", "consent", "policy", "gdpr", "acknowledge")
                ):
                    await box.check(timeout=2500)
                    done.append("checkbox")
            except Exception:
                continue
    except Exception:
        pass
    return done


def _value_map(profile: dict[str, str], message: str) -> dict[str, str]:
    full = profile.get("full_name") or f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
    return {
        "first_name": profile.get("first_name", ""),
        "last_name": profile.get("last_name", ""),
        "full_name": full,
        "name": full,
        "email": profile.get("email", ""),
        "email_confirm": profile.get("email", ""),
        "company_email": profile.get("company_email") or profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "company": profile.get("company", ""),
        "website": profile.get("website", ""),
        "job_title": profile.get("job_title", ""),
        "message": message,
        "subject": (message.split("\n")[0][:80] if message else "Inquiry"),
        "address": profile.get("address", ""),
        "city": profile.get("city", ""),
        "state": profile.get("state", ""),
        "zip": profile.get("zip", ""),
        "country": profile.get("country", "United States"),
        "preferred_contact": profile.get("preferred_contact", "email"),
    }


async def _fill_on_target(
    target: Page | Frame,
    profile: dict[str, str],
    message: str,
    use_human_type: bool = True,
) -> FillResult:
    result = FillResult()
    fields = await find_form_fields(target)
    if not fields:
        result.notes = "no_fillable_fields_found"
        return result

    values = _value_map(profile, message)

    # Prefer required fields only. If none marked required, fill all matched.
    required_fields = {k: v for k, v in fields.items() if v.required}
    optional_fields = {k: v for k, v in fields.items() if not v.required}
    to_fill = required_fields if required_fields else fields

    for field_type, match in to_fill.items():
        value = values.get(field_type, "")
        if not value:
            result.skipped.append(f"{field_type}(no_value)")
            continue
        try:
            await match.locator.scroll_into_view_if_needed(timeout=3000)
            if use_human_type and field_type in (
                "message", "subject", "full_name", "first_name", "last_name", "email", "company"
            ):
                await human_type(match.locator, value)
            else:
                await match.locator.click(timeout=2000)
                await match.locator.fill(value, timeout=5000)
            tag = "req" if match.required else "opt"
            result.filled.append(f"{field_type}({tag})")
            await asyncio.sleep(random.uniform(0.12, 0.35))
        except Exception as e:
            result.unknown_required.append(f"{field_type}:{type(e).__name__}")

    if required_fields:
        for field_type in optional_fields:
            result.skipped.append(f"{field_type}(optional)")

    checked = await tick_required_checkboxes(target)
    result.filled.extend(checked)

    if result.filled:
        result.notes = "filled=" + ",".join(result.filled)
    else:
        result.notes = "could_not_fill_any_fields"
    if result.skipped:
        result.notes += " | skipped=" + ",".join(result.skipped)
    if result.unknown_required:
        result.notes += " | unknown=" + ",".join(result.unknown_required)
    return result


async def fill_form(
    page: Page,
    profile: dict[str, str],
    message: str,
) -> FillResult:
    await asyncio.sleep(0.8)
    await dismiss_popups(page)
    await click_contact_triggers(page)

    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(0.5)
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.3)
    except Exception:
        pass

    await dismiss_popups(page)

    result = await _fill_on_target(page, profile, message)
    if result.ok:
        return result

    try:
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            url = (frame.url or "").lower()
            if any(x in url for x in ("google.com/maps", "facebook", "doubleclick", "analytics", "gtm")):
                continue
            try:
                fr = await _fill_on_target(frame, profile, message)
                if fr.ok:
                    fr.notes = "iframe:" + fr.notes
                    return fr
            except Exception:
                continue
    except Exception:
        pass

    return result


async def submit_form(page: Page) -> tuple[bool, str]:
    selectors = [
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

    async def try_target(target: Page | Frame) -> tuple[bool, str]:
        for sel in selectors:
            try:
                loc = target.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible(timeout=1000):
                    await loc.click(timeout=5000)
                    await asyncio.sleep(1.5)
                    return True, f"clicked:{sel}"
            except Exception:
                continue
        try:
            for btn in await target.locator("form button, form [role='button']").all():
                text = ((await btn.inner_text()) or "").strip().lower()
                if any(k in text for k in ("send", "submit", "contact", "enquire", "inquire")):
                    if await btn.is_visible():
                        await btn.click(timeout=5000)
                        await asyncio.sleep(1.5)
                        return True, f"clicked:text:{text[:30]}"
        except Exception:
            pass
        return False, "no_submit_button_found"

    ok, notes = await try_target(page)
    if ok:
        return ok, notes

    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            ok, notes = await try_target(frame)
            if ok:
                return True, f"iframe:{notes}"
        except Exception:
            continue

    return False, "no_submit_button_found"
