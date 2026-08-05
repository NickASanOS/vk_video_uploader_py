"""Pipeline orchestration: download → upload → thumbnail."""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from rich.console import Console

from vk_uploader.logging_setup import create_download_progress
from vk_uploader.models import (
    AppConfig,
    BotDetectionError,
    DownloadError,
    DownloadResult,
    JobContext,
    PipelineStage,
    UploadError,
    UploadResult,
    VkSaveResponse,
)
from vk_uploader.vk_api import VkApiError, VkClient
from vk_uploader.ytdlp_downloader import YtDlpDownloader

_DOWNLOAD_PROGRESS_RE = re.compile(r"\[download\]\s+([\d.]+)%")
_DOWNLOAD_SPEED_RE = re.compile(r"at\s+(\S+)")
_DOWNLOAD_ETA_RE = re.compile(r"ETA\s+(\S+)")


def run_pipeline(console: Console, ctx: JobContext, config: AppConfig) -> None:
    """Execute the full download → upload workflow."""
    vk = VkClient(access_token=config.vk.access_token)

    result = _stage_download(console, ctx, config)
    if result is None:
        return

    _log_sub_status = _stage_subtitles(console, result.file_path, config)
    title, description = _stage_translate_metadata(console, ctx, config, result)
    description = f"{description}\n\n{ctx.youtube_url}".strip()

    publish_at = _build_publish_at(ctx)
    thumb_url = _select_thumbnail_url(result) if ctx.thumbnail_enabled else None
    album_id, album_status = _resolve_album(vk, ctx, console)
    save_response = _stage_vk_save(
        console, vk, ctx, title, description, publish_at, thumb_url, album_id,
    )
    if save_response is None:
        return

    upload_result = _stage_video_upload(console, vk, ctx, result, save_response)
    if upload_result is None:
        return

    thumbnail_ok = _stage_thumbnail_upload(
        console, vk, ctx, result, upload_result, thumb_url,
    )

    ctx.stage = PipelineStage.COMPLETED

    _print_summary(
        console,
        ctx,
        config,
        result,
        upload_result,
        publish_at,
        _log_sub_status,
        album_status,
        thumbnail_ok,
    )

    # ── Cleanup (optional) ──
    if config.defaults.cleanup_after_upload:
        _cleanup_downloaded_files(console, result.file_path)


def _stage_download(
    console: Console, ctx: JobContext, config: AppConfig
) -> DownloadResult | None:
    ctx.stage = PipelineStage.DOWNLOADING
    _log_stage(console, ctx.stage)

    progress = create_download_progress()
    task_id = progress.add_task("Downloading", total=100)

    def on_progress(d: dict[str, str]) -> None:
        line = d.get("line", "")
        # yt-dlp --newline outputs: [download]  45.2% of 1.2GiB at 5.0MiB/s ETA 02:30
        m = _DOWNLOAD_PROGRESS_RE.search(line)
        if m:
            pct = float(m.group(1))
            speed_m = _DOWNLOAD_SPEED_RE.search(line)
            eta_m = _DOWNLOAD_ETA_RE.search(line)
            parts = [f"{pct:.1f}%"]
            if speed_m:
                parts.append(f"{speed_m.group(1)}")
            if eta_m:
                parts.append(f"ETA {eta_m.group(1)}")
            desc = "Downloading [dim]" + " • ".join(parts) + "[/dim]"
            progress.update(task_id, completed=pct, description=desc)
        elif "[Merger]" in line:
            progress.update(
                task_id, total=None, completed=0,
                description="Merging video & audio...",
            )
        elif "[ExtractAudio]" in line:
            progress.update(
                task_id, total=None, completed=0,
                description="Extracting audio...",
            )
        elif "[VideoConvertor]" in line:
            progress.update(
                task_id, total=None, completed=0,
                description="Converting video...",
            )

    ytdlp_tail: list[str] = []

    def on_log(line: str) -> None:
        ytdlp_tail.append(line)
        if len(ytdlp_tail) > 20:
            ytdlp_tail.pop(0)

    downloader = YtDlpDownloader(
        output_dir=ctx.output_dir,
        video_format=config.download.video_format,
        on_progress=on_progress,
        on_log=on_log,
        cookies_from_browser=config.defaults.cookies_from_browser or None,
        subtitles_lang=config.defaults.lang if config.defaults.subtitles else None,
    )

    try:
        with progress:
            result = downloader.download(ctx.youtube_url)
            progress.update(task_id, completed=100, description="Done")
    except DownloadError as e:
        if isinstance(e, BotDetectionError):
            raise
        ctx.stage = PipelineStage.ERROR
        ctx.error_message = str(e)
        _log_error(console, str(e))
        if ytdlp_tail:
            console.print("[dim]Last yt-dlp output:[/dim]")
            for line in ytdlp_tail[-8:]:
                console.print(f"  [dim]{line}[/dim]")
        return None

    ctx.download_result = result
    console.print(f"[green]Downloaded:[/green] {result.file_path}")
    console.print(f"  Title: {result.title}")
    if result.description:
        console.print(f"  Description: {result.description[:120]}...")

    ctx.stage = PipelineStage.DOWNLOAD_COMPLETED
    return result


