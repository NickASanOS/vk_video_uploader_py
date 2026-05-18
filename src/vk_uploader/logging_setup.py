"""Rich console setup: progress bars and coloured output."""

from __future__ import annotations

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

