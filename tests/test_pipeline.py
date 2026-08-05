"""Tests for pipeline helper behavior."""

from __future__ import annotations

from pathlib import Path

from vk_uploader.pipeline import _cleanup_downloaded_files, _matching_srt_files


def test_matching_srt_files_excludes_similar_prefixes(tmp_path: Path):
    video = tmp_path / "abc.mp4"
    video.write_text("video")
    own_plain = tmp_path / "abc.srt"
    own_lang = tmp_path / "abc.en.srt"
    other = tmp_path / "abcd.srt"
    own_plain.write_text("plain")
    own_lang.write_text("lang")
    other.write_text("other")

    assert _matching_srt_files(video) == [own_lang, own_plain]


def test_cleanup_removes_only_matching_sidecars(mocker, tmp_path: Path):
    video = tmp_path / "abc.mp4"
    own_srt = tmp_path / "abc.en.srt"
    other_srt = tmp_path / "abcd.srt"
    video.write_text("video")
    own_srt.write_text("sub")
    other_srt.write_text("other")
    console = mocker.MagicMock()

    _cleanup_downloaded_files(console, video)

    assert not video.exists()
    assert not own_srt.exists()
    assert other_srt.exists()
