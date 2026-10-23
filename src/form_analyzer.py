"""Heuristic form field detection — broad keywords + raw fallback fields."""

from __future__ import annotations

from dataclasses import dataclass

from playwright.async_api import Frame, Locator, Page


@dataclass
class FieldMatch:
    locator: Locator
    field_type: str
    score: float
    reason: str
    required: bool = False


FIELD_KEYWORDS: dict[str, list[str]] = {
    "first_name": [
        "first name", "firstname", "first_name", "fname", "given name",
        "forename", "first-name", "givenname",
    ],
    "last_name": [
        "last name", "lastname", "last_name", "lname", "surname",
        "family name", "last-name", "familyname",
    ],
    "full_name": [
        "full name", "your name", "contact name", "fullname",
        "display name", "your full name", "enter your name", "name",
    ],
    "email": [
        "email address", "e-mail address", "emailaddress", "e-mail",
        "email", "mail address", "work email", "business email",
        "company email", "your email", "mail",
    ],
    "phone": [
        "phone number", "telephone", "mobile number", "cell phone",
        "mobile", "phone", "tel", "cell", "contact number", "whatsapp",
    ],
    "company": [
        "company name", "organization", "organisation", "business name",
        "company", "business", "firm", "employer", "agency",
    ],
    "website": ["website", "web site", "homepage", "company website", "url", "site"],
    "job_title": ["job title", "jobtitle", "position", "role", "title"],
    "message": [
        "your message", "how can we help", "tell us more", "additional information",
        "additional info", "comments", "comment", "enquiry", "inquiry",
        "question", "details", "description", "message", "body", "notes",
    ],
    "subject": ["subject", "topic", "regarding", "reason for contact"],
    "address": ["street address", "address line", "mailing address", "address"],
    "city": ["city", "town"],
    "state": ["state", "province", "region"],
    "zip": ["zip code", "postal code", "postcode", "zip", "postal"],
    "country": ["country", "nation"],
}

NEWSLETTER_SIGNALS = (
    "newsletter", "subscribe", "subscription", "signup", "sign up", "sign-up",
    "mailing list", "mail list", "join our", "stay updated", "stay informed",
    "get updates", "promo", "promotional", "coupon", "discount code",
    "footer-email", "footer_email", "mc-embedded", "mailchimp", "klavio",
    "klaviyo", "email-signup", "email_signup", "opt-in", "optin",
)
SEARCH_SIGNALS = ("search", "query")


def _is_newsletter_or_search(signals: str) -> bool:
    s = (signals or "").lower()
    if any(x in s for x in SEARCH_SIGNALS) and "message" not in s and "contact" not in s:
        return True
    if any(x in s for x in NEWSLETTER_SIGNALS):
        return True
    return False


async def _form_looks_like_newsletter(loc: Locator) -> bool:
    try:
        return await loc.evaluate(
            """el => {
                const form = el.closest('form');
                if (!form) return false;
                const t = ((form.getAttribute('id')||'') + ' ' +
                           (form.getAttribute('class')||'') + ' ' +
                           (form.getAttribute('action')||'') + ' ' +
                           (form.innerText||'').slice(0, 200)).toLowerCase();
                const bad = ['newsletter','subscribe','subscription','signup','sign-up',
                             'mailing list','mailchimp','klaviyo','footer-email','opt-in'];
                if (bad.some(b => t.includes(b))) return true;
                const inputs = form.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=checkbox])');
                const areas = form.querySelectorAll('textarea');
                if (areas.length === 0 && inputs.length <= 2) {
                    const hasEmail = !!form.querySelector('input[type=email], input[name*=email i]');
                    const hasMessageWords = /message|comment|enquiry|inquiry|question/.test(t);
                    if (hasEmail && !hasMessageWords) return true;
                }
                return false;
            }"""
        )
    except Exception:
        return False


async def _get_field_signals(loc: Locator) -> str:
    parts: list[str] = []
    for attr in ("name", "id", "placeholder", "aria-label", "aria-labelledby", "autocomplete"):
        try:
            val = await loc.get_attribute(attr)
            if val:
                parts.append(val)
        except Exception:
            pass
    try:
        label = await loc.evaluate(
            """el => {
                if (el.labels && el.labels.length) return el.labels[0].textContent || '';
                const id = el.id;
                if (id) {
                    const l = document.querySelector('label[for="'+id+'"]');
                    if (l) return l.textContent || '';
                }
                const prev = el.previousElementSibling;
                if (prev && prev.tagName === 'LABEL') return prev.textContent || '';
                const parent = el.closest('label, .form-group, .gfield, .hs-form-field, .field, .form-field, li, p, div');
                if (parent) {
                    const t = (parent.innerText || '').split('\\n')[0];
                    if (t && t.length < 80) return t;
                }
                return '';
            }"""
        )
        if label:
            parts.append(str(label))
    except Exception:
        pass
    return " ".join(parts).lower()