def _stage_translate_metadata(
    console: Console,
    ctx: JobContext,
    config: AppConfig,
    result: DownloadResult,
) -> tuple[str, str]:
    title = ctx.title_override or result.title
    description = ctx.description_override or result.description

    if not config.defaults.translation:
        return title, description

    lang = config.defaults.lang
    console.print(f"\n  Translating to [bold]{lang}[/bold]...")

    from vk_uploader.translate import translate_text

    warned = False

    def on_translation_error(error: Exception) -> None:
        nonlocal warned
        if warned:
            return
        warned = True
        console.print(f"  [yellow]Translation failed (non-fatal): {error}[/yellow]")

    translated_title = translate_text(title, lang, on_error=on_translation_error)
    if translated_title != title:
        console.print(f"  Title: [dim]{translated_title}[/dim]")

    translated_description = (
        translate_text(description, lang, on_error=on_translation_error)
        if description else ""
    )
    if translated_description != description:
        console.print(f"  Description: [dim]{translated_description[:120]}...[/dim]")

    if not ctx.title_override:
        title = translated_title
    if not ctx.description_override:
        description = translated_description

    return title, description


def _build_publish_at(ctx: JobContext) -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        hours=ctx.publish_delay_hours
    )


def _select_thumbnail_url(result: DownloadResult) -> str | None:
    if result.thumbnail_url:
        return result.thumbnail_url
    if result.video_id:
        return f"https://img.youtube.com/vi/{result.video_id}/maxresdefault.jpg"
    return None


def _resolve_album(
    vk: VkClient, ctx: JobContext, console: Console
) -> tuple[str | None, str]:
    if not ctx.album_spec:
        return None, ""

    from vk_uploader.vk_api import resolve_album

    return resolve_album(vk, ctx.group_id, ctx.album_spec, console)


def _stage_vk_save(
    console: Console,
    vk: VkClient,
    ctx: JobContext,
    title: str,
    description: str,
    publish_at: datetime.datetime,
    thumb_url: str | None,
    album_id: str | None,
) -> VkSaveResponse | None:
    ctx.stage = PipelineStage.UPLOADING_TO_VK
    _log_stage(console, ctx.stage)

    console.print(f"  Title: [bold]{title}[/bold]")
    console.print(f"  Scheduled for: [bold]{publish_at.isoformat()}[/bold]")

    if ctx.thumbnail_enabled:
        if thumb_url:
            console.print(f"  Thumbnail: [dim]{thumb_url}[/dim]")
        else:
            console.print("  [yellow]No thumbnail URL in YouTube metadata[/yellow]")

    try:
        save_response = vk.video_save(
            name=title,
            description=description,
            group_id=ctx.group_id,
            publish_at=publish_at,
            wallpost=ctx.wallpost,
            thumb_url=thumb_url,
            album_id=album_id,
        )
    except VkApiError as e:
        ctx.stage = PipelineStage.ERROR
        ctx.error_message = str(e)
        _log_error(console, str(e))
        return None

    ctx.vk_save_response = save_response
    return save_response


