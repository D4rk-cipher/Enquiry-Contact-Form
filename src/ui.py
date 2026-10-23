"""Interactive menu, validation, and run summary UI."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .config import get_profile, list_templates, load_config
from .domain_extractor import load_domains_from_csv, load_emails_from_csv

console = Console()


def banner() -> None:
    console.print(
        Panel.fit(
            "[bold cyan]Enquiry Contact Form Bot[/bold cyan]\n"
            "[dim]Phase 1 — find forms, fill them, log results[/dim]",
            border_style="cyan",
        )
    )


def pause(msg: str = "Press Enter to continue…") -> None:
    try:
        Prompt.ask(f"[dim]{msg}[/dim]", default="")
    except Exception:
        pass


def ask_choice(title: str, options: list[str], default: int = 1) -> int:
    console.print(f"\n[bold]{title}[/bold]")
    for i, opt in enumerate(options, 1):
        mark = " [dim](default)[/dim]" if i == default else ""
        console.print(f"  [cyan]{i}[/cyan]) {opt}{mark}")
    console.print()
    while True:
        raw = Prompt.ask("Choice", default=str(default))
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw)
        console.print(f"[red]Enter a number from 1 to {len(options)}[/red]")


def validate_csv(path: Path) -> tuple[bool, str, int]:
    if not path.exists():
        return False, f"File not found: {path}", 0
    if not path.is_file():
        return False, f"Not a file: {path}", 0
    try:
        emails = load_emails_from_csv(path)
        if not emails:
            return (
                False,
                "No emails found. Use one email per line, or a CSV with an email column.",
                0,
            )
        pairs = load_domains_from_csv(path)
        if not pairs:
            return False, "Emails found but no valid domains could be extracted.", 0
        return True, f"{len(emails)} email(s) → {len(pairs)} unique domain(s)", len(pairs)
    except Exception as e:
        return False, f"Could not read file: {e}", 0


def validate_profile(config: dict) -> list[str]:
    profile = get_profile(config)
    warnings: list[str] = []
    if not profile.get("email") or "@" not in profile.get("email", ""):
        warnings.append("profile.email is missing or invalid — forms need your email")
    if not (profile.get("first_name") or profile.get("full_name")):
        warnings.append("profile first_name / full_name is empty")
    msg = (config.get("default_message") or "").strip()
    templates = list_templates("data/templates")
    if not msg and not templates:
        warnings.append("No default_message and no templates in data/templates/")
    return warnings


def show_profile(config: dict) -> None:
    profile = get_profile(config)
    table = Table(title="Your profile (config.yaml)", show_header=True, header_style="bold")
    table.add_column("Field", style="cyan", width=18)
    table.add_column("Value")
    for key in (
        "first_name", "last_name", "full_name", "email", "phone",
        "company", "website", "job_title",
    ):
        table.add_row(key, str(profile.get(key) or "[dim]—[/dim]"))
    console.print(table)
    console.print("[dim]Edit config.yaml to change these values.[/dim]")


def show_templates() -> None:
    templates = list_templates("data/templates")
    if not templates:
        console.print("[yellow]No templates in data/templates/[/yellow]")
        return
    table = Table(title="Message templates", show_header=True, header_style="bold")
    table.add_column("#", width=4)
    table.add_column("Name")
    table.add_column("Preview", max_width=50)
    for i, name in enumerate(templates, 1):
        path = Path("data/templates") / f"{name}.txt"
        preview = ""
        try:
            text = path.read_text(encoding="utf-8").strip().replace("\n", " ")
            preview = (text[:50] + "…") if len(text) > 50 else text
        except Exception:
            preview = "—"
        table.add_row(str(i), name, preview)
    console.print(table)


def show_last_results(output_dir: Path = Path("output")) -> None:
    results = output_dir / "results.csv"
    if not results.exists():
        console.print("[yellow]No results yet (output/results.csv missing).[/yellow]")
        return
    counts: dict[str, int] = {}
    rows = 0
    try:
        with results.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows += 1
                st = (row.get("status") or "unknown").strip()
                counts[st] = counts.get(st, 0) + 1
    except Exception as e:
        console.print(f"[red]Could not read results: {e}[/red]")
        return

    if rows == 0:
        console.print("[yellow]results.csv is empty.[/yellow]")
        return

    table = Table(title=f"Results summary ({rows} rows)", header_style="bold")
    table.add_column("Status", style="cyan")
    table.add_column("Count", justify="right")
    colors = {
        "submitted": "green",
        "filled_only": "blue",
        "captcha": "yellow",
        "no_form": "magenta",
        "inaccessible": "red",
        "error": "red",
    }
    for st, n in sorted(counts.items(), key=lambda x: -x[1]):
        c = colors.get(st, "white")
        table.add_row(f"[{c}]{st}[/{c}]", str(n))
    console.print(table)
    console.print(
        f"[dim]Full log: {results} · CAPTCHA: output/needs_captcha.csv · "
        f"Dead sites: output/inaccessible.csv[/dim]"
    )


def pick_csv() -> Path | None:
    default = Path("data/emails.csv")
    while True:
        raw = Prompt.ask(
            "Path to email list (CSV or one email per line)",
            default=str(default) if default.exists() else "data/emails.csv",
        )
        path = Path(raw.strip().strip('"').strip("'"))
        ok, msg, _ = validate_csv(path)
        if ok:
            console.print(f"  [green]✓[/green] {msg}")
            return path
        console.print(f"  [red]✗[/red] {msg}")
        if not Confirm.ask("Try another path?", default=True):
            return None


def pick_template() -> str | None:
    templates = list_templates("data/templates")
    if not templates:
        console.print("[yellow]No templates — will use default_message from config.yaml[/yellow]")
        return None
    labels = [t.replace("_", " ").title() for t in templates]
    idx = ask_choice("Message template", labels, default=1)
    choice = templates[idx - 1]
    console.print(f"  → [green]{choice}[/green]")
    return choice


def pick_mode() -> str:
    idx = ask_choice(
        "Mode",
        [
            "Test — fill forms only, do not submit",
            "Submit — fill and send the forms",
        ],
        default=1,
    )
    return "test" if idx == 1 else "submit"


def pick_limit(max_domains: int) -> int | None:
    console.print(f"\n[dim]{max_domains} domain(s) available.[/dim]")
    raw = Prompt.ask("Limit to first N domains (Enter = all)", default="").strip()
    if not raw:
        return None
    if raw.isdigit() and int(raw) > 0:
        return min(int(raw), max_domains)
    console.print("[yellow]Invalid limit — using all domains.[/yellow]")
    return None


def run_wizard(config_path: Path = Path("config.yaml")) -> dict[str, Any] | None:
    banner()
    config = load_config(config_path)

    warnings = validate_profile(config)
    if warnings:
        console.print(Panel(
            "\n".join(f"• {w}" for w in warnings),
            title="[yellow]Profile warnings[/yellow]",
            border_style="yellow",
        ))
        if not Confirm.ask("Continue anyway?", default=True):
            return None

    csv_path = pick_csv()
    if not csv_path:
        console.print("[dim]Cancelled.[/dim]")
        return None

    ok, msg, n_domains = validate_csv(csv_path)
    template = pick_template()
    mode = pick_mode()
    resume = Confirm.ask("Resume previous run (skip already processed domains)?", default=True)
    limit = pick_limit(n_domains)

    console.print()
    summary = Table(title="Ready to run", show_header=False, box=None)
    summary.add_column("k", style="dim", width=14)
    summary.add_column("v")
    summary.add_row("CSV", str(csv_path))
    summary.add_row("Domains", msg)
    summary.add_row("Template", template or "default message")
    summary.add_row("Mode", "[bold]SUBMIT[/bold]" if mode == "submit" else "TEST (fill only)")
    summary.add_row("Resume", "yes" if resume else "no")
    summary.add_row("Limit", str(limit) if limit else "all")
    summary.add_row("Profile email", get_profile(config).get("email", "—"))
    console.print(summary)
    console.print()

    if mode == "submit":
        console.print("[bold yellow]Submit mode will actually send forms to websites.[/bold yellow]")
        if not Confirm.ask("Are you sure?", default=False):
            console.print("[dim]Cancelled.[/dim]")
            return None
    elif not Confirm.ask("Start now?", default=True):
        console.print("[dim]Cancelled.[/dim]")
        return None

    return {
        "input_path": csv_path,
        "mode": mode,
        "config_path": config_path,
        "template_name": template,
        "resume": resume,
        "limit": limit,
        "email_column": None,
    }


def main_menu(config_path: Path = Path("config.yaml")) -> str:
    banner()
    idx = ask_choice(
        "Main menu",
        [
            "Start a run (pick CSV, template, mode)",
            "View / check profile",
            "View message templates",
            "View last results summary",
            "Exit",
        ],
        default=1,
    )
    return ["run", "profile", "templates", "results", "exit"][idx - 1]


def print_run_summary(logger_output: Path = Path("output")) -> None:
    console.print()
    console.rule("[bold green]Run finished[/bold green]")
    show_last_results(logger_output)
    console.print()
    console.print("[bold]Output files[/bold]")
    console.print("  • output/results.csv")
    console.print("  • output/needs_captcha.csv")
    console.print("  • output/inaccessible.csv")
    console.print("  • output/progress.json")
    console.print("  • output/screenshots/  [dim](success only)[/dim]")
