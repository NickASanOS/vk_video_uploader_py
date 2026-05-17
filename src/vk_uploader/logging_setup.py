"""Rich console setup: progress bars and coloured output."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)


def create_console() -> Console:
    return Console()


_PROGRESS_COLUMNS = [
    SpinnerColumn(),
    TextColumn("[bold]{task.description}"),
    BarColumn(),
    TaskProgressColumn(),
    TextColumn("•"),
    TimeRemainingColumn(elapsed_when_finished=True),
]


def create_download_progress() -> Progress:
    return Progress(*_PROGRESS_COLUMNS)


def format_progress(d: dict[str, Any]) -> str:
    """Convert a yt-dlp progress dict to a short display string."""
    status = d.get("status", "")
    if status == "downloading":
        pct = d.get("_percent_str", "??%").strip()
        speed = d.get("_speed_str", "??")
        eta = d.get("_eta_str", "??")
        return f"{pct} @ {speed} • ETA {eta}"
    elif status == "finished":
        return "Processing..."
    return str(status)
