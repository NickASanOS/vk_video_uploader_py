"""VK API client: HTTP wrapper for video upload workflow."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rich.console import Console

import requests
from requests_toolbelt import (  # type: ignore[import-untyped]
    MultipartEncoder,
    MultipartEncoderMonitor,
)

from vk_uploader.models import UploadError, UploadResult, VkSaveResponse

API_VERSION = "5.199"

_MIME_MAP = {
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".flv": "video/x-flv",
}


def _mime_for(path: Path) -> str:
    return _MIME_MAP.get(path.suffix.lower(), "video/mp4")


def _api_error_code(value: Any) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return -1


def _ensure_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise UploadError(f"Invalid response from {context}: expected object")
    return value


def _upload_response_int(data: dict[str, Any], key: str, context: str) -> int:
    try:
        return int(data.get(key, 0))
    except (TypeError, ValueError):
        raise UploadError(
            f"Invalid response from {context}: {key} must be an integer"
        ) from None


def _raise_vk_error(raw_error: Any) -> None:
    err = raw_error if isinstance(raw_error, dict) else {}
    raise VkApiError(
        code=_api_error_code(err.get("error_code", -1)),
        message=str(err.get("error_msg", raw_error)),
    )


class VkApiError(Exception):
    """Raised when the VK API returns an error response."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"VK API error [{code}]: {message}")


class VkClient:
    """Synchronous VK API client for video upload workflow."""

    def __init__(self, access_token: str, api_version: str = API_VERSION):
        self._token = access_token
        self._version = api_version

    def call_method(self, method: str, params: dict[str, str]) -> Any:
        """POST to api.vk.com/method/<method>. Returns parsed response. Raises VkApiError."""
        url = f"https://api.vk.com/method/{method}"
        body = {**params, "access_token": self._token, "v": self._version}

        try:
            resp = requests.post(url, data=body, timeout=60)
            resp.raise_for_status()
            raw_data: Any = resp.json()
        except requests.RequestException as e:
            raise VkApiError(code=-1, message=f"Network error calling {method}: {e}") from e
        except ValueError as e:
            raise VkApiError(code=-1, message=f"Invalid JSON from {method}: {e}") from e

        if not isinstance(raw_data, dict):
            raise VkApiError(
                code=-1,
                message=f"Invalid response from {method}: expected object",
            )

        data: dict[str, Any] = raw_data
        if "error" in data:
            _raise_vk_error(data["error"])

        if "response" not in data:
            raise VkApiError(
                code=-1,
                message=f"Invalid response from {method}: missing response",
            )

        response: Any = data["response"]
        return response

    def get_albums(self, owner_id: str, count: int = 50) -> list[dict[str, Any]]:
        """Get video albums for an owner (group or user)."""
        result = self.call_method("video.getAlbums", {
            "owner_id": owner_id,
            "count": str(count),
            "extended": "1",
        })
        if isinstance(result, dict):
            items = result.get("items", [])
            return items if isinstance(items, list) else []
        return []

    def add_album(self, group_id: str, title: str) -> int:
        """Create a new video album in a community. Returns album_id."""
        result = self.call_method("video.addAlbum", {
            "group_id": group_id,
            "title": title,
        })
        if isinstance(result, dict):
            return int(result.get("album_id", 0))
        return 0

    def users_get(self) -> list[dict[str, Any]]:
        """Verify token validity and return user info."""
        result = self.call_method("users.get", {})
        return result if isinstance(result, list) else []

    def video_save(
        self,
        name: str,
        description: str,
        group_id: str,
        publish_at: datetime,
        wallpost: bool = False,
        thumb_url: str | None = None,
        album_id: str | None = None,
    ) -> VkSaveResponse:
        """Call video.save. Returns VkSaveResponse with upload_url, video_id, owner_id."""
        params: dict[str, str] = {
            "name": name,
            "description": description,
            "group_id": group_id,
            "wallpost": "1" if wallpost else "0",
            "publish_date": str(int(publish_at.timestamp())),
        }
        if thumb_url:
            params["thumb_url"] = thumb_url
        if album_id:
            params["album_id"] = album_id

        response = self.call_method("video.save", params)
        resp_dict: dict[str, Any] = response if isinstance(response, dict) else {}

        upload_url = resp_dict.get("upload_url", "")
        if not upload_url:
            raise VkApiError(code=-1, message="video.save did not return upload_url")

        return VkSaveResponse(
            upload_url=str(upload_url),
            video_id=int(resp_dict.get("video_id", 0)),
            owner_id=int(resp_dict.get("owner_id", 0)),
        )

    def upload_video_file(
        self,
        upload_url: str,
        file_path: Path,
        on_progress: Callable[[float], None] | None = None,
    ) -> UploadResult:
        """Multipart POST video file to the upload URL. Returns UploadResult.

        If on_progress is given, it is called with a float 0–100 as the
        upload proceeds.
        """
        file_size = file_path.stat().st_size
        mime = _mime_for(file_path)

        with open(file_path, "rb") as f:
            encoder = MultipartEncoder(
                fields={"video_file": (file_path.name, f, mime)},
            )

            try:
                if on_progress and file_size > 0:

                    def _callback(monitor: MultipartEncoderMonitor) -> None:
                        pct = (monitor.bytes_read / monitor.len) * 100
                        on_progress(pct)

                    monitor = MultipartEncoderMonitor(encoder, _callback)
                    resp = requests.post(
                        upload_url,
                        data=monitor,
                        headers={"Content-Type": monitor.content_type},
                        timeout=600,
                    )
                else:
                    resp = requests.post(
                        upload_url,
                        data=encoder,
                        headers={"Content-Type": encoder.content_type},
                        timeout=600,
                    )
                resp.raise_for_status()
                raw_data: Any = resp.json()
            except requests.RequestException as e:
                raise UploadError(
                    f"Network error during upload: {e}. "
                    f"VK upload servers can be unstable with large files — try again."
                ) from e
            except ValueError as e:
                raise UploadError(
                    f"Invalid JSON from VK upload server: {e}"
                ) from e

        data = _ensure_object(raw_data, "VK upload server")
        if "error" in data:
            _raise_vk_error(data["error"])

        return UploadResult(
            video_id=_upload_response_int(data, "video_id", "VK upload server"),
            owner_id=_upload_response_int(data, "owner_id", "VK upload server"),
            raw_response=data,
        )

    def upload_video_thumbnail(
        self, video_id: int, owner_id: int, thumbnail_path: Path
    ) -> dict[str, Any]:
        """Upload a custom thumbnail for a video.

        Uses the VK API flow:
        1. video.getThumbUploadUrl → obtain an upload URL.
        2. POST the image file to that URL.
        3. video.saveUploadedThumb → apply the uploaded thumbnail.
        """
        # 1. Get thumbnail upload URL.
        thumb_url_resp = self.call_method(
            "video.getThumbUploadUrl",
            {"owner_id": str(owner_id)},
        )
        thumb_url_dict: dict[str, Any] = (
            thumb_url_resp if isinstance(thumb_url_resp, dict) else {}
        )
        upload_url = thumb_url_dict.get("upload_url", "")
        if not upload_url:
            raise VkApiError(
                code=-1,
                message="video.getThumbUploadUrl did not return upload_url",
            )

        # 2. Upload the image.
        with open(thumbnail_path, "rb") as f:
            try:
                upload_resp = requests.post(
                    upload_url,
                    files={"file": (thumbnail_path.name, f, "image/jpeg")},
                    timeout=60,
                )
                upload_resp.raise_for_status()
                raw_upload_data: Any = upload_resp.json()
            except requests.RequestException as e:
                raise UploadError(
                    f"Network error uploading thumbnail: {e}"
                ) from e
            except ValueError as e:
                raise UploadError(
                    f"Invalid JSON from thumbnail upload: {e}"
                ) from e

        upload_data = _ensure_object(raw_upload_data, "thumbnail upload")
        if "error" in upload_data:
            _raise_vk_error(upload_data["error"])

        # 3. Apply the uploaded thumbnail to the video.
        result = self.call_method(
            "video.saveUploadedThumb",
            {
                "owner_id": str(owner_id),
                "video_id": str(video_id),
                "thumb_json": upload_resp.text,
                "set_thumb": "1",
            },
        )
        return _ensure_object(result, "video.saveUploadedThumb")


