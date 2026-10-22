#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enquiry Contact Form Bot - Phase 1

Default: interactive menu
CLI still available for automation.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Prompt, Confirm
from rich.table import Table

from src.config import load_config, get_message, get_profile, list_templates
from src.domain_extractor import load_domains_from_csv
from src.browser import get_browser, new_page
from src.page_finder import find_contact_page
from src.form_filler import fill_form, submit_form
from src.captcha_detector import page_has_captcha
from src.logger import RunLogger
from src.utils import polite_delay

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
    timeout = int(settings.get("timeout_ms", 30_000))
    success_only = bool(settings.get("screenshot_on_success_only", True))

    page = await new_page(context)
    contact_url = ""
    status = "error"
    notes = ""
    screenshot_path = ""

    try:
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
        take_shot = False
        if success_only:
            if status in ("submitted", "filled_only"):
                take_shot = True
        else:
            take_shot = True

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

    console.print(f"Mode: [bold cyan]{mode}[/bold cyan] | Template: [cyan]{template_name or 'default'}[/cyan]")
    console.print(f"Delay ~ {delay}s | Profile email: {config['profile'].get('email')}")
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
                    domain, email, config, mode, template_name, logger, context
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
                    await polite_delay(delay)

    console.print()
    console.print("[bold green]Done.[/bold green] Results -> output/results.csv")
    console.print("CAPTCHA / manual -> output/needs_captcha.csv")
    console.print("Progress saved -> output/progress.json")


def interactive_menu() -> None:
    console.print(
        Panel.fit(
            "[bold cyan]Enquiry Contact Form Bot[/bold cyan]\nPhase 1",
            border_style="cyan",
        )
    )

    default_csv = Path("data/emails.csv")
    csv_path_str = Prompt.ask(
        "Path to email CSV",
        default=str(default_csv) if default_csv.exists() else "data/emails.csv",
    )
    csv_path = Path(csv_path_str)
    if not csv_path.exists():
        console.print(f"[red]File not found: {csv_path}[/red]")
        raise typer.Exit(1)

    templates = list_templates("data/templates")
    template_name: str | None = None

    if templates:
        table = Table(title="Available message templates", show_header=True)
        table.add_column("#", style="cyan", width=4)
        table.add_column("Template")
        for i, name in enumerate(templates, 1):
            table.add_row(str(i), name)
        console.print(table)

        choice = Prompt.ask(
            "Select template number (or press Enter for first)",
            default="1",
        )
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(templates):
                template_name = templates[idx]
        except ValueError:
            if choice in templates:
                template_name = choice
            else:
                template_name = templates[0] if templates else None
    else:
        console.print("[yellow]No templates found in data/templates/ - using config default[/yellow]")

    mode_choice = Prompt.ask(
        "Mode",
        choices=["test", "submit"],
        default="test",
    )

    resume = Confirm.ask("Resume previous run (skip already processed)?", default=True)
    limit_str = Prompt.ask("Limit to first N domains (Enter = all)", default="")
    limit = int(limit_str) if limit_str.strip().isdigit() else None

    console.print()
    console.print(
        f"[bold]Ready:[/bold] CSV={csv_path} | Template={template_name or 'default'} | Mode={mode_choice}"
    )
    if not Confirm.ask("Start now?", default=True):
        console.print("Cancelled.")
        raise typer.Exit(0)

    asyncio.run(
        run_bot(
            input_path=csv_path,
            mode=mode_choice,
            config_path=Path("config.yaml"),
            template_name=template_name,
            resume=resume,
            limit=limit,
            email_column=None,
        )
    )


@app.command()
def main(
    input: Optional[Path] = typer.Option(
        None, "--input", "-i", help="CSV file with emails (omit for interactive menu)"
    ),
    mode: str = typer.Option("test", "--mode", "-m", help="test | submit"),
    config: Path = typer.Option("config.yaml", "--config", "-c"),
    template: Optional[str] = typer.Option(
        None, "--template", "-t", help="Template name from data/templates/"
    ),
    industry: Optional[str] = typer.Option(
        None, "--industry", help="Alias for --template (legacy)"
    ),
    resume: bool = typer.Option(False, "--resume"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l"),
    email_column: Optional[str] = typer.Option(None, "--email-column"),
    menu: bool = typer.Option(False, "--menu", help="Force interactive menu"),
):
    """Enquiry Contact Form Bot. Run with no arguments for the interactive menu."""
    template_name = template or industry

    if input is None or menu:
        interactive_menu()
        return

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
            template_name=template_name,
            resume=resume,
            limit=limit,
            email_column=email_column,
        )
    )


if __name__ == "__main__":
    if len(sys.argv) == 1:
        interactive_menu()
    else:
        app()
