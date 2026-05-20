"""Data classes and enums used across the application."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path


class PipelineStage(Enum):
    IDLE = auto()
    DOWNLOADING = auto()
    DOWNLOAD_COMPLETED = auto()
    UPLOADING_TO_VK = auto()
    UPLOADING_THUMBNAIL = auto()
    COMPLETED = auto()
    ERROR = auto()

    @property
    def label(self) -> str:
        labels = {
            self.IDLE: "Idle",
            self.DOWNLOADING: "Downloading",
            self.DOWNLOAD_COMPLETED: "Download completed",
            self.UPLOADING_TO_VK: "Uploading to VK",
            self.UPLOADING_THUMBNAIL: "Uploading thumbnail",
            self.COMPLETED: "Completed",
            self.ERROR: "Error",
        }
        return labels[self]


@dataclass
class DownloadResult:
    """Result of a yt-dlp download operation."""

    file_path: Path
    title: str
    description: str
    thumbnail_url: str | None
    duration: int
    uploader: str
    webpage_url: str


@dataclass
class VkSaveResponse:
    """Response from VK video.save."""

    upload_url: str
    video_id: int
    owner_id: int


@dataclass
class UploadResult:
    """Result of uploading a video file to VK."""

    video_id: int
    owner_id: int
    raw_response: dict[str, object]


@dataclass
class JobContext:
    """All state carried through a single pipeline run."""

    youtube_url: str
    output_dir: Path
    group_id: str
    publish_delay_hours: int
    thumbnail_enabled: bool
    wallpost: bool
    title_override: str | None = None
    description_override: str | None = None
    # Filled in during pipeline execution:
    download_result: DownloadResult | None = None
    vk_save_response: VkSaveResponse | None = None
    upload_result: UploadResult | None = None
    stage: PipelineStage = PipelineStage.IDLE
    error_message: str | None = None


@dataclass
class VkConfig:
    """VK-specific config section."""

    access_token: str = ""
    group_id: str = ""
    app_id: str = ""
    expires_at: str | None = None
    user_id: str | None = None


@dataclass
class DefaultsConfig:
    """Default behaviour config section."""

    publish_delay_hours: int = 24
    thumbnail: bool = True
    wallpost: bool = False
    translation: bool = False
    subtitles: bool = False
    lang: str = "ru"
    cookies_from_browser: str = ""


@dataclass
class DownloadConfig:
    """Download behaviour config section."""

    output_dir: str = "~/Downloads"
    video_format: str = "bv*+ba[ext=m4a]/bv*+ba/b"


@dataclass
class AppConfig:
    """Top-level config object matching config.yaml structure."""

    vk: VkConfig = field(default_factory=VkConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    download: DownloadConfig = field(default_factory=DownloadConfig)


# --- Custom exceptions ---


class VkUploaderError(Exception):
    """Base exception for all vk_uploader errors."""
    pass


class UsageError(VkUploaderError):
    """Invalid command-line usage."""
    pass


class ConfigError(VkUploaderError):
    """Configuration-related error."""
    pass


class AuthError(VkUploaderError):
    """OAuth flow error."""
    pass


class AuthTimeoutError(AuthError):
    """OAuth flow timed out waiting for user."""
    pass


class DownloadError(VkUploaderError):
    """yt-dlp download failure."""
    pass


class BotDetectionError(DownloadError):
    """YouTube bot-detection — needs browser cookies."""
    pass


class UploadError(VkUploaderError):
    """VK upload failure."""
    pass
