"""
Fill contact forms with high coverage:
  1) dismiss popups / entry gates / reveal sections
  2) wait for JS forms
  3) fill required (or all matched) fields — never newsletter boxes
  4) fallback: email / textarea / name on real contact forms only
  5) iframes included
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field

from playwright.async_api import Frame, Page

from .form_analyzer import FieldMatch, find_fallback_fields, find_form_fields


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
    "#hs-eu-confirmation-button", "#hs-eu-cookie-confirmation-button",
    "a#hs-eu-confirmation-button", "#onetrust-accept-btn-handler",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "#accept-cookie", "#cookie-accept",
    "button:has-text('Accept all')", "button:has-text('Accept All')",
    "button:has-text('Accept Cookies')", "button:has-text('Accept')",
    "button:has-text('I agree')", "button:has-text('I Agree')",
    "button:has-text('Allow all')", "button:has-text('Allow All')",
    "button:has-text('Got it')", "button:has-text('OK')", "button:has-text('Agree')",
    "a:has-text('Accept all')", "a:has-text('Accept All')", "a:has-text('Accept')",
    "[aria-label='Accept']", ".cookie-accept", ".cc-btn.cc-dismiss", ".cc-allow",
    "button[id*='accept' i]", "a[id*='accept' i]",
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
            if await loc.count() > 0 and await loc.is_visible(timeout=500):
                await loc.click(timeout=2000)
                await asyncio.sleep(0.35)
        except Exception:
            continue
    try:
        await page.evaluate(
            """() => {
                const sels = [
                    '#hs-eu-confirmation-button', '#onetrust-accept-btn-handler',
                    '.cookie-accept', '.cc-dismiss', '.pum-close', '.modal-close',
                    '#accept-cookie', '#cookie-accept'
                ];
                for (const s of sels) {
                    const el = document.querySelector(s);
                    if (el) el.click();
                }
                document.querySelectorAll(
                    '.pum-overlay, .pum-active, .modal-backdrop, .popup-overlay, .cookie-banner'
                ).forEach(el => { try { el.remove(); } catch(e) {} });
                document.body.style.overflow = '';
            }"""
        )
    except Exception:
        pass
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    await asyncio.sleep(0.4)


async def click_entry_gates(page: Page) -> None:
    """Click splash / age-gate / Enter site buttons that block the real page."""
    texts = [
        "enter site", "enter the site", "enter website", "enter",
        "i am 18", "i am 18+", "i am over 18", "i am over 21", "i am 21",
        "yes, i am", "yes i am", "i agree", "i accept",
        "continue", "continue to site", "continue to website",
        "proceed", "go to site", "go to website", "view site", "view website",
        "access site", "let me in", "i understand", "got it",
        "start browsing", "browse site",
    ]
    for text in texts:
        try:
            loc = page.locator(
                f"button:has-text('{text}'), a:has-text('{text}'), [role='button']:has-text('{text}')"
            )
            if await loc.count() > 0 and await loc.first.is_visible(timeout=400):
                await loc.first.click(timeout=2000)
                await asyncio.sleep(0.9)
                return
        except Exception:
            continue
    try:
        clicked = await page.evaluate(
            """() => {
                const phrases = [
                    'enter site','enter the site','enter website','enter',
                    'i am 18','i am 18+','i am over 18','i am over 21','i am 21',
                    'yes, i am','yes i am','continue to site','continue to website',
                    'continue','proceed','go to site','view site','access site',
                    'let me in','i understand','start browsing','browse site',
                    'i agree','i accept'
                ];
                const nodes = [...document.querySelectorAll(
                    'button, a, [role="button"], input[type="button"], input[type="submit"], .btn, [onclick]'
                )];
                for (const el of nodes) {
                    const t = (el.innerText || el.value || el.textContent || '').trim().toLowerCase();
                    if (!t || t.length > 40) continue;
                    if (phrases.some(p => t === p || t.startsWith(p))) {
                        el.click();
                        return t;
                    }
                }
                for (const el of nodes) {
                    const t = (el.innerText || el.value || '').trim().toLowerCase();
                    if (t === 'yes' || t === 'y') { el.click(); return t; }
                }
                return null;
            }"""
        )
        if clicked:
            await asyncio.sleep(1.0)
    except Exception:
        pass


async def click_contact_triggers(page: Page) -> None:
    try:
        clicked = await page.evaluate(
            """() => {
                const byData = document.querySelector(
                    '[data-type*="CONTACT" i], [data-action*="contact" i], [href="#contact"]'
                );
                if (byData && byData.tagName !== 'A') { byData.click(); return 'data'; }
                const texts = [
                    'contact us', 'get in touch', 'send a message', 'send message',
                    'enquire', 'inquiry', 'message us', 'write to us', 'email us'
                ];
                const nodes = [...document.querySelectorAll(
                    'a, button, [role="button"], summary, .btn, [data-toggle]'
                )];
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
            await asyncio.sleep(1.0)
    except Exception:
        pass


async def wait_for_form_ready(page: Page) -> None:
    await asyncio.sleep(1.2)
    try:
        await page.wait_for_selector(
            "form input, form textarea, input[type='email'], textarea, iframe",
            timeout=5000,
            state="attached",
        )
    except Exception:
        pass
    await asyncio.sleep(0.6)


async def human_type(locator, text: str) -> None:
    await locator.click(timeout=3000)
    try:
        await locator.fill("")
    except Exception:
        pass
    if len(text) > 80:
        await locator.fill(text)
    else:
        for ch in text:
            await locator.type(ch, delay=random.randint(20, 55))


async def tick_required_checkboxes(target: Page | Frame) -> list[str]:
    done: list[str] = []
    try:
        boxes = target.locator("input[type='checkbox']")
        count = await boxes.count()
        for i in range(min(count, 15)):
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
                if any(k in combined for k in ("newsletter", "subscribe", "marketing", "promotional", "offers")):
                    continue
                if any(
                    k in combined
                    for k in ("privacy", "terms", "agree", "consent", "policy", "gdpr", "acknowledge", "accept")
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


async def _fill_matches(
    matches: dict[str, FieldMatch] | list[FieldMatch],
    values: dict[str, str],
    use_human_type: bool,
) -> FillResult:
    result = FillResult()
    items = list(matches.items()) if isinstance(matches, dict) else [(m.field_type, m) for m in matches]
    for field_type, match in items:
        value = values.get(field_type, "") or values.get("full_name" if field_type == "name" else "", "")
        if not value:
            result.skipped.append(f"{field_type}(no_value)")
            continue
        try:
            await match.locator.scroll_into_view_if_needed(timeout=3000)
            if use_human_type and field_type in (
                "message", "subject", "full_name", "first_name", "last_name", "email", "company", "name"
            ):
                await human_type(match.locator, value)
            else:
                await match.locator.click(timeout=2000)
                await match.locator.fill(value, timeout=5000)
            tag = "req" if match.required else "opt"
            result.filled.append(f"{field_type}({tag})")
            await asyncio.sleep(random.uniform(0.1, 0.3))
        except Exception as e:
            result.unknown_required.append(f"{field_type}:{type(e).__name__}")
    return result


async def _fill_on_target(
    target: Page | Frame,
    profile: dict[str, str],
    message: str,
    use_human_type: bool = True,
) -> FillResult:
    values = _value_map(profile, message)
    fields = await find_form_fields(target)

    if fields:
        required = {k: v for k, v in fields.items() if v.required}
        to_fill = required if required else fields
        result = await _fill_matches(to_fill, values, use_human_type)
        if required:
            for k in fields:
                if k not in required:
                    result.skipped.append(f"{k}(optional)")
    else:
        result = FillResult(notes="no_named_fields")

    filled_types = {x.split("(")[0] for x in result.filled}
    need_fallback = not result.ok or (
        "email" not in filled_types and "message" not in filled_types
    )
    if need_fallback:
        fallback = await find_fallback_fields(target)
        fallback = [m for m in fallback if m.field_type not in filled_types]
        if fallback:
            extra = await _fill_matches(fallback, values, use_human_type)
            result.filled.extend(extra.filled)
            result.skipped.extend(extra.skipped)
            result.unknown_required.extend(extra.unknown_required)
            if extra.filled:
                result.notes = (result.notes + " | " if result.notes else "") + "used_fallback"

    checked = await tick_required_checkboxes(target)
    result.filled.extend(checked)

    # Reject subscribe-only fills (email alone is not a contact form)
    types = {x.split("(")[0] for x in result.filled if x != "checkbox"}
    if types and types <= {"email", "email_confirm"}:
        result.filled = []
        result.notes = "skipped_newsletter_like_form"
        return result

    if result.filled:
        result.notes = "filled=" + ",".join(result.filled) + (
            (" | " + result.notes) if result.notes else ""
        )
    else:
        result.notes = result.notes or "could_not_fill_any_fields"
    if result.skipped:
        result.notes += " | skipped=" + ",".join(result.skipped[:12])
    if result.unknown_required:
        result.notes += " | unknown=" + ",".join(result.unknown_required[:8])
    return result


async def fill_form(
    page: Page,
    profile: dict[str, str],
    message: str,
) -> FillResult:
    await dismiss_popups(page)
    await click_entry_gates(page)
    await dismiss_popups(page)
    await click_contact_triggers(page)
    await wait_for_form_ready(page)

    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(0.6)
        await page.evaluate("window.scrollTo(0, Math.min(800, document.body.scrollHeight/2))")
        await asyncio.sleep(0.4)
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
            if any(
                x in url
                for x in (
                    "google.com/maps", "facebook", "doubleclick", "analytics",
                    "gtm", "youtube", "twitter", "linkedin",
                )
            ):
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
        "form button[type='submit']", "form input[type='submit']",
        "button[type='submit']", "input[type='submit']",
        "button:has-text('Submit')", "button:has-text('Send')",
        "button:has-text('Send message')", "button:has-text('Send Message')",
        "button:has-text('Contact us')", "button:has-text('Get in touch')",
        "button:has-text('Enquire')", "button:has-text('Inquire')",
        "input[value='Submit']", "input[value='Send']", "[type='submit']",
    ]

    async def try_target(target: Page | Frame) -> tuple[bool, str]:
        for sel in selectors:
            try:
                loc = target.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible(timeout=800):
                    await loc.scroll_into_view_if_needed(timeout=2000)
                    await loc.click(timeout=5000)
                    await asyncio.sleep(1.5)
                    return True, f"clicked:{sel}"
            except Exception:
                continue
        try:
            for btn in await target.locator("form button, form [role='button'], button").all():
                text = ((await btn.inner_text()) or "").strip().lower()
                if any(k in text for k in ("send", "submit", "contact", "enquire", "inquire", "get in touch")):
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
