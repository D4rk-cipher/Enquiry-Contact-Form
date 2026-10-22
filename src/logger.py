"""Logging, progress tracking and screenshot helpers."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RunLogger:
    def __init__(self, output_dir: str | Path = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "screenshots").mkdir(exist_ok=True)

        self.results_path = self.output_dir / "results.csv"
        self.captcha_path = self.output_dir / "needs_captcha.csv"
        self.inaccessible_path = self.output_dir / "inaccessible.csv"
        self.progress_path = self.output_dir / "progress.json"

        self._init_csv(self.results_path, [
            "timestamp", "domain", "original_email", "contact_url",
            "status", "notes", "screenshot_path"
        ])
        self._init_csv(self.captcha_path, [
            "timestamp", "domain", "original_email", "contact_url", "notes"
        ])
        self._init_csv(self.inaccessible_path, [
            "timestamp", "domain", "original_email", "contact_url", "notes"
        ])

        self.processed: set[str] = set()
        self._load_progress()

    def _init_csv(self, path: Path, headers: list[str]) -> None:
        if not path.exists():
            with path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)

    def _load_progress(self) -> None:
        if self.progress_path.exists():
            try:
                data = json.loads(self.progress_path.read_text(encoding="utf-8"))
                self.processed = set(data.get("processed_domains", []))
            except Exception:
                self.processed = set()

    def save_progress(self) -> None:
        data = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "processed_count": len(self.processed),
            "processed_domains": sorted(self.processed),
        }
        self.progress_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def is_processed(self, domain: str) -> bool:
        return domain.lower() in self.processed

    def mark_processed(self, domain: str) -> None:
        self.processed.add(domain.lower())
        self.save_progress()

    def log_result(
        self,
        domain: str,
        original_email: str,
        contact_url: str,
        status: str,
        notes: str = "",
        screenshot_path: str = "",
    ) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with self.results_path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                ts, domain, original_email, contact_url,
                status, notes, screenshot_path
            ])

        if status == "captcha":
            with self.captcha_path.open("a", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([ts, domain, original_email, contact_url, notes])

        if status == "inaccessible":
            with self.inaccessible_path.open("a", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([ts, domain, original_email, contact_url, notes])

        self.mark_processed(domain)

    def screenshot_path_for(self, domain: str, status: str = "") -> Path:
        safe = domain.replace(".", "_").replace("/", "_")[:80]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"{safe}_{status}_{ts}.png" if status else f"{safe}_{ts}.png"
        return self.output_dir / "screenshots" / name
