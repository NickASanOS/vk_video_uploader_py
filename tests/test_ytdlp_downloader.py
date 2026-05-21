"""Tests for ytdlp_downloader.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vk_uploader.ytdlp_downloader import YtDlpDownloader, _find_ytdlp


def test_find_ytdlp_finds_path_binary(mocker):
    mocker.patch("vk_uploader.ytdlp_downloader.Path.exists", return_value=False)
    mocker.patch("vk_uploader.ytdlp_downloader.shutil.which", return_value="/usr/bin/yt-dlp")

    path = _find_ytdlp()

    assert path == "/usr/bin/yt-dlp"


class TestYtDlpDownloader:
    @pytest.fixture(autouse=True)
    def mock_ytdlp_binary(self, mocker):
        mocker.patch("vk_uploader.ytdlp_downloader._find_ytdlp", return_value="yt-dlp")

    def test_download_returns_result(self, mocker, tmp_path: Path):
        info = {
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
        out_file = tmp_path / "Test Video.mp4"
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
        info = {"title": "V", "description": "", "duration": 0, "uploader": ""}
        mocker.patch.object(YtDlpDownloader, "_extract_info", return_value=info)

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = mocker.MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.wait.return_value = 0

        def create_file(*args, **kwargs):
            (tmp_path / "V.mp4").write_text("fake")
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
        assert "ru" in args[idx + 1]
        assert "en" in args[idx + 1]

    def test_subtitles_args_absent_when_lang_none(self, mocker, tmp_path: Path):
        info = {"title": "V", "description": "", "duration": 0, "uploader": ""}
        mocker.patch.object(YtDlpDownloader, "_extract_info", return_value=info)

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = mocker.MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.wait.return_value = 0

        def create_file(*args, **kwargs):
            (tmp_path / "V.mp4").write_text("fake")
            return mock_proc
        mock_popen.side_effect = create_file

        downloader = YtDlpDownloader(output_dir=tmp_path, subtitles_lang=None)
        downloader.download("https://example.com/v")

        args = mock_popen.call_args[0][0]
        assert "--write-subs" not in args
        assert "--write-auto-subs" not in args
