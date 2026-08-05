"""Tests for ytdlp_downloader.py."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from vk_uploader.models import BotDetectionError
from vk_uploader.ytdlp_downloader import YtDlpDownloader, _build_env, _find_ytdlp


def test_find_ytdlp_finds_path_binary(mocker):
    mocker.patch("vk_uploader.ytdlp_downloader.Path.exists", return_value=False)
    mocker.patch("vk_uploader.ytdlp_downloader.shutil.which", return_value="/usr/bin/yt-dlp")

    path = _find_ytdlp()

    assert path == "/usr/bin/yt-dlp"


def test_build_env_prepends_common_tool_paths(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")

    env = _build_env()

    assert env["PATH"].split(os.pathsep) == [
        os.path.expanduser("~/.deno/bin"),
        os.path.expanduser("~/.local/bin"),
        "/usr/bin",
    ]


def test_build_env_keeps_common_tool_paths_when_path_empty(monkeypatch):
    monkeypatch.setenv("PATH", "")

    env = _build_env()

    assert env["PATH"].split(os.pathsep) == [
        os.path.expanduser("~/.deno/bin"),
        os.path.expanduser("~/.local/bin"),
    ]


def test_build_env_keeps_common_tool_paths_when_path_missing(monkeypatch):
    monkeypatch.delenv("PATH", raising=False)

    env = _build_env()

    assert env["PATH"].split(os.pathsep) == [
        os.path.expanduser("~/.deno/bin"),
        os.path.expanduser("~/.local/bin"),
    ]


class TestYtDlpDownloader:
    @pytest.fixture(autouse=True)
    def mock_ytdlp_binary(self, mocker):
        mocker.patch("vk_uploader.ytdlp_downloader._find_ytdlp", return_value="yt-dlp")

    def test_download_returns_result(self, mocker, tmp_path: Path):
        info = {
            "id": "abc123def45",
            "title": "Test Video",
            "description": "A test description",
            "thumbnail": "https://i.ytimg.com/thumb.jpg",
            "duration": 120,
            "uploader": "Test Channel",
        }

        # Mock _extract_info to return canned metadata.
        mocker.patch.object(YtDlpDownloader, "_extract_info", return_value=info)

        # Mock subprocess.Popen for the download step.
        mock_proc = mocker.MagicMock()
        mock_proc.stdout = iter(["line 1", "line 2"])
        mock_proc.wait.return_value = 0
        mocker.patch("subprocess.Popen", return_value=mock_proc)

        # Create a fake output file.
        out_file = tmp_path / "abc123def45.mp4"
        out_file.write_text("fake data")

        downloader = YtDlpDownloader(output_dir=tmp_path)
        result = downloader.download("https://example.com/v")

        assert result.title == "Test Video"
        assert result.description == "A test description"
        assert result.thumbnail_url == "https://i.ytimg.com/thumb.jpg"
        assert result.file_path == out_file

    def test_download_nonzero_exit_raises(self, mocker, tmp_path: Path):
        info = {"title": "X", "description": "", "duration": 0, "uploader": ""}
        mocker.patch.object(YtDlpDownloader, "_extract_info", return_value=info)

        mock_proc = mocker.MagicMock()
        mock_proc.stdout = iter(["error: video unavailable"])
        mock_proc.wait.return_value = 1
        mocker.patch("subprocess.Popen", return_value=mock_proc)

        downloader = YtDlpDownloader(output_dir=tmp_path)
        try:
            downloader.download("https://example.com/v")
            pytest.fail("Should have raised")
        except Exception:
            pass

    def test_extract_info_parses_json(self, mocker):
        info = {"title": "Hello", "description": "World"}
        mocker.patch(
            "subprocess.run",
            return_value=mocker.MagicMock(
                returncode=0, stdout=json.dumps(info), stderr="",
            ),
        )

        downloader = YtDlpDownloader(output_dir=Path("/tmp"))
        result = downloader._extract_info("https://example.com/v")
        assert result == info

    def test_subtitles_args_present_when_lang_set(self, mocker, tmp_path: Path):
        info = {
            "id": "abc123def45",
            "title": "V",
            "description": "",
            "duration": 0,
            "uploader": "",
        }
        mocker.patch.object(YtDlpDownloader, "_extract_info", return_value=info)

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = mocker.MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.wait.return_value = 0

        def create_file(*args, **kwargs):
            (tmp_path / "abc123def45.mp4").write_text("fake")
            return mock_proc
        mock_popen.side_effect = create_file

        downloader = YtDlpDownloader(output_dir=tmp_path, subtitles_lang="ru")
        downloader.download("https://example.com/v")

        args = mock_popen.call_args[0][0]
        assert "--write-subs" in args
        assert "--write-auto-subs" in args
        assert "--sub-langs" in args
        assert "--convert-subs" in args
        idx = args.index("--sub-langs")
        assert args[idx + 1] == "ru,ru.*,en,en.*"

    def test_subtitles_args_absent_when_lang_none(self, mocker, tmp_path: Path):
        info = {
            "id": "abc123def45",
            "title": "V",
            "description": "",
            "duration": 0,
            "uploader": "",
        }
        mocker.patch.object(YtDlpDownloader, "_extract_info", return_value=info)

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = mocker.MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.wait.return_value = 0

        def create_file(*args, **kwargs):
            (tmp_path / "abc123def45.mp4").write_text("fake")
            return mock_proc
        mock_popen.side_effect = create_file

        downloader = YtDlpDownloader(output_dir=tmp_path, subtitles_lang=None)
        downloader.download("https://example.com/v")

        args = mock_popen.call_args[0][0]
        assert "--write-subs" not in args
        assert "--write-auto-subs" not in args

    def test_cached_video_still_downloads_missing_subtitles(self, mocker, tmp_path: Path):
        info = {
            "id": "abc123def45",
            "title": "V",
            "description": "",
            "duration": 0,
            "uploader": "",
        }
        mocker.patch.object(YtDlpDownloader, "_extract_info", return_value=info)
        cached = tmp_path / "abc123def45.mp4"
        cached.write_text("fake")

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = mocker.MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        downloader = YtDlpDownloader(output_dir=tmp_path, subtitles_lang="ru")
        result = downloader.download("https://youtube.com/watch?v=abc123def45")

        assert result.file_path == cached
        mock_popen.assert_called_once()

    def test_cached_video_with_non_default_extension_is_reused(
        self, mocker, tmp_path: Path
    ):
        info = {
            "id": "abc123def45",
            "title": "V",
            "description": "",
            "duration": 0,
            "uploader": "",
        }
        mocker.patch.object(YtDlpDownloader, "_extract_info", return_value=info)
        cached = tmp_path / "abc123def45.mov"
        cached.write_text("fake")
        mock_popen = mocker.patch("subprocess.Popen")

        downloader = YtDlpDownloader(output_dir=tmp_path)
        result = downloader.download("https://youtube.com/watch?v=abc123def45")

        assert result.file_path == cached
        mock_popen.assert_not_called()

    def test_download_fallback_finds_non_default_extension(
        self, mocker, tmp_path: Path
    ):
        info = {
            "id": "abc123def45",
            "title": "V",
            "description": "",
            "duration": 0,
            "uploader": "",
        }
        mocker.patch.object(YtDlpDownloader, "_extract_info", return_value=info)

        mock_proc = mocker.MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.wait.return_value = 0

        def create_file(*args, **kwargs):
            (tmp_path / "abc123def45.mov").write_text("fake")
            return mock_proc

        mocker.patch("subprocess.Popen", side_effect=create_file)

        downloader = YtDlpDownloader(output_dir=tmp_path)
        result = downloader.download("https://youtube.com/watch?v=abc123def45")

        assert result.file_path == tmp_path / "abc123def45.mov"

    def test_nonzero_exit_continues_when_non_default_output_exists(
        self, mocker, tmp_path: Path
    ):
        info = {
            "id": "abc123def45",
            "title": "V",
            "description": "",
            "duration": 0,
            "uploader": "",
        }
        mocker.patch.object(YtDlpDownloader, "_extract_info", return_value=info)

        mock_proc = mocker.MagicMock()
        mock_proc.stdout = iter(["warning"])
        mock_proc.wait.return_value = 1

        def create_file(*args, **kwargs):
            (tmp_path / "abc123def45.mov").write_text("fake")
            return mock_proc

        mocker.patch("subprocess.Popen", side_effect=create_file)

        downloader = YtDlpDownloader(output_dir=tmp_path)
        result = downloader.download("https://youtube.com/watch?v=abc123def45")

        assert result.file_path == tmp_path / "abc123def45.mov"

    def test_download_bot_detection_raises_specific_error(self, mocker, tmp_path: Path):
        info = {
            "id": "abc123def45",
            "title": "V",
            "description": "",
            "duration": 0,
            "uploader": "",
        }
        mocker.patch.object(YtDlpDownloader, "_extract_info", return_value=info)

        mock_proc = mocker.MagicMock()
        mock_proc.stdout = iter(["ERROR: Sign in to confirm you're not a bot"])
        mock_proc.wait.return_value = 1
        mocker.patch("subprocess.Popen", return_value=mock_proc)

        downloader = YtDlpDownloader(output_dir=tmp_path)
        with pytest.raises(BotDetectionError):
            downloader.download("https://youtube.com/watch?v=abc123def45")
