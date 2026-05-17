"""yt-dlp integration: download YouTube videos as a native Python library."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from yt_dlp import DownloadError as YtDlpError  # type: ignore[import-untyped]
from yt_dlp import YoutubeDL

from vk_uploader.models import DownloadError, DownloadResult


class YtDlpDownloader:
    """Wraps yt_dlp.YoutubeDL for downloading YouTube videos."""

    def __init__(
        self,
        output_dir: Path,
        video_format: str = "bv*+ba/b",
        on_progress: Callable[[dict[str, Any]], None] | None = None,
        on_log: Callable[[str], None] | None = None,
    ):
        self._output_dir = output_dir
        self._video_format = video_format
        self._on_progress = on_progress
        self._on_log = on_log

    def download(self, url: str) -> DownloadResult:
        """Download a YouTube video and return a DownloadResult with metadata."""
        self._output_dir.mkdir(parents=True, exist_ok=True)

        ydl_opts = {
            "format": self._video_format,
            "merge_output_format": "mp4",
            "outtmpl": str(self._output_dir / "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [self._on_progress_hook] if self._on_progress else [],
        }

        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise DownloadError("yt-dlp returned no info")
        except YtDlpError as e:
            raise DownloadError(str(e)) from e

        file_path_str = ydl.prepare_filename(info)
        actual = Path(file_path_str)
        final_path = actual.resolve()
        if not final_path.exists():
            stem = actual.stem
            candidates = list(self._output_dir.glob(f"{stem}.*"))
            if candidates:
                final_path = max(candidates, key=lambda p: p.stat().st_size)
            else:
                raise DownloadError(f"Downloaded file not found: {final_path}")

        return DownloadResult(
            file_path=final_path,
            title=info.get("title", "Untitled"),
            description=info.get("description", ""),
            thumbnail_url=info.get("thumbnail"),
            duration=int(info.get("duration", 0)),
            uploader=info.get("uploader", ""),
            webpage_url=info.get("webpage_url", url),
        )

    def _on_progress_hook(self, d: dict[str, Any]) -> None:
        """Bridge yt-dlp progress hook to our on_progress callback."""
        if self._on_progress:
            self._on_progress(d)
