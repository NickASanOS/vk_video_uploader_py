"""Thumbnail helpers: download from YouTube URL, prepare for VK upload."""

from __future__ import annotations

import hashlib
from pathlib import Path

import requests

from vk_uploader.models import UploadError


def download_thumbnail(thumbnail_url: str, output_dir: Path) -> Path:
    """Download a thumbnail image from a URL to a local file in output_dir.

    Returns the path to the downloaded file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    url_hash = hashlib.md5(thumbnail_url.encode()).hexdigest()[:8]
    output_path = output_dir / f"thumbnail_{url_hash}.jpg"

    try:
        resp = requests.get(thumbnail_url, stream=True, timeout=30)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
    except requests.RequestException as e:
        raise UploadError(f"Failed to download thumbnail: {e}") from e

    return output_path
