"""Find a contact page for a given domain."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout


async def try_url(page: Page, url: str, timeout: int = 15_000) -> bool:
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        if resp and resp.status >= 400:
            return False
        return True
    except Exception:
        return False


async def page_looks_like_contact(page: Page, keywords: list[str]) -> bool:
    try:
        forms = await page.locator("form").count()
        if forms == 0:
            inputs = await page.locator("input, textarea").count()
            if inputs < 2:
                return False

        text = (await page.inner_text("body")).lower()
        for kw in keywords:
            if kw.lower() in text:
                return True
        if await page.locator("input[type='email'], input[name*='email' i]").count() > 0:
            if await page.locator("textarea, input[name*='message' i], input[name*='comment' i]").count() > 0:
                return True
    except Exception:
        return False
    return False


async def find_contact_page(
    page: Page,
    domain: str,
    contact_paths: list[str],
    contact_keywords: list[str],
    timeout_ms: int = 20_000,
) -> str | None:
    """
    Returns the URL of a likely contact page, or None.
    Tries common paths first, then homepage + nav links.
    """
    base = f"https://{domain}"

    # 1. Common paths
    for path in contact_paths:
        url = urljoin(base, path)
        if await try_url(page, url, timeout=timeout_ms):
            if await page_looks_like_contact(page, contact_keywords):
                return page.url

    # 2. Homepage
    if not await try_url(page, base, timeout=timeout_ms):
        base = f"http://{domain}"
        if not await try_url(page, base, timeout=timeout_ms):
            return None

    if await page_looks_like_contact(page, contact_keywords):
        return page.url

    # 3. Scan nav / footer links
    try:
        links = await page.locator("a[href]").all()
        candidates: list[str] = []
        for link in links[:80]:
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

        seen = set()
        for cand in candidates:
            if cand not in seen:
                seen.add(cand)
                if await try_url(page, cand, timeout=timeout_ms):
                    if await page_looks_like_contact(page, contact_keywords):
                        return page.url
    except Exception:
        pass

    return None
