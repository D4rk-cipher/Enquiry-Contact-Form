#!/usr/bin/env python3
"""
Contact Form Bot - Phase 1
Usage examples:
  python main.py --input data/emails.csv --mode test
  python main.py --input data/emails.csv --mode submit --resume
  python main.py --input data/emails.csv --mode test --industry real_estate --limit 20
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from src.config import load_config, get_message, get_profile
from src.domain_extractor import load_domains_from_csv
from src.browser import get_browser, new_page
from src.page_finder import find_contact_page
from src.form_filler import fill_form, submit_form
from src.captcha_detector import page_has_captcha
from src.logger import RunLogger
from src.utils import polite_delay

app = typer.Typer(add_completion=False, help="Contact Form Outreach Bot - Phase 1")
console = Console()


async def process_domain(
    domain: str,
    original_email: str,
    config: dict,
    mode: str,
    industry: str | None,
    logger: RunLogger,
    context,
) -> str:
    """Process a single domain. Returns final status."""
    settings = config["settings"]
    profile = get_profile(config)
    message = get_message(config, industry)
    contact_paths = config["contact_paths"]
    keywords = config["contact_keywords"]
    timeout = int(settings.get("timeout_ms", 30_000))

    page = await new_page(context)
    contact_url = ""
    status = "error"
    notes = ""
    screenshot_path = ""

    try:
        contact_url = await find_contact_page(
            page, domain, contact_paths, keywords, timeout_ms=timeout
        )
        if not contact_url:
            status = "no_form"
            notes = "contact_page_not_found"
            return status

        if await page_has_captcha(page):
            status = "captcha"
            notes = "captcha_or_challenge_detected"
            return status

        ok, fill_notes = await fill_form(page, profile, message)
        if not ok:
            status = "error"
            notes = fill_notes
            return status

        notes = fill_notes

        if mode == "test":
            status = "filled_only"
            notes = "test_mode: " + notes
        else:
            clicked, sub_notes = await submit_form(page)
            if clicked:
                status = "submitted"
                notes = notes + " | " + sub_notes
                await page.wait_for_timeout(2000)
            else:
                status = "filled_only"
                notes = notes + " | " + sub_notes + " (submit_failed)"

        return status

    except Exception as e:
        status = "error"
        notes = f"{type(e).__name__}: {str(e)[:120]}"
        return status
    finally:
        try:
            if settings.get("screenshot_on_every_attempt") or (
                settings.get("screenshot_on_failure_only")
                and status not in ("submitted", "filled_only")
            ):
                shot = logger.screenshot_path_for(domain, status)
                await page.screenshot(path=str(shot), full_page=True)
                screenshot_path = str(shot)
        except Exception:
            pass

        logger.log_result(
            domain=domain,
            original_email=original_email,
            contact_url=contact_url or "",
            status=status,
            notes=notes,
            screenshot_path=screenshot_path,
        )
        try:
            await page.close()
        except Exception:
            pass


async def run_bot(
    input_path: Path,
    mode: str,
    config_path: Path,
    industry: Optional[str],
    resume: bool,
    limit: Optional[int],
    email_column: Optional[str],
) -> None:
    config = load_config(config_path)
    settings = config["settings"]
    delay = float(settings.get("delay_between_domains_sec", 10))

    console.print(f"[bold]Loading domains from[/bold] {input_path}")
    pairs = load_domains_from_csv(input_path, email_column)
    console.print(f"Found [green]{len(pairs)}[/green] unique domains")

    logger = RunLogger(output_dir="output")

    if resume:
        before = len(pairs)
        pairs = [(d, e) for d, e in pairs if not logger.is_processed(d)]
        console.print(
            f"Resume: skipped {before - len(pairs)} already processed -> {len(pairs)} remaining"
        )

    if limit is not None and limit > 0:
        pairs = pairs[:limit]
        console.print(f"Limiting to first {limit} domains")

    if not pairs:
        console.print("[yellow]Nothing to process.[/yellow]")
        return

    console.print(f"Mode: [bold cyan]{mode}[/bold cyan] | Delay ~ {delay}s between domains")
    console.print(f"Profile email: {config['profile'].get('email')}")
    console.print()

    async with get_browser(settings) as context:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Processing", total=len(pairs))

            for idx, (domain, email) in enumerate(pairs, 1):
                progress.update(task, description=f"[cyan]{domain}[/cyan]")
                status = await process_domain(
                    domain, email, config, mode, industry, logger, context
                )
                color = {
                    "submitted": "green",
                    "filled_only": "blue",
                    "captcha": "yellow",
                    "no_form": "magenta",
                    "error": "red",
                }.get(status, "white")
                console.print(f"  [{color}]{status:12}[/{color}] {domain}")

                progress.advance(task)

                if idx < len(pairs):
                    await polite_delay(delay)

    console.print()
    console.print("[bold green]Done.[/bold green] Results -> output/results.csv")
    console.print("CAPTCHA / manual -> output/needs_captcha.csv")
    console.print("Progress saved -> output/progress.json")


@app.command()
def main(
    input: Path = typer.Option(..., "--input", "-i", help="CSV file with emails"),
    mode: str = typer.Option("test", "--mode", "-m", help="test | submit"),
    config: Path = typer.Option("config.yaml", "--config", "-c", help="Path to config.yaml"),
    industry: Optional[str] = typer.Option(None, "--industry", help="Message template key"),
    resume: bool = typer.Option(False, "--resume", help="Skip already processed domains"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Process only first N domains"),
    email_column: Optional[str] = typer.Option(None, "--email-column", help="Name of email column in CSV"),
):
    """Contact Form Bot - Phase 1 (heuristics + Playwright)."""
    if mode not in ("test", "submit"):
        console.print("[red]mode must be 'test' or 'submit'[/red]")
        raise typer.Exit(1)
    if not input.exists():
        console.print(f"[red]Input file not found: {input}[/red]")
        raise typer.Exit(1)

    asyncio.run(
        run_bot(
            input_path=input,
            mode=mode,
            config_path=config,
            industry=industry,
            resume=resume,
            limit=limit,
            email_column=email_column,
        )
    )


if __name__ == "__main__":
    app()
