"""Find a contact page for a given domain."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from playwright.async_api import Page


@dataclass
class FindResult:
    status: str  # "found" | "no_form" | "inaccessible"
    url: str | None = None
    notes: str = ""


async def try_url(page: Page, url: str, timeout: int = 15_000) -> bool:
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        if resp and resp.status >= 400:
            return False
        # brief pause so cookie banners / iframes can appear
        await page.wait_for_timeout(700)
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
            if await page.locator(
                "textarea, input[name*='message' i], input[name*='comment' i]"
            ).count() > 0:
                return True
        # HubSpot / iframe forms often leave text like "send us an email"
        if any(k in text for k in ("send us an email", "contact us", "get in touch")):
            if await page.locator("iframe").count() > 0:
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
) -> FindResult:
    """
    Returns FindResult with status:
      - found: contact page located
      - inaccessible: homepage could not be reached at all
      - no_form: site reachable but no contact form found
    """
    https_base = f"https://{domain}"
    http_base = f"http://{domain}"

    homepage_ok = await try_url(page, https_base, timeout=timeout_ms)
    base = https_base
    if not homepage_ok:
        homepage_ok = await try_url(page, http_base, timeout=timeout_ms)
        base = http_base

    if not homepage_ok:
        return FindResult(
            status="inaccessible",
            notes="homepage_unreachable",
        )

    if await page_looks_like_contact(page, contact_keywords):
        return FindResult(status="found", url=page.url)

    for path in contact_paths:
        url = urljoin(base, path)
        if await try_url(page, url, timeout=timeout_ms):
            if await page_looks_like_contact(page, contact_keywords):
                return FindResult(status="found", url=page.url)

    try:
        if page.url.rstrip("/") not in (https_base, http_base):
            await try_url(page, base, timeout=timeout_ms)

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

        seen: set[str] = set()
        for cand in candidates:
            if cand in seen:
                continue
            seen.add(cand)
            if await try_url(page, cand, timeout=timeout_ms):
                if await page_looks_like_contact(page, contact_keywords):
                    return FindResult(status="found", url=page.url)
    except Exception:
        pass

    return FindResult(status="no_form", notes="contact_page_not_found")
