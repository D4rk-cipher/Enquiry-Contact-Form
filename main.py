#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enquiry Contact Form Bot - Phase 1

Interactive (default):
  python main.py

CLI:
  python main.py --input data/emails.csv --mode test
  python main.py --input data/emails.csv --mode submit --resume --template real_estate
"""

from __future__ import annotations

import asyncio
import sys
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
from src import ui

app = typer.Typer(add_completion=False, help="Enquiry Contact Form Bot - Phase 1")
console = Console()


async def process_domain(
    domain: str,
    original_email: str,
    config: dict,
    mode: str,
    template_name: str | None,
    logger: RunLogger,
    context,
) -> str:
    settings = config["settings"]
    profile = get_profile(config)
    message = get_message(config, template_name)
    contact_paths = config["contact_paths"]
    keywords = config["contact_keywords"]
    timeout = min(int(settings.get("timeout_ms", 12_000)), 12_000)
    success_only = bool(settings.get("screenshot_on_success_only", True))

    page = await new_page(context)
    contact_url = ""
    status = "error"
    notes = ""
    screenshot_path = ""

    try:
        console.print(f"[cyan]{domain}[/cyan] → finding contact page…")
        result = await find_contact_page(
            page, domain, contact_paths, keywords, timeout_ms=timeout
        )

        if result.status == "inaccessible":
            status = "inaccessible"
            notes = result.notes or "homepage_unreachable"
            return status

        if result.status == "no_form":
            status = "no_form"
            notes = result.notes or "contact_page_not_found"
            return status

        contact_url = result.url or page.url
        console.print(f"[cyan]{domain}[/cyan] → {contact_url}")

        if await page_has_captcha(page):
            status = "captcha"
            notes = "captcha_or_challenge_detected"
            return status

        fill_result = await fill_form(page, profile, message)
        if not fill_result.ok:
            status = "error"
            notes = fill_result.notes or "fill_failed"
            return status

        notes = fill_result.notes

        if mode == "test":
            status = "filled_only"
            notes = "test_mode: " + notes
        else:
            clicked, sub_notes = await submit_form(page)
            if clicked:
                status = "submitted"
                notes = notes + " | " + sub_notes
                await page.wait_for_timeout(1500)
            else:
                status = "filled_only"
                notes = notes + " | " + sub_notes + " (submit_failed)"

        return status

    except Exception as e:
        status = "error"
        notes = f"{type(e).__name__}: {str(e)[:120]}"
        return status
    finally:
        take_shot = (not success_only) or status in ("submitted", "filled_only")
        if take_shot:
            try:
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
    template_name: Optional[str],
    resume: bool,
    limit: Optional[int],
    email_column: Optional[str],
) -> None:
    config = load_config(config_path)
    settings = config["settings"]
    d_min = float(settings.get("delay_min", settings.get("delay_between_domains_sec", 8)))
    d_max = float(settings.get("delay_max", max(d_min + 5, 15)))

    ok, msg, n = ui.validate_csv(input_path)
    if not ok:
        console.print(f"[red]Cannot start:[/red] {msg}")
        raise typer.Exit(1)

    for w in ui.validate_profile(config):
        console.print(f"[yellow]Warning:[/yellow] {w}")

    console.print(f"[bold]Loading domains from[/bold] {input_path}")
    pairs = load_domains_from_csv(input_path, email_column)
    console.print(f"Found [green]{len(pairs)}[/green] unique domains ({msg})")

    logger = RunLogger(output_dir="output")

    if resume:
        before = len(pairs)
        pairs = [(d, e) for d, e in pairs if not logger.is_processed(d)]
        console.print(
            f"Resume: skipped {before - len(pairs)} already processed → {len(pairs)} remaining"
        )

    if limit is not None and limit > 0:
        pairs = pairs[:limit]
        console.print(f"Limiting to first {limit} domains")

    if not pairs:
        console.print("[yellow]Nothing to process.[/yellow]")
        console.print(
            "[dim]Tip: all domains may already be in output/progress.json — "
            "delete it to re-run, or turn resume off.[/dim]"
        )
        return

    console.rule("[bold]Contact Form Bot[/bold]")
    console.print(f"  Mode     : [bold]{'SUBMIT' if mode == 'submit' else 'TEST (fill only)'}[/bold]")
    console.print(f"  Template : [cyan]{template_name or 'default'}[/cyan]")
    console.print(f"  Delay    : {d_min:.0f}–{d_max:.0f}s between domains")
    console.print(f"  Profile  : {config['profile'].get('email')}")
    console.rule()

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
                try:
                    status = await asyncio.wait_for(
                        process_domain(
                            domain, email, config, mode, template_name, logger, context
                        ),
                        timeout=90.0,
                    )
                except asyncio.TimeoutError:
                    status = "inaccessible"
                    console.print(f"  [red]{'inaccessible':14}[/red] {domain} (timed out)")
                    logger.log_result(
                        domain=domain,
                        original_email=email,
                        contact_url="",
                        status="inaccessible",
                        notes="domain_timeout_90s",
                        screenshot_path="",
                    )
                color = {
                    "submitted": "green",
                    "filled_only": "blue",
                    "captcha": "yellow",
                    "no_form": "magenta",
                    "inaccessible": "red",
                    "error": "red",
                }.get(status, "white")
                console.print(f"  [{color}]{status:14}[/{color}] {domain}")
                progress.advance(task)

                if idx < len(pairs):
                    await polite_delay(d_min, d_max)

    ui.print_run_summary(Path("output"))


def interactive_loop(config_path: Path = Path("config.yaml")) -> None:
    while True:
        action = ui.main_menu(config_path)

        if action == "exit":
            console.print("[dim]Bye.[/dim]")
            return

        if action == "profile":
            config = load_config(config_path)
            ui.show_profile(config)
            for w in ui.validate_profile(config):
                console.print(f"[yellow]• {w}[/yellow]")
            ui.pause()
            continue

        if action == "templates":
            ui.show_templates()
            ui.pause()
            continue

        if action == "results":
            ui.show_last_results(Path("output"))
            ui.pause()
            continue

        if action == "run":
            opts = ui.run_wizard(config_path)
            if not opts:
                continue
            try:
                asyncio.run(run_bot(**opts))
            except typer.Exit:
                pass
            except KeyboardInterrupt:
                console.print("\n[yellow]Stopped by user.[/yellow]")
            ui.pause()
            continue


@app.command()
def main(
    input: Optional[Path] = typer.Option(
        None, "--input", "-i", help="CSV / email list (omit for interactive menu)"
    ),
    mode: str = typer.Option("test", "--mode", "-m", help="test | submit"),
    config: Path = typer.Option("config.yaml", "--config", "-c"),
    template: Optional[str] = typer.Option(
        None, "--template", "-t", help="Template name from data/templates/"
    ),
    resume: bool = typer.Option(False, "--resume", help="Skip already processed domains"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l"),
    email_column: Optional[str] = typer.Option(None, "--email-column"),
    menu: bool = typer.Option(False, "--menu", help="Force interactive menu"),
):
    """Enquiry Contact Form Bot. No args → interactive menu."""
    if input is None or menu:
        interactive_loop(config)
        return

    if mode not in ("test", "submit"):
        console.print("[red]mode must be 'test' or 'submit'[/red]")
        raise typer.Exit(1)
    if not input.exists():
        console.print(f"[red]Input file not found: {input}[/red]")
        raise typer.Exit(1)

    ok, msg, _ = ui.validate_csv(input)
    if not ok:
        console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)

    asyncio.run(
        run_bot(
            input_path=input,
            mode=mode,
            config_path=config,
            template_name=template,
            resume=resume,
            limit=limit,
            email_column=email_column,
        )
    )


if __name__ == "__main__":
    if len(sys.argv) == 1:
        interactive_loop(Path("config.yaml"))
    else:
        app()
