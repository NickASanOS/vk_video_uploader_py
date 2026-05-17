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
            pct_str = d.get("_percent_str", "0%").strip().rstrip("%")
            try:
                pct = float(pct_str)
            except ValueError:
                pct = 0
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

    # --- Stage: Upload to VK ---
    ctx.stage = PipelineStage.UPLOADING_TO_VK
    _log_stage(console, ctx.stage)

    publish_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        hours=ctx.publish_delay_hours
    )

    title = ctx.title_override or result.title
    description = ctx.description_override or result.description

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
    import json
    console.print(
        f"  [dim]video.save: upload_url={save_response.upload_url}, "
        f"video_id={save_response.video_id}, owner_id={save_response.owner_id}[/dim]"
    )

    # Upload video file.
    console.print("  Uploading video to VK...")
    try:
        upload_result = vk.upload_video_file(save_response.upload_url, result.file_path)
    except VkApiError as e:
        ctx.stage = PipelineStage.ERROR
        ctx.error_message = str(e)
        _log_error(console, str(e))
        return

    ctx.upload_result = upload_result
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
            console.print(
                f"  [dim]thumb response: {json.dumps(resp, indent=2, ensure_ascii=False)}[/dim]"
            )
            console.print("[green]Thumbnail uploaded.[/green]")
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
