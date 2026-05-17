"""Pipeline orchestration: download → upload → thumbnail."""

from __future__ import annotations

import datetime
from typing import Any

from rich.console import Console

from vk_uploader.logging_setup import create_download_progress, format_progress
from vk_uploader.models import (
    AppConfig,
    DownloadError,
    JobContext,
    PipelineStage,
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

    def on_progress(d: dict[str, Any]) -> None:
        status = d.get("status", "")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            pct = (d.get("downloaded_bytes", 0) / total * 100) if total else 0
            desc = f"Downloading [dim]{format_progress(d)}[/dim]"
            progress.update(task_id, completed=pct, description=desc)
        elif status == "finished":
            progress.update(task_id, completed=100, description="Processing...")

    downloader = YtDlpDownloader(
        output_dir=ctx.output_dir,
        video_format=config.download.video_format,
        on_progress=on_progress,
    )

    try:
        with progress:
            result = downloader.download(ctx.youtube_url)
            # If download was instant (cached), ensure bar shows 100%.
            progress.update(task_id, completed=100, description="Done")
    except DownloadError as e:
        ctx.stage = PipelineStage.ERROR
        ctx.error_message = str(e)
        _log_error(console, str(e))
        return

    ctx.download_result = result
    progress.stop()
    console.print(f"[green]Downloaded:[/green] {result.file_path}")
    console.print(f"  Title: {result.title}")
    if result.description:
        console.print(f"  Description: {result.description[:120]}...")

    ctx.stage = PipelineStage.DOWNLOAD_COMPLETED

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

    # --- Stage: Upload to VK ---
    ctx.stage = PipelineStage.UPLOADING_TO_VK
    _log_stage(console, ctx.stage)

    publish_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        hours=ctx.publish_delay_hours
    )

    console.print(f"  Title: [bold]{title}[/bold]")
    console.print(f"  Scheduled for: [bold]{publish_at.isoformat()}[/bold]")

    thumb_url = result.thumbnail_url if ctx.thumbnail_enabled else None
    if ctx.thumbnail_enabled:
        if thumb_url:
            console.print(f"  Thumbnail: [dim]{thumb_url}[/dim]")
        else:
            console.print("  [yellow]No thumbnail URL in YouTube metadata[/yellow]")

    # video.save (without thumb_url — unsupported by VK API 5.199).
    try:
        save_response = vk.video_save(
            name=title,
            description=description,
            group_id=ctx.group_id,
            publish_at=publish_at,
            wallpost=ctx.wallpost,
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
    except VkApiError as e:
        ctx.stage = PipelineStage.ERROR
        ctx.error_message = str(e)
        _log_error(console, str(e))
        return

    ctx.upload_result = upload_result
    upload_progress.stop()
    console.print("[green]Video uploaded.[/green]")
    console.print(f"  video_id: {upload_result.video_id}, owner_id: {upload_result.owner_id}")

    # ── Upload thumbnail separately ──
    if thumb_url:
        ctx.stage = PipelineStage.UPLOADING_THUMBNAIL
        _log_stage(console, ctx.stage)

        from vk_uploader.thumbnail import download_thumbnail

        local_thumb = download_thumbnail(thumb_url, ctx.output_dir)
        try:
            resp = vk.upload_video_thumbnail(
                video_id=upload_result.video_id,
                owner_id=upload_result.owner_id,
                thumbnail_path=local_thumb,
            )
            photo_id = resp.get("photo_id", "?")
            console.print(f"[green]Thumbnail uploaded (photo_id={photo_id}).[/green]")
        except VkApiError as e:
            console.print(f"[yellow]Thumbnail upload failed (non-fatal): {e}[/yellow]")
        finally:
            local_thumb.unlink(missing_ok=True)

    ctx.stage = PipelineStage.COMPLETED
    _log_stage(console, ctx.stage)
    console.print("[bold green]Done![/bold green]")


def _log_stage(console: Console, stage: PipelineStage) -> None:
    console.print(f"\n[bold cyan]── {stage.label} ──[/bold cyan]")


def _log_error(console: Console, message: str) -> None:
    console.print(f"\n[bold red]Error:[/bold red] {message}")