def _stage_video_upload(
    console: Console,
    vk: VkClient,
    ctx: JobContext,
    result: DownloadResult,
    save_response: VkSaveResponse,
) -> UploadResult | None:
    upload_progress = create_download_progress()
    upload_task = upload_progress.add_task("Uploading to VK", total=100)

    file_size_mb = result.file_path.stat().st_size / (1024 * 1024)

    def on_upload_progress(pct: float) -> None:
        desc = f"Uploading to VK [dim]{file_size_mb:.0f} MiB[/dim]"
        upload_progress.update(upload_task, completed=pct, description=desc)

    try:
        with upload_progress:
            upload_result = vk.upload_video_file(
                save_response.upload_url,
                result.file_path,
                on_progress=on_upload_progress,
            )
            upload_progress.update(upload_task, completed=100, description="Done")
    except (VkApiError, UploadError) as e:
        ctx.stage = PipelineStage.ERROR
        ctx.error_message = str(e)
        _log_error(console, str(e))
        return None

    ctx.upload_result = upload_result
    console.print("[green]Video uploaded.[/green]")
    console.print(f"  video_id: {upload_result.video_id}, owner_id: {upload_result.owner_id}")
    return upload_result


def _stage_thumbnail_upload(
    console: Console,
    vk: VkClient,
    ctx: JobContext,
    result: DownloadResult,
    upload_result: UploadResult,
    thumb_url: str | None,
) -> bool:
    if not thumb_url:
        return False

    ctx.stage = PipelineStage.UPLOADING_THUMBNAIL
    _log_stage(console, ctx.stage)

    from vk_uploader.thumbnail import download_thumbnail

    urls_to_try = [thumb_url]
    if result.thumbnail_url and result.thumbnail_url not in urls_to_try:
        urls_to_try.append(result.thumbnail_url)
    if result.video_id:
        neutral_url = f"https://img.youtube.com/vi/{result.video_id}/maxresdefault.jpg"
        if neutral_url not in urls_to_try:
            urls_to_try.append(neutral_url)

    local_thumb = None
    for url in urls_to_try:
        try:
            local_thumb = download_thumbnail(url, ctx.output_dir)
            break
        except UploadError:
            continue

    if local_thumb is None:
        console.print("[yellow]Thumbnail download failed (non-fatal).[/yellow]")
        return False

    try:
        resp = vk.upload_video_thumbnail(
            video_id=upload_result.video_id,
            owner_id=upload_result.owner_id,
            thumbnail_path=local_thumb,
        )
        photo_id = resp.get("photo_id", "?")
        console.print(f"[green]Thumbnail uploaded (photo_id={photo_id}).[/green]")
        return True
    except (VkApiError, UploadError) as e:
        console.print(f"[yellow]Thumbnail upload failed (non-fatal): {e}[/yellow]")
        return False
    finally:
        local_thumb.unlink(missing_ok=True)


