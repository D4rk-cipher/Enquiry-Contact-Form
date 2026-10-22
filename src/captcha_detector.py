"""Simple CAPTCHA / anti-bot detection for Phase 1 (detect & skip)."""

from __future__ import annotations

from playwright.async_api import Page


CAPTCHA_SELECTORS = [
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    "iframe[src*='challenges.cloudflare.com']",
    "div.g-recaptcha",
    "div.h-captcha",
    "div.cf-turnstile",
    "[data-sitekey]",
    "#cf-challenge-running",
    ".cf-browser-verification",
    "text=Verify you are human",
    "text=Checking your browser",
    "text=Just a moment",
    "text=Enable JavaScript and cookies to continue",
]


async def page_has_captcha(page: Page) -> bool:
    """Return True if a CAPTCHA or strong anti-bot challenge is present."""
    try:
        for sel in CAPTCHA_SELECTORS:
            try:
                count = await page.locator(sel).count()
                if count > 0:
                    return True
            except Exception:
                continue

        content = (await page.content()).lower()
        indicators = [
            "recaptcha",
            "hcaptcha",
            "cf-turnstile",
            "checking your browser before accessing",
            "verify you are human",
            "attention required",
            "enable javascript and cookies",
        ]
        for ind in indicators:
            if ind in content:
                return True
    except Exception:
        pass
    return False
