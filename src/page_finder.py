"""Find a contact page for a given domain."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout


@dataclass
class FindResult:
    status: str  # "found" | "no_form" | "inaccessible"
    url: str | None = None
    notes: str = ""


NAV_TIMEOUT_MS = 12_000
MAX_CONTACT_PATHS = 8
MAX_LINK_CANDIDATES = 6


async def try_url(page: Page, url: str, timeout: int = NAV_TIMEOUT_MS) -> bool:
    """Always returns within ~timeout ms. Stops hung navigations."""
    timeout = min(timeout, NAV_TIMEOUT_MS)
    try:
        resp = await page.goto(url, wait_until="commit", timeout=timeout)
        if resp and resp.status >= 400:
            return False
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=min(4000, timeout))
        except Exception:
            pass
        await asyncio.sleep(0.4)
        return True
    except PlaywrightTimeout:
        try:
            await page.evaluate("window.stop()")
        except Exception:
            pass
        return False
    except Exception:
        try:
            await page.evaluate("window.stop()")
        except Exception:
            pass
        return False


async def page_looks_like_contact(page: Page, keywords: list[str]) -> bool:
    try:
        has_real = await page.evaluate(
            """() => {
            for (const form of document.querySelectorAll('form')) {
                const hasEmail = !!form.querySelector(
                    'input[type="email"], input[name*="email" i], input[id*="email" i], input[placeholder*="email" i]'
                );
                const hasMessage = !!form.querySelector('textarea');
                const hasPhone = !!form.querySelector(
                    'input[type="tel"], input[name*="phone" i], input[id*="phone" i], input[placeholder*="phone" i]'
                );
                if (hasEmail && (hasMessage || hasPhone)) return true;
            }
            return false;
        }"""
        )
        if has_real:
            return True

        body = (await page.inner_text("body")).lower()
        if await page.locator("iframe").count() > 0:
            if any(
                k in body
                for k in (
                    "send us an email",
                    "contact us",
                    "get in touch",
                    "contact form",
                    "enquire",
                    "inquiry",
                )
            ):
                return True
            for kw in keywords:
                if kw.lower() in body:
                    return True

        if await page.locator("input[type='email'], input[name*='email' i]").count() > 0:
            for kw in keywords:
                if kw.lower() in body:
                    return True
    except Exception:
        return False
    return False


async def find_contact_page(
    page: Page,
    domain: str,
    contact_paths: list[str],
    contact_keywords: list[str],
    timeout_ms: int = NAV_TIMEOUT_MS,
) -> FindResult:
    timeout_ms = min(int(timeout_ms), NAV_TIMEOUT_MS)
    https_base = f"https://{domain}"
    http_base = f"http://{domain}"

    homepage_ok = await try_url(page, https_base, timeout=timeout_ms)
    base = https_base
    if not homepage_ok:
        homepage_ok = await try_url(page, http_base, timeout=timeout_ms)
        base = http_base

    if not homepage_ok:
        return FindResult(status="inaccessible", notes="homepage_unreachable")

    if await page_looks_like_contact(page, contact_keywords):
        return FindResult(status="found", url=page.url)

    for path in contact_paths[:MAX_CONTACT_PATHS]:
        url = urljoin(base, path)
        if await try_url(page, url, timeout=timeout_ms):
            if await page_looks_like_contact(page, contact_keywords):
                return FindResult(status="found", url=page.url)

    try:
        if page.url.rstrip("/") not in (https_base, http_base):
            await try_url(page, base, timeout=timeout_ms)

        links = await page.locator("a[href]").all()
        candidates: list[str] = []
        for link in links[:50]:
            try:
                href = await link.get_attribute("href")
                text = (await link.inner_text()).lower().strip()
                if not href:
                    continue
                full = urljoin(page.url, href)
                parsed = urlparse(full)
                if parsed.netloc and domain not in parsed.netloc:
                    continue
                for kw in contact_keywords:
                    if kw in text or kw.replace(" ", "") in href.lower():
                        candidates.append(full)
                        break
            except Exception:
                continue

        seen: set[str] = set()
        tried = 0
        for cand in candidates:
            if cand in seen:
                continue
            seen.add(cand)
            tried += 1
            if tried > MAX_LINK_CANDIDATES:
                break
            if await try_url(page, cand, timeout=timeout_ms):
                if await page_looks_like_contact(page, contact_keywords):
                    return FindResult(status="found", url=page.url)
    except Exception:
        pass

    return FindResult(status="no_form", notes="contact_page_not_found")
