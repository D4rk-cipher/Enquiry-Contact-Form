"""Playwright browser context manager."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from playwright.async_api import async_playwright, Browser, BrowserContext, Page


@asynccontextmanager
async def get_browser(settings: dict[str, Any]) -> AsyncIterator[BrowserContext]:
    headless = bool(settings.get("headless", False))
    # Cap so a single dead site cannot stall forever
    timeout = min(int(settings.get("timeout_ms", 15_000)), 15_000)
    user_agent = settings.get("user_agent")

    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context_options: dict[str, Any] = {
            "viewport": {"width": 1280, "height": 900},
            "locale": "en-US",
        }
        if user_agent:
            context_options["user_agent"] = user_agent

        context = await browser.new_context(**context_options)
        context.set_default_timeout(timeout)
        context.set_default_navigation_timeout(timeout)

        try:
            yield context
        finally:
            await context.close()
            await browser.close()


async def new_page(context: BrowserContext) -> Page:
    page = await context.new_page()
    return page
