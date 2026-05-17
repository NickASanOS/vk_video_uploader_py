"""VK API client: HTTP wrapper for video upload workflow."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, cast

import requests

from vk_uploader.models import UploadResult, VkSaveResponse

API_VERSION = "5.199"


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

        resp = requests.post(url, data=body, timeout=60)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        if "error" in data:
            err = data["error"]
            raise VkApiError(
                code=err.get("error_code", -1),
                message=err.get("error_msg", str(err)),
            )

        response: Any = data["response"]
        return response

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

    def upload_video_file(self, upload_url: str, file_path: Path) -> UploadResult:
        """Multipart POST video file to the upload URL. Returns UploadResult."""
        with open(file_path, "rb") as f:
            resp = requests.post(
                upload_url,
                files={"video_file": (file_path.name, f, "video/mp4")},
                timeout=600,
            )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        if "error" in data:
            err = data["error"]
            raise VkApiError(
                code=err.get("error_code", -1),
                message=err.get("error_msg", str(err)),
            )

        return UploadResult(
            video_id=int(data.get("video_id", 0)),
            owner_id=int(data.get("owner_id", 0)),
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
            upload_resp = requests.post(
                upload_url,
                files={"file": (thumbnail_path.name, f, "image/jpeg")},
                timeout=60,
            )
        upload_resp.raise_for_status()
        upload_data: dict[str, Any] = upload_resp.json()

        if "error" in upload_data:
            err = upload_data["error"]
            raise VkApiError(
                code=err.get("error_code", -1),
                message=err.get("error_msg", str(err)),
            )

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
        return cast(dict[str, Any], result)