def _print_summary(
    console: Console,
    ctx: JobContext,
    config: AppConfig,
    result: DownloadResult,
    upload_result: UploadResult,
    publish_at: datetime.datetime,
    sub_status: str,
    album_status: str,
    thumbnail_ok: bool,
) -> None:
    console.print("\n[bold]── Summary ──[/bold]")
    console.print(f"  Download:        [green]✓[/green] {result.file_path}")
    if config.defaults.translation:
        console.print(f"  Translation:     [green]✓[/green] → {config.defaults.lang}")
    if config.defaults.subtitles:
        sub_summary = sub_status if sub_status else "[green]✓[/green]"
        console.print(f"  Subtitles:       {sub_summary}")
    console.print(
        f"  Video upload:    [green]✓[/green] "
        f"(video_id: {upload_result.video_id}, owner_id: {upload_result.owner_id})"
    )
    if album_status:
        console.print(f"  Album:           {album_status}")
    if ctx.thumbnail_enabled:
        status = "[green]✓[/green]" if thumbnail_ok else "[red]✗[/red]"
        console.print(f"  Thumbnail:       {status}")
    if config.defaults.wallpost:
        console.print("  Wall post:       [green]✓[/green] (scheduled)")
    console.print(
        f"  Publish at:      {publish_at.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    console.print("[bold green]Done![/bold green]")


def _stage_subtitles(console: Console, video_path: Path, config: AppConfig) -> str:
    """Translate or prune sidecar SRT files for the downloaded video."""
    if not config.defaults.subtitles:
        return ""

    srt_files = _matching_srt_files(video_path)
    if not srt_files:
        return "[yellow]not found[/yellow]"

    lang = config.defaults.lang
    srt_files.sort(key=lambda p: _srt_score(p, lang), reverse=True)
    best_srt = srt_files[0]

    # Detect language of the best SRT.
    parts = best_srt.stem.rsplit(".", 1)
    srt_lang = parts[-1] if len(parts) > 1 else ""

    if srt_lang != lang and not srt_lang.startswith(lang[:2]):
        from vk_uploader.srt import parse_srt, translate_srt_entries, write_srt

        console.print(f"  Translating subtitles {srt_lang} → {lang}...")
        entries = parse_srt(best_srt)
        translated = translate_srt_entries(entries, lang)
        target_srt = video_path.with_suffix(f".{lang}.srt")
        write_srt(translated, target_srt)
        for f in srt_files:
            f.unlink(missing_ok=True)
        return f"translated {srt_lang} → {lang}"

    for f in srt_files:
        if f != best_srt:
            f.unlink(missing_ok=True)
    return f"[green]✓ ({srt_lang})[/green]"


def _matching_srt_files(video_path: Path) -> list[Path]:
    """Return SRT sidecars belonging exactly to *video_path*.

    Matches ``abc.srt`` and ``abc.<lang>.srt`` for ``abc.mp4`` but not
    ``abcd.srt``.
    """
    stem = video_path.stem
    plain = video_path.parent / f"{stem}.srt"
    matches = [plain] if plain.is_file() else []
    matches.extend(
        p for p in video_path.parent.glob(f"{stem}.*.srt")
        if p.is_file()
    )
    return matches


def _srt_score(path: Path, lang: str) -> int:
    parts = path.stem.rsplit(".", 1)
    code = parts[-1] if len(parts) > 1 else ""
    if code == lang:
        return 3
    if code.startswith(lang[:2]):
        return 2
    if code.startswith("en"):
        return 1
    return 0


def _cleanup_downloaded_files(console: Console, video_path: Path) -> None:
    """Remove downloaded video and its SRT sidecars after successful upload."""
    console.print()
    console.print("[dim]Cleaning up downloaded files...[/dim]")
    if video_path.exists():
        video_path.unlink()
        console.print(f"  [dim]Removed: {video_path.name}[/dim]")
    for srt_file in _matching_srt_files(video_path):
        srt_file.unlink(missing_ok=True)
        console.print(f"  [dim]Removed: {srt_file.name}[/dim]")
    console.print("[green]Cleanup complete.[/green]")


def _log_stage(console: Console, stage: PipelineStage) -> None:
    console.print(f"\n[bold cyan]── {stage.label} ──[/bold cyan]")


def _log_error(console: Console, message: str) -> None:
    console.print(f"\n[bold red]Error:[/bold red] {message}")