def resolve_album(
    vk: VkClient,
    group_id: str,
    album_spec: str,
    console: Console,
) -> tuple[str | None, str]:
    """Resolve an album spec to an album_id and status label.

    Two modes:
    - ``album_spec == "true"``: interactive — list albums, pick or create new.
    - otherwise: find album by name (case-insensitive), create if not found.

    Returns ``(album_id, status_label)`` where *album_id* is ``None`` on
    failure/cancel and *status_label* is a short description for the summary.
    """
    owner_id = f"-{group_id}"

    # Fetch existing albums.
    try:
        albums = vk.get_albums(owner_id)
    except VkApiError as e:
        console.print(f"[yellow]Failed to fetch albums: {e}[/yellow]")
        return None, "[red]✗ (album fetch failed)[/red]"

    if album_spec.lower() == "true":
        # ── Interactive mode ──
        if albums:
            console.print("\n[bold]Albums in community:[/bold]")
            for i, a in enumerate(albums, 1):
                title = a.get("title", "?")
                cnt = a.get("count", 0)
                console.print(f"  {i}. {title} [dim]({cnt} videos)[/dim]")
            console.print("  [n] [bold]Create new album...[/bold]")
        else:
            console.print("[dim]No albums in this community.[/dim]")
            return _create_album_interactive(vk, group_id, console)

        choice = console.input("\nEnter number (or 'n' for new): ").strip()
        if choice.lower() == "n":
            return _create_album_interactive(vk, group_id, console)

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(albums):
                album = albums[idx]
                album_id = str(album.get("id", ""))
                title = album.get("title", "?")
                return album_id, f"[green]✓ ({title})[/green]"
        except ValueError:
            pass

        console.print("[yellow]Invalid choice, skipping album.[/yellow]")
        return None, "[yellow]skipped[/yellow]"
    else:
        # ── Non-interactive: find by name or create ──
        target = album_spec.strip().lower()
        for a in albums:
            if a.get("title", "").lower() == target:
                album_id = str(a.get("id", ""))
                return album_id, f"[green]✓ ({a.get('title','?')})[/green]"

        # Not found — create new.
        try:
            new_id = vk.add_album(group_id, album_spec.strip())
            if new_id:
                return str(new_id), f"[green]✓ ({album_spec.strip()})[/green]"
        except VkApiError as e:
            console.print(f"[yellow]Failed to create album: {e}[/yellow]")
            return None, "[red]✗ (create failed)[/red]"

        return None, "[yellow]skipped[/yellow]"


def _create_album_interactive(
    vk: VkClient,
    group_id: str,
    console: Console,
) -> tuple[str | None, str]:
    """Prompt for album title and create it. Returns (album_id, status)."""
    title = console.input("New album title: ").strip()
    if not title:
        console.print("[yellow]No title — skipping album.[/yellow]")
        return None, "[yellow]skipped[/yellow]"

    try:
        new_id = vk.add_album(group_id, title)
        if new_id:
            return str(new_id), f"[green]✓ ({title})[/green]"
    except VkApiError as e:
        console.print(f"[yellow]Failed to create album: {e}[/yellow]")

    return None, "[red]✗ (create failed)[/red]"
