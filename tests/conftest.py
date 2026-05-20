"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from vk_uploader.models import AppConfig, DefaultsConfig, DownloadConfig, JobContext, VkConfig


@pytest.fixture
def sample_config() -> AppConfig:
    return AppConfig(
        vk=VkConfig(
            access_token="test-token",
            group_id="12345",
            app_id="67890",
            expires_at="2026-12-31T00:00:00",
            user_id="111",
        ),
        defaults=DefaultsConfig(
            publish_delay_hours=24,
            thumbnail=True,
            wallpost=False,
            subtitles=False,
        ),
        download=DownloadConfig(
            output_dir="~/Downloads",
            video_format="bv*+ba/b",
        ),
    )


@pytest.fixture
def job_context() -> JobContext:
    return JobContext(
        youtube_url="https://www.youtube.com/watch?v=test123",
        output_dir=Path("/tmp/vk-test"),
        group_id="12345",
        publish_delay_hours=24,
        thumbnail_enabled=True,
        wallpost=False,
    )
