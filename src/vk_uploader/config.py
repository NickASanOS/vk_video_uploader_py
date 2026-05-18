"""Config file management: load/save ~/.config/vk_uploader/config.yaml."""

from __future__ import annotations

import contextlib
import os
import stat
from pathlib import Path
from typing import Any

import yaml

from vk_uploader.models import AppConfig, ConfigError, DefaultsConfig, DownloadConfig, VkConfig

CONFIG_DIR = "~/.config/vk_uploader"
CONFIG_FILENAME = "config.yaml"


class ConfigFile:
    """Loads and saves config from ~/.config/vk_uploader/config.yaml."""

    def __init__(self, config_dir: str = CONFIG_DIR, filename: str = CONFIG_FILENAME):
        self._dir = Path(config_dir).expanduser()
        self._path = self._dir / filename

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> AppConfig:
        """Load config from YAML. Returns defaults if file does not exist."""
        if not self._path.exists():
            return AppConfig()

        try:
            data = yaml.safe_load(Path(self._path).read_text())
        except yaml.YAMLError as e:
            raise ConfigError(f"Failed to parse config file: {self._path}\n{e}") from e

        if data is None:
            return AppConfig()

        if not isinstance(data, dict):
            raise ConfigError(f"Config must be a YAML mapping, got: {type(data).__name__}")

        return self._dict_to_config(data)

    def save(self, config: AppConfig) -> None:
        """Save config to YAML. Creates parent directories if needed."""
        self._dir.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "vk": {
                "access_token": config.vk.access_token,
                "group_id": config.vk.group_id,
                "app_id": config.vk.app_id,
            },
            "defaults": {
                "publish_delay_hours": config.defaults.publish_delay_hours,
                "thumbnail": config.defaults.thumbnail,
                "wallpost": config.defaults.wallpost,
                "translation": config.defaults.translation,
                "lang": config.defaults.lang,
            },
            "download": {
                "output_dir": config.download.output_dir,
                "video_format": config.download.video_format,
            },
        }
        # Only write optional fields if they have values.
        if config.vk.expires_at:
            data["vk"]["expires_at"] = config.vk.expires_at
        if config.vk.user_id:
            data["vk"]["user_id"] = config.vk.user_id

        Path(self._path).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))

        # Restrict permissions: config contains a token.
        with contextlib.suppress(OSError):
            os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)

    def resolve_output_dir(self, config: AppConfig) -> Path:
        """Expand ~ in output_dir and return as Path."""
        return Path(config.download.output_dir).expanduser()

    def _dict_to_config(self, data: dict[str, Any]) -> AppConfig:
        vk_data = data.get("vk", {})
        defaults_data = data.get("defaults", {})
        download_data = data.get("download", {})

        vk = VkConfig(
            access_token=str(vk_data.get("access_token") or ""),
            group_id=str(vk_data.get("group_id") or ""),
            app_id=str(vk_data.get("app_id") or ""),
            expires_at=vk_data.get("expires_at"),
            user_id=vk_data.get("user_id"),
        )
        defaults = DefaultsConfig(
            publish_delay_hours=int(defaults_data.get("publish_delay_hours", 24)),
            thumbnail=bool(defaults_data.get("thumbnail", True)),
            wallpost=bool(defaults_data.get("wallpost", False)),
            translation=bool(defaults_data.get("translation", False)),
            lang=str(defaults_data.get("lang", "ru")),
        )
        download = DownloadConfig(
            output_dir=str(download_data.get("output_dir", "~/Downloads")),
            video_format=str(download_data.get("video_format", "bv*+ba/b")),
        )
        return AppConfig(vk=vk, defaults=defaults, download=download)
