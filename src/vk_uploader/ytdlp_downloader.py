"""yt-dlp integration: download YouTube videos via the standalone yt-dlp binary."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from vk_uploader.models import DownloadError, DownloadResult

_FFMPEG_CANDIDATES = [
    os.path.expanduser("~/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg"),
    os.path.expanduser("~/ffmpeg-git-*-amd64-static/ffmpeg"),
    os.path.expanduser("~/ffmpeg-*-amd64-static/ffmpeg"),
    "/usr/local/bin/ffmpeg",
    "/usr/bin/ffmpeg",
    "ffmpeg",
]


def _find_ffmpeg() -> str | None:
    """Return the path to a working ffmpeg, preferring custom static builds."""
    for pattern in _FFMPEG_CANDIDATES:
        if "*" in pattern:
            matches = sorted(glob.glob(pattern))
            if matches:
                return matches[-1]  # latest version
        elif Path(pattern).exists():
            return pattern
        elif pattern == "ffmpeg":
            found = shutil.which("ffmpeg")
            if found:
                return found
    return None


def _find_ytdlp() -> str:
    """Return the path to the standalone yt-dlp binary."""
    candidates = [
        os.path.expanduser("~/.local/bin/yt-dlp"),
        "/usr/local/bin/yt-dlp",
        "yt-dlp",
    ]
    for c in candidates:
        if Path(c).exists() or c == "yt-dlp":
            return c
    raise DownloadError(
        "yt-dlp binary not found. Install it:\n"
        "  curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \\\n"
        "    -o ~/.local/bin/yt-dlp && chmod +x ~/.local/bin/yt-dlp"
    )


def _build_env() -> dict[str, str]:
    """Return an environment dict that includes common tool paths."""
    env = os.environ.copy()
    extra_paths = [
        os.path.expanduser("~/.deno/bin"),
        os.path.expanduser("~/.local/bin"),
    ]
    existing = env.get("PATH", "")
    env["PATH"] = ":".join(extra_paths) + ":" + existing if existing else ""
    return env


def _deno_path() -> str | None:
    """Return the path to deno if available."""
    for loc in [
        os.path.expanduser("~/.deno/bin/deno"),
        "/usr/local/bin/deno",
        "/usr/bin/deno",
    ]:
        if Path(loc).exists():
            return loc
    found = shutil.which("deno")
    return found


class YtDlpDownloader:
    """Wraps the standalone yt-dlp binary for downloading YouTube videos."""

    def __init__(
        self,
        output_dir: Path,
        video_format: str = "bv*+ba[ext=m4a]/bv*+ba/b",
        on_progress: Callable[[dict[str, str]], None] | None = None,
        on_log: Callable[[str], None] | None = None,
    ):
        self._output_dir = output_dir
        self._video_format = video_format
        self._on_progress = on_progress
        self._on_log = on_log
        self._binary = _find_ytdlp()

    def download(self, url: str) -> DownloadResult:
        """Download a YouTube video and return a DownloadResult with metadata."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        out_tpl = str(self._output_dir / "%(title)s.%(ext)s")

        # 1. Extract metadata (no download).
        info = self._extract_info(url)

        title = str(info.get("title", "Untitled"))
        description = str(info.get("description", ""))
        thumbnail_url = info.get("thumbnail")
        duration = int(str(info.get("duration", 0)))
        uploader = str(info.get("uploader", ""))

        # 2. Download.
        args = [
            self._binary,
            "--newline",
            "-f", self._video_format,
            "--merge-output-format", "mp4",
            "-o", out_tpl,
            "--no-playlist",
        ]
        ffmpeg_path = _find_ffmpeg()
        if ffmpeg_path:
            args += ["--ffmpeg-location", ffmpeg_path]
        deno = _deno_path()
        if deno:
            args += ["--js-runtimes", "deno"]
        args.append(url)

        self._log(f"Command: {self._binary} -f {self._video_format} --merge-output-format mp4 ...")

        env = _build_env()
        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )
        except FileNotFoundError:
            raise DownloadError(f"yt-dlp binary not found at {self._binary}") from None

        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            self._log(line)
            if self._on_progress:
                self._on_progress({"line": line})

        # Collect stderr for error reporting.
        assert proc.stderr is not None
        stderr_lines = [line.rstrip("\n") for line in proc.stderr]
        for line in stderr_lines:
            self._log(line)

        exit_code = proc.wait()
        if exit_code != 0:
            detail = "\n".join(stderr_lines[-5:]) if stderr_lines else "no output"
            raise DownloadError(f"yt-dlp exited with code {exit_code}:\n{detail}")

        # 3. Find the downloaded file.
        files = sorted(
            [f for f in self._output_dir.iterdir() if f.is_file()],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        candidates = [f for f in files if f.suffix.lower() in (".mp4", ".mkv", ".webm")]
        if not candidates:
            candidates = files

        if not candidates:
            raise DownloadError("Download completed but no output file found.")

        return DownloadResult(
            file_path=candidates[0],
            title=title,
            description=description,
            thumbnail_url=str(thumbnail_url) if thumbnail_url else None,
            duration=duration,
            uploader=uploader,
            webpage_url=url,
        )

    def _extract_info(self, url: str) -> dict[str, Any]:
        """Get video metadata without downloading."""
        import json

        args = [
            self._binary,
            "--dump-json",
            "--no-playlist",
        ]
        deno = _deno_path()
        if deno:
            args += ["--js-runtimes", "deno"]
        args.append(url)
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=60, env=_build_env(),
            )
        except FileNotFoundError:
            raise DownloadError(f"yt-dlp binary not found at {self._binary}") from None

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise DownloadError(f"yt-dlp metadata failed: {stderr}")

        try:
            info: dict[str, Any] = json.loads(result.stdout)
            return info
        except json.JSONDecodeError as e:
            raise DownloadError(f"Failed to parse yt-dlp output: {e}") from e

    def _log(self, msg: str) -> None:
        if self._on_log:
            self._on_log(msg)
