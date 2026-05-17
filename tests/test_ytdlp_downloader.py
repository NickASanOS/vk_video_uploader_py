"""Tests for ytdlp_downloader.py."""

from __future__ import annotations

from pathlib import Path

from vk_uploader.models import DownloadResult
from vk_uploader.ytdlp_downloader import YtDlpDownloader


def test_download_returns_download_result(mocker):
    info = {
        "title": "Test Video",
        "description": "A test description",
        "thumbnail": "https://i.ytimg.com/thumb.jpg",
        "duration": 120,
        "uploader": "Test Channel",
        "webpage_url": "https://www.youtube.com/watch?v=test",
    }

    output_dir = Path("/tmp/vk-test")

    mock_ydl = mocker.patch("vk_uploader.ytdlp_downloader.YoutubeDL")
    mock_ydl_instance = mock_ydl.return_value.__enter__.return_value
    mock_ydl_instance.extract_info.return_value = info
    mock_ydl_instance.prepare_filename.return_value = str(output_dir / "Test Video.mp4")

    # Create the expected output file.
    output_dir.mkdir(parents=True, exist_ok=True)
    expected_file = output_dir / "Test Video.mp4"
    expected_file.write_text("fake video content")

    downloader = YtDlpDownloader(output_dir=output_dir)
    result = downloader.download("https://www.youtube.com/watch?v=test")

    assert isinstance(result, DownloadResult)
    assert result.title == "Test Video"
    assert result.description == "A test description"
    assert result.thumbnail_url == "https://i.ytimg.com/thumb.jpg"
    assert result.duration == 120
    assert result.uploader == "Test Channel"

    # Clean up
    expected_file.unlink()


def test_download_passes_options_to_ytdlp(mocker):
    mocker.patch("vk_uploader.ytdlp_downloader.YoutubeDL")
    mock_ydl = mocker.patch("vk_uploader.ytdlp_downloader.YoutubeDL")
    mock_ydl_instance = mock_ydl.return_value.__enter__.return_value
    mock_ydl_instance.extract_info.return_value = {
        "title": "X",
        "description": "",
        "thumbnail": None,
        "duration": 0,
        "uploader": "",
        "webpage_url": "url",
    }
    mock_ydl_instance.prepare_filename.return_value = "/tmp/files/X.mp4"
    (Path("/tmp/files")).mkdir(parents=True, exist_ok=True)
    Path("/tmp/files/X.mp4").write_text("data")

    output_dir = Path("/tmp/files")
    downloader = YtDlpDownloader(output_dir=output_dir, video_format="best")
    downloader.download("https://example.com/v")

    call_args = mock_ydl.call_args[1] if mock_ydl.call_args[1] else {}
    assert call_args.get("params") is None  # passed as kwargs to YoutubeDL constructor
    # Actually, check the options passed.
    assert len(mock_ydl.call_args_list) > 0
    # The first call to YoutubeDL(...) has the options dict.
    ydl_opts = mock_ydl.call_args[0][0] if mock_ydl.call_args[0] else {}
    assert ydl_opts.get("format") == "best"
    assert "outtmpl" in ydl_opts
