"""Pipeline orchestration: download → upload → thumbnail."""

from __future__ import annotations

import datetime
from pathlib import Path

from rich.console import Console

from vk_uploader.logging_setup import create_download_progress
from vk_uploader.models import (
    AppConfig,
    BotDetectionError,
    DownloadError,
    JobContext,
    PipelineStage,
    UploadError,
)
from vk_uploader.vk_api import VkApiError, VkClient
from vk_uploader.ytdlp_downloader import YtDlpDownloader


def run_pipeline(console: Console, ctx: JobContext, config: AppConfig) -> None:
    """Execute the full download → upload workflow."""
    vk = VkClient(access_token=config.vk.access_token)

    # --- Stage: Download ---
    ctx.stage = PipelineStage.DOWNLOADING
    _log_stage(console, ctx.stage)

    progress = create_download_progress()
    task_id = progress.add_task("Downloading", total=100)

    import re

    def on_progress(d: dict[str, str]) -> None:
        line = d.get("line", "")
        # yt-dlp --newline outputs: [download]  45.2% of 1.2GiB at 5.0MiB/s ETA 02:30
        m = re.search(r"\[download\]\s+([\d.]+)%", line)
        if m:
            pct = float(m.group(1))
            speed_m = re.search(r"at\s+(\S+)", line)
            eta_m = re.search(r"ETA\s+(\S+)", line)
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

    # Collect the last N lines of yt-dlp output for error reporting.
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
            # If download was instant (cached), ensure bar shows 100%.
            progress.update(task_id, completed=100, description="Done")
    except DownloadError as e:
        # Re-raise BotDetectionError so the CLI can prompt for browser cookies.
        if isinstance(e, BotDetectionError):
            raise
        ctx.stage = PipelineStage.ERROR
        ctx.error_message = str(e)
        _log_error(console, str(e))
        if ytdlp_tail:
            console.print("[dim]Last yt-dlp output:[/dim]")
            for line in ytdlp_tail[-8:]:
                console.print(f"  [dim]{line}[/dim]")
        return

    ctx.download_result = result
    progress.stop()
    console.print(f"[green]Downloaded:[/green] {result.file_path}")
    console.print(f"  Title: {result.title}")
    if result.description:
        console.print(f"  Description: {result.description[:120]}...")

    ctx.stage = PipelineStage.DOWNLOAD_COMPLETED

    # --- Subtitle processing (optional) ---
    if config.defaults.subtitles:
        _log_sub_status = ""

        video_stem = result.file_path.stem
        srt_files = sorted(result.file_path.parent.glob(f"{video_stem}*.srt"))

        if srt_files:
            lang = config.defaults.lang

            def _srt_score(p: Path) -> int:
                parts = p.stem.rsplit(".", 1)
                code = parts[-1] if len(parts) > 1 else ""
                if code == lang:
                    return 3
                if code.startswith(lang[:2]):
                    return 2
                if code.startswith("en"):
                    return 1
                return 0

            srt_files.sort(key=_srt_score, reverse=True)
            best_srt = srt_files[0]

            # Detect language of the best SRT.
            parts = best_srt.stem.rsplit(".", 1)
            srt_lang = parts[-1] if len(parts) > 1 else ""

            if srt_lang != lang and not srt_lang.startswith(lang[:2]):
                # Translate to target language.
                from vk_uploader.srt import parse_srt, translate_srt_entries, write_srt

                console.print(f"  Translating subtitles {srt_lang} → {lang}...")
                entries = parse_srt(best_srt)
                translated = translate_srt_entries(entries, lang)
                target_srt = result.file_path.with_suffix(f".{lang}.srt")
                write_srt(translated, target_srt)
                _log_sub_status = f"translated {srt_lang} → {lang}"
                # Clean up all raw SRT files downloaded by yt-dlp.
                for f in srt_files:
                    f.unlink(missing_ok=True)
            else:
                _log_sub_status = f"[green]✓ ({srt_lang})[/green]"
                # Keep only the target language SRT, clean up the rest.
                for f in srt_files:
                    if f != best_srt:
                        f.unlink(missing_ok=True)
        else:
            _log_sub_status = "[yellow]not found[/yellow]"

    # --- Translation (optional) ---
    title = ctx.title_override or result.title
    description = ctx.description_override or result.description

    if config.defaults.translation:
        lang = config.defaults.lang
        console.print(f"\n  Translating to [bold]{lang}[/bold]...")

        from vk_uploader.translate import translate_text

        t_title = translate_text(title, lang)
        if t_title != title:
            console.print(f"  Title: [dim]{t_title}[/dim]")

        t_desc = translate_text(description, lang) if description else ""
        if t_desc != description:
            console.print(f"  Description: [dim]{t_desc[:120]}...[/dim]")

        # Use translated values only if user didn't provide explicit overrides.
        if not ctx.title_override:
            title = t_title
        if not ctx.description_override:
            description = t_desc

    # Always append the YouTube link to the description.
    description = f"{description}\n\n{ctx.youtube_url}".strip()

    # --- Stage: Upload to VK ---
    ctx.stage = PipelineStage.UPLOADING_TO_VK
    _log_stage(console, ctx.stage)

    publish_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        hours=ctx.publish_delay_hours
    )

    console.print(f"  Title: [bold]{title}[/bold]")
    console.print(f"  Scheduled for: [bold]{publish_at.isoformat()}[/bold]")

    thumb_url: str | None = None
    if ctx.thumbnail_enabled:
        # Build priority list: lang-specific → neutral → yt-dlp fallback.
        if result.video_id:
            lang = config.defaults.lang
            thumb_url = f"https://img.youtube.com/vi/{result.video_id}/maxresdefault_{lang}.jpg"
        elif result.thumbnail_url:
            thumb_url = result.thumbnail_url

        if thumb_url:
            console.print(f"  Thumbnail: [dim]{thumb_url}[/dim]")
        else:
            console.print("  [yellow]No thumbnail URL in YouTube metadata[/yellow]")

    # --- Album resolution (optional) ---
    album_id: str | None = None
    album_status = ""
    if ctx.album_spec:
        from vk_uploader.vk_api import resolve_album

        album_id, album_status = resolve_album(
            vk, ctx.group_id, ctx.album_spec, console,
        )

    # video.save (without thumb_url — unsupported by VK API 5.199).
    try:
        save_response = vk.video_save(
            name=title,
            description=description,
            group_id=ctx.group_id,
            publish_at=publish_at,
            wallpost=ctx.wallpost,
            album_id=album_id,
        )
    except VkApiError as e:
        ctx.stage = PipelineStage.ERROR
        ctx.error_message = str(e)
        _log_error(console, str(e))
        return

    ctx.vk_save_response = save_response

    # Upload video file with progress bar.
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
        return

    ctx.upload_result = upload_result
    upload_progress.stop()
    console.print("[green]Video uploaded.[/green]")
    console.print(f"  video_id: {upload_result.video_id}, owner_id: {upload_result.owner_id}")

    # ── Upload thumbnail separately ──
    thumbnail_ok = True
    if thumb_url:
        ctx.stage = PipelineStage.UPLOADING_THUMBNAIL
        _log_stage(console, ctx.stage)

        from vk_uploader.thumbnail import download_thumbnail

        # Build fallback chain: lang-specific → yt-dlp → neutral.
        urls_to_try = [thumb_url]
        if result.thumbnail_url and result.thumbnail_url not in urls_to_try:
            urls_to_try.append(result.thumbnail_url)
        if result.video_id:
            lang = config.defaults.lang
            neutral_url = f"https://img.youtube.com/vi/{result.video_id}/maxresdefault.jpg"
            if neutral_url not in urls_to_try:
                urls_to_try.append(neutral_url)

        local_thumb = None
        for url in urls_to_try:
            try:
                local_thumb = download_thumbnail(url, ctx.output_dir)
                break
            except (UploadError, Exception):
                continue

        if local_thumb is None:
            console.print("[yellow]Thumbnail download failed (non-fatal).[/yellow]")
            thumbnail_ok = False
        else:
            try:
                resp = vk.upload_video_thumbnail(
                    video_id=upload_result.video_id,
                    owner_id=upload_result.owner_id,
                    thumbnail_path=local_thumb,
                )
                photo_id = resp.get("photo_id", "?")
                console.print(f"[green]Thumbnail uploaded (photo_id={photo_id}).[/green]")
            except (VkApiError, UploadError) as e:
                console.print(f"[yellow]Thumbnail upload failed (non-fatal): {e}[/yellow]")
                thumbnail_ok = False
            finally:
                local_thumb.unlink(missing_ok=True)
    else:
        thumbnail_ok = False

    ctx.stage = PipelineStage.COMPLETED

    # ── Summary ──
    console.print("\n[bold]── Summary ──[/bold]")
    console.print(f"  Download:        [green]✓[/green] {result.file_path}")
    if config.defaults.translation:
        console.print(f"  Translation:     [green]✓[/green] → {config.defaults.lang}")
    if config.defaults.subtitles:
        sub_summary = _log_sub_status if _log_sub_status else "[green]✓[/green]"
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


def _log_stage(console: Console, stage: PipelineStage) -> None:
    console.print(f"\n[bold cyan]── {stage.label} ──[/bold cyan]")


def _log_error(console: Console, message: str) -> None:
    console.print(f"\n[bold red]Error:[/bold red] {message}")
