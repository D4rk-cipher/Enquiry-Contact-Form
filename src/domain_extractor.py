"""Extract unique domains from a list of emails."""

from __future__ import annotations

import csv
import re
from pathlib import Path


EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@([a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})$")


def extract_domain(email: str) -> str | None:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return None
    match = EMAIL_RE.match(email)
    if not match:
        domain = email.split("@")[-1].strip().lower()
        if "." in domain and " " not in domain:
            return domain
        return None
    domain = match.group(1).lower()
    for prefix in ("mail.", "email.", "smtp.", "webmail.", "mx."):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
            break
    return domain


def load_emails_from_csv(path: str | Path, email_column: str | None = None) -> list[str]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    emails: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        if email_column and email_column in fieldnames:
            col = email_column
        else:
            candidates = [c for c in fieldnames if c and "email" in c.lower()]
            if candidates:
                col = candidates[0]
            elif fieldnames:
                col = fieldnames[0]
            else:
                f.seek(0)
                return [line.strip() for line in f if line.strip() and "@" in line]

        for row in reader:
            val = (row.get(col) or "").strip()
            if val and "@" in val:
                emails.append(val)

    return emails


def emails_to_unique_domains(emails: list[str]) -> list[tuple[str, str]]:
    """Returns list of (domain, original_email) keeping first occurrence of each domain."""
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for email in emails:
        domain = extract_domain(email)
        if domain and domain not in seen:
            seen.add(domain)
            result.append((domain, email))
    return result


def load_domains_from_csv(path: str | Path, email_column: str | None = None) -> list[tuple[str, str]]:
    emails = load_emails_from_csv(path, email_column)
    return emails_to_unique_domains(emails)
