"""yt-dlp integration: download YouTube videos via the standalone yt-dlp binary."""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from vk_uploader.models import BotDetectionError, DownloadError, DownloadResult

_YT_ID_RE = re.compile(r"([\w-]{11})")
_BOT_DETECTION_MARKERS = (
    "Sign in to confirm",
    "confirm you're not a bot",
    "This helps protect our community",
)


def _extract_youtube_id(url: str) -> str | None:
    """Extract the 11-char YouTube video ID from a URL."""
    parsed = urlparse(url)
    if parsed.netloc in ("www.youtube.com", "youtube.com", "m.youtube.com", "music.youtube.com"):
        qs = parse_qs(parsed.query)
        return qs.get("v", [None])[0]
    if parsed.netloc == "youtu.be":
        return parsed.path.lstrip("/")
    # Short links like https://youtube.com/shorts/VIDEO_ID
    m = _YT_ID_RE.search(parsed.path)
    if m:
        return m.group(1)
    return None


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
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    # Fall back to PATH lookup.
    found = shutil.which("yt-dlp")
    if found:
        return found
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


def _looks_like_bot_detection(output: str) -> bool:
    """Return True when yt-dlp output indicates YouTube bot detection."""
    return any(marker.lower() in output.lower() for marker in _BOT_DETECTION_MARKERS)


def _subtitle_langs_arg(target_lang: str) -> str:
    """Build a yt-dlp subtitle language selector with an English fallback."""
    lang = target_lang.strip()
    if not lang:
        return ""
    targets = [lang, f"{lang}.*"]
    if not lang.lower().startswith("en"):
        targets.extend(["en", "en.*"])
    return ",".join(targets)


class YtDlpDownloader:
    """Wraps the standalone yt-dlp binary for downloading YouTube videos."""

    def __init__(
        self,
        output_dir: Path,
        video_format: str = "bv*+ba[ext=m4a]/bv*+ba/b",
        on_progress: Callable[[dict[str, str]], None] | None = None,
        on_log: Callable[[str], None] | None = None,
        cookies_from_browser: str | None = None,
        subtitles_lang: str | None = None,
    ):
        self._output_dir = output_dir
        self._video_format = video_format
        self._on_progress = on_progress
        self._on_log = on_log
        self._binary = _find_ytdlp()
        self._cookies_from_browser = cookies_from_browser
        self._subtitles_lang = subtitles_lang

    def download(self, url: str) -> DownloadResult:
        """Download a YouTube video and return a DownloadResult with metadata."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        out_tpl = str(self._output_dir / "%(id)s.%(ext)s")

        # 1. Extract metadata (no download).
        info = self._extract_info(url)

        title = str(info.get("title", "Untitled"))
        description = str(info.get("description", ""))
        thumbnail_url = info.get("thumbnail")
        duration = int(str(info.get("duration", 0)))
        uploader = str(info.get("uploader", ""))
        video_id = str(info.get("id", _extract_youtube_id(url) or "unknown"))

        # 2. Check if the merged file already exists (skip re-download unless
        # subtitles were requested and are not present yet).
        for ext in (".mp4", ".mkv", ".webm"):
            candidate = self._output_dir / f"{video_id}{ext}"
            if candidate.exists() and candidate.stat().st_size > 0:
                srt_files = list(candidate.parent.glob(f"{candidate.stem}*.srt"))
                if self._subtitles_lang and not srt_files:
                    self._log(
                        f"File exists but subtitles are missing, running yt-dlp: {candidate}"
                    )
                    break
                self._log(f"Skipping download — file exists: {candidate}")
                return DownloadResult(
                    file_path=candidate,
                    title=title,
                    description=description,
                    thumbnail_url=str(thumbnail_url) if thumbnail_url else None,
                    duration=duration,
                    uploader=uploader,
                    webpage_url=url,
                    video_id=video_id,
                )

        # 3. Download.
        args = [
            self._binary,
            "--newline",
            "-f", self._video_format,
            "--merge-output-format", "mp4",
            # AV1 + faststart crashes ffmpeg; disable it.
            "--postprocessor-args", "ffmpeg:-movflags -faststart",
            "-o", out_tpl,
            "--no-playlist",
        ]
        if self._subtitles_lang:
            sub_langs = _subtitle_langs_arg(self._subtitles_lang)
            args += [
                "--write-subs",
                "--write-auto-subs",
                "--sub-langs", sub_langs,
                "--convert-subs", "srt",
            ]
        if self._cookies_from_browser:
            args += ["--cookies-from-browser", self._cookies_from_browser]
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
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
        except FileNotFoundError:
            raise DownloadError(f"yt-dlp binary not found at {self._binary}") from None

        assert proc.stdout is not None
        output_tail: list[str] = []
        for line in proc.stdout:
            line = line.rstrip("\n")
            output_tail.append(line)
            if len(output_tail) > 40:
                output_tail.pop(0)
            self._log(line)
            if self._on_progress:
                self._on_progress({"line": line})

        exit_code = proc.wait()
        if exit_code != 0:
            tail = "\n".join(output_tail)
            if _looks_like_bot_detection(tail):
                raise BotDetectionError(tail)
            # yt-dlp may have created the merged file despite a non-fatal
            # post-processing error (e.g. renaming a leftover .part file).
            merged_path = self._output_dir / f"{video_id}.mp4"
            if not merged_path.exists() or merged_path.stat().st_size == 0:
                raise DownloadError(
                    f"yt-dlp exited with code {exit_code}"
                )
            self._log(f"yt-dlp exited with code {exit_code} but merged file exists, continuing")

        # 3. Find the downloaded file.
        merged_path = self._output_dir / f"{video_id}.mp4"
        if merged_path.exists() and merged_path.stat().st_size > 0:
            return DownloadResult(
                file_path=merged_path,
                title=title,
                description=description,
                thumbnail_url=str(thumbnail_url) if thumbnail_url else None,
                duration=duration,
                uploader=uploader,
                webpage_url=url,
                video_id=video_id,
            )

        files = sorted(
            [
                f for f in self._output_dir.glob(f"{video_id}.*")
                if f.is_file() and f.suffix.lower() in (".mp4", ".mkv", ".webm")
            ],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if not files:
            raise DownloadError("Download completed but no output file found.")

        return DownloadResult(
            file_path=files[0],
            title=title,
            description=description,
            thumbnail_url=str(thumbnail_url) if thumbnail_url else None,
            duration=duration,
            uploader=uploader,
            webpage_url=url,
            video_id=video_id,
        )

    def _extract_info(self, url: str) -> dict[str, Any]:
        """Get video metadata without downloading."""
        import json

        args = [
            self._binary,
            "--dump-json",
            "--no-playlist",
        ]
        if self._cookies_from_browser:
            args += ["--cookies-from-browser", self._cookies_from_browser]
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
            output = "\n".join(part.strip() for part in (result.stderr, result.stdout) if part)
            if _looks_like_bot_detection(output):
                raise BotDetectionError(output)
            raise DownloadError(f"yt-dlp metadata failed: {output}")

        try:
            info: dict[str, Any] = json.loads(result.stdout)
            return info
        except json.JSONDecodeError as e:
            raise DownloadError(f"Failed to parse yt-dlp output: {e}") from e

    def _log(self, msg: str) -> None:
        if self._on_log:
            self._on_log(msg)
