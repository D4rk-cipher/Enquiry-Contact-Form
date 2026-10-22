"""Extract unique domains from a list of emails."""

from __future__ import annotations

import csv
import re
from pathlib import Path


EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@([a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})$")


def extract_domain(email: str) -> str | None:
    email = (email or "").strip().lower()
    email = email.removeprefix("mailto:").strip("<> \t\"'")
    if not email or "@" not in email:
        return None
    match = EMAIL_RE.match(email)
    if not match:
        domain = email.split("@")[-1].strip().lower()
        if "." in domain and " " not in domain and len(domain) > 3:
            return domain
        return None
    domain = match.group(1).lower()
    for prefix in ("mail.", "email.", "smtp.", "webmail.", "mx."):
        if domain.startswith(prefix):
            domain = domain[len(prefix) :]
            break
    return domain


def _looks_like_email(s: str) -> bool:
    s = (s or "").strip().strip("<>\"'")
    return bool(s) and "@" in s and "." in s.split("@")[-1]


def load_emails_from_csv(path: str | Path, email_column: str | None = None) -> list[str]:
    """
    Load emails from:
      - CSV with a header row (email / Email / ...)
      - CSV with no header (one email per line)
      - Plain .txt list (one email per line)
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    if not lines:
        return []

    first = lines[0].strip().strip("<>\"'")
    header_words = {"email", "e-mail", "emails", "mail", "address", "email_address", "emailaddress"}

    # Plain list: first line is an email (no header)
    if "," not in first and "\t" not in first and _looks_like_email(first):
        return [ln.strip().strip("<>\"'") for ln in lines if _looks_like_email(ln)]

    emails: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except Exception:
            dialect = csv.excel

        has_header = True
        try:
            has_header = csv.Sniffer().has_header(sample)
        except Exception:
            has_header = True

        if not has_header and _looks_like_email(lines[0].split(",")[0]):
            reader = csv.reader(f, dialect)
            for row in reader:
                if not row:
                    continue
                val = (row[0] or "").strip().strip("<>\"'")
                if _looks_like_email(val):
                    emails.append(val)
            return emails

        reader = csv.DictReader(f, dialect=dialect)
        fieldnames = [c for c in (reader.fieldnames or []) if c]

        if email_column and email_column in fieldnames:
            col = email_column
        else:
            candidates = [c for c in fieldnames if c and "email" in c.lower()]
            if candidates:
                col = candidates[0]
            elif fieldnames:
                col = fieldnames[0]
            else:
                return [ln for ln in lines if _looks_like_email(ln)]

        # If DictReader treated an email as the header, recover it
        if _looks_like_email(col):
            emails.append(col.strip().strip("<>\"'"))

        for row in reader:
            val = (row.get(col) or "").strip().strip("<>\"'")
            if _looks_like_email(val):
                emails.append(val)

    if not emails:
        emails = [ln.strip().strip("<>\"'") for ln in lines if _looks_like_email(ln)]

    return emails


def emails_to_unique_domains(emails: list[str]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for email in emails:
        domain = extract_domain(email)
        if domain and domain not in seen:
            seen.add(domain)
            result.append((domain, email))
    return result


def load_domains_from_csv(
    path: str | Path, email_column: str | None = None
) -> list[tuple[str, str]]:
    emails = load_emails_from_csv(path, email_column)
    return emails_to_unique_domains(emails)