async def _is_required(loc: Locator) -> bool:
    try:
        return await loc.evaluate(
            """el => {
                if (el.required) return true;
                if ((el.getAttribute('aria-required') || '').toLowerCase() === 'true') return true;
                const cls = (el.className || '').toString().toLowerCase();
                if (cls.includes('required') || cls.includes('mandatory')) return true;
                let labelText = '';
                if (el.labels && el.labels.length) labelText = el.labels[0].textContent || '';
                else if (el.id) {
                    const l = document.querySelector('label[for="' + el.id + '"]');
                    if (l) labelText = l.textContent || '';
                }
                const parent = el.closest('.form-group, .gfield, .hs-form-field, .field, .form-field, p, div, li');
                if (parent) labelText += ' ' + (parent.innerText || '').slice(0, 100);
                if (/\\*|required|mandatory/i.test(labelText)) return true;
                if (el.getAttribute('data-required') === 'true') return true;
                return false;
            }"""
        )
    except Exception:
        return False


def _score_field(signals: str, field_type: str) -> float:
    keywords = FIELD_KEYWORDS.get(field_type, [])
    score = 0.0
    for kw in keywords:
        if kw in signals:
            score += 1.0 + (len(kw) / 15.0)
            break
    return score


async def find_form_fields(page: Page | Frame) -> dict[str, FieldMatch]:
    candidates: dict[str, list[FieldMatch]] = {k: [] for k in FIELD_KEYWORDS}
    inputs = page.locator("form input, form textarea, form select, input, textarea, select")
    count = min(await inputs.count(), 80)

    for i in range(count):
        loc = inputs.nth(i)
        try:
            input_type = (await loc.get_attribute("type") or "").lower()
            if input_type in ("hidden", "submit", "button", "image", "file", "checkbox", "radio", "password"):
                continue
            if await _form_looks_like_newsletter(loc):
                continue
            signals = await _get_field_signals(loc)
            if _is_newsletter_or_search(signals):
                continue

            required = await _is_required(loc)
            type_boost: dict[str, float] = {}
            if input_type == "email":
                type_boost["email"] = 3.0
            if input_type == "tel":
                type_boost["phone"] = 3.0
            tag = await loc.evaluate("el => el.tagName.toLowerCase()")
            if tag == "textarea":
                type_boost["message"] = type_boost.get("message", 0) + 2.0

            for field_type in FIELD_KEYWORDS:
                sc = _score_field(signals, field_type) + type_boost.get(field_type, 0)
                if sc > 0:
                    if required:
                        sc += 0.3
                    candidates[field_type].append(
                        FieldMatch(locator=loc, field_type=field_type, score=sc, reason=signals[:80], required=required)
                    )
        except Exception:
            continue

    best: dict[str, FieldMatch] = {}
    used: set[str] = set()
    priority = [
        "email", "message", "first_name", "last_name", "full_name",
        "phone", "company", "subject", "website", "job_title",
        "address", "city", "state", "zip", "country",
    ]
    for ft in priority:
        matches = sorted(candidates.get(ft, []), key=lambda m: m.score, reverse=True)
        for m in matches:
            try:
                key = await m.locator.evaluate(
                    "el => (el.name||'')+'|'+(el.id||'')+'|'+(el.placeholder||'')"
                )
                if key in used:
                    continue
                best[ft] = m
                used.add(key)
                break
            except Exception:
                continue
    return best


async def find_fallback_fields(page: Page | Frame) -> list[FieldMatch]:
    results: list[FieldMatch] = []
    used: set[str] = set()

    async def add(loc: Locator, field_type: str, score: float, reason: str) -> None:
        try:
            if not await loc.is_visible(timeout=500):
                return
            key = await loc.evaluate(
                "el => (el.name||'')+'|'+(el.id||'')+'|'+(el.placeholder||'')"
            )
            if key in used:
                return
            used.add(key)
            req = await _is_required(loc)
            results.append(FieldMatch(locator=loc, field_type=field_type, score=score, reason=reason, required=req))
        except Exception:
            pass

    n = min(await page.locator("input[type='email']").count(), 5)
    for i in range(n):
        loc = page.locator("input[type='email']").nth(i)
        if await _form_looks_like_newsletter(loc):
            continue
        await add(loc, "email", 2.0, "type=email")

    n = min(await page.locator("textarea").count(), 5)
    for i in range(n):
        loc = page.locator("textarea").nth(i)
        if await _form_looks_like_newsletter(loc):
            continue
        await add(loc, "message", 2.0, "textarea")

    n = min(await page.locator("input[type='tel']").count(), 3)
    for i in range(n):
        await add(page.locator("input[type='tel']").nth(i), "phone", 2.0, "type=tel")

    n = min(await page.locator("input[type='text'], input:not([type])").count(), 12)
    for i in range(n):
        loc = page.locator("input[type='text'], input:not([type])").nth(i)
        try:
            if await _form_looks_like_newsletter(loc):
                continue
            signals = await _get_field_signals(loc)
            if _is_newsletter_or_search(signals):
                continue
            ft = "full_name"
            if any(x in signals for x in ("email", "mail")):
                ft = "email"
            elif any(x in signals for x in ("phone", "mobile", "tel")):
                ft = "phone"
            elif any(x in signals for x in ("company", "organization", "business")):
                ft = "company"
            elif any(x in signals for x in ("first", "fname")):
                ft = "first_name"
            elif any(x in signals for x in ("last", "lname", "surname")):
                ft = "last_name"
            await add(loc, ft, 1.0, signals[:60] or "text-input")
        except Exception:
            continue

    return results
