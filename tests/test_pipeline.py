"""Tests for pipeline helper behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from vk_uploader.models import (
    AppConfig,
    DefaultsConfig,
    DownloadResult,
    JobContext,
    UploadResult,
)
from vk_uploader.pipeline import (
    _cleanup_downloaded_files,
    _matching_srt_files,
    _stage_thumbnail_upload,
    _stage_translate_metadata,
)


def test_matching_srt_files_excludes_similar_prefixes(tmp_path: Path):
    video = tmp_path / "abc.mp4"
    video.write_text("video")
    own_plain = tmp_path / "abc.srt"
    own_lang = tmp_path / "abc.en.srt"
    other = tmp_path / "abcd.srt"
    own_plain.write_text("plain")
    own_lang.write_text("lang")
    other.write_text("other")

    assert set(_matching_srt_files(video)) == {own_lang, own_plain}


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


def test_stage_translate_metadata_warns_when_translation_fails(mocker, tmp_path: Path):
    console = mocker.MagicMock()
    ctx = JobContext(
        youtube_url="https://youtube.com/watch?v=abc123def45",
        output_dir=tmp_path,
        group_id="123",
        publish_delay_hours=24,
        thumbnail_enabled=True,
        wallpost=False,
    )
    config = AppConfig(defaults=DefaultsConfig(translation=True, lang="ru"))
    result = DownloadResult(
        file_path=tmp_path / "abc123def45.mp4",
        title="Hello",
        description="World",
        thumbnail_url=None,
        duration=0,
        uploader="",
        webpage_url=ctx.youtube_url,
        video_id="abc123def45",
    )

    def fail_translation(text: str, target_lang: str, on_error=None) -> str:
        if on_error is not None:
            on_error(RuntimeError("network down"))
        return text

    mocker.patch("vk_uploader.translate.translate_text", side_effect=fail_translation)

    title, description = _stage_translate_metadata(console, ctx, config, result)

    assert title == "Hello"
    assert description == "World"
    warning_calls = [
        call for call in console.print.call_args_list
        if "Translation failed" in str(call)
    ]
    assert len(warning_calls) == 1


def test_stage_thumbnail_upload_does_not_hide_programming_errors(mocker, tmp_path: Path):
    console = mocker.MagicMock()
    vk = mocker.MagicMock()
    ctx = JobContext(
        youtube_url="https://youtube.com/watch?v=abc123def45",
        output_dir=tmp_path,
        group_id="123",
        publish_delay_hours=24,
        thumbnail_enabled=True,
        wallpost=False,
    )
    result = DownloadResult(
        file_path=tmp_path / "abc123def45.mp4",
        title="Hello",
        description="World",
        thumbnail_url="https://i.ytimg.com/thumb.jpg",
        duration=0,
        uploader="",
        webpage_url=ctx.youtube_url,
        video_id="abc123def45",
    )
    upload_result = UploadResult(video_id=1, owner_id=-1, raw_response={})

    mocker.patch(
        "vk_uploader.thumbnail.download_thumbnail",
        side_effect=TypeError("bug"),
    )

    with pytest.raises(TypeError, match="bug"):
        _stage_thumbnail_upload(
            console, vk, ctx, result, upload_result, result.thumbnail_url
        )
