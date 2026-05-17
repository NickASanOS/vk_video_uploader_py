"""Tests for thumbnail.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from vk_uploader.thumbnail import download_thumbnail


def test_download_thumbnail_saves_file(mocker, tmp_path: Path):
    fake_image = b"\xff\xd8\xff\xe0fake jpeg"
    mock_resp = mocker.MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.iter_content.return_value = [fake_image]
    mocker.patch("vk_uploader.thumbnail.requests.get", return_value=mock_resp)

    result = download_thumbnail("https://i.ytimg.com/thumb.jpg", tmp_path)

    assert result.exists()
    assert result.suffix == ".jpg"
    assert result.read_bytes() == fake_image


def test_download_thumbnail_http_error(mocker, tmp_path: Path):
    import requests as req
    mocker.patch(
        "vk_uploader.thumbnail.requests.get",
        side_effect=req.ConnectionError("timeout"),
    )
    with pytest.raises(Exception):  # noqa: B017
        download_thumbnail("https://i.ytimg.com/thumb.jpg", tmp_path)
