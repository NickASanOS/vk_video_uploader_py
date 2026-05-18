"""Tests for config.py."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
import yaml

from vk_uploader.config import CONFIG_FILENAME, ConfigFile
from vk_uploader.models import AppConfig, ConfigError, DownloadConfig, VkConfig


def test_load_returns_defaults_when_file_missing(tmp_path: Path):
    cfg = ConfigFile(config_dir=str(tmp_path), filename=CONFIG_FILENAME)
    assert not cfg.path.exists()
    config = cfg.load()
    assert config == AppConfig()


def test_load_returns_defaults_when_file_empty(tmp_path: Path):
    p = tmp_path / CONFIG_FILENAME
    p.write_text("")
    cfg = ConfigFile(config_dir=str(tmp_path), filename=CONFIG_FILENAME)
    config = cfg.load()
    assert config == AppConfig()


def test_load_full_config(tmp_path: Path):
    p = tmp_path / CONFIG_FILENAME
    p.write_text(
        yaml.safe_dump({
            "vk": {
                "access_token": "abc123",
                "group_id": "999",
                "app_id": "888",
                "expires_at": "2026-12-31T00:00:00",
                "user_id": "42",
            },
            "defaults": {
                "publish_delay_hours": 48,
                "thumbnail": False,
                "wallpost": True,
            },
            "download": {
                "output_dir": "/custom/path",
                "video_format": "best",
            },
        })
    )

    cfg = ConfigFile(config_dir=str(tmp_path), filename=CONFIG_FILENAME)
    config = cfg.load()

    assert config.vk.access_token == "abc123"
    assert config.vk.group_id == "999"
    assert config.vk.app_id == "888"
    assert config.vk.expires_at == "2026-12-31T00:00:00"
    assert config.vk.user_id == "42"
    assert config.defaults.publish_delay_hours == 48
    assert config.defaults.thumbnail is False
    assert config.defaults.wallpost is True
    assert config.download.output_dir == "/custom/path"
    assert config.download.video_format == "best"


def test_load_partial_config_fills_defaults(tmp_path: Path):
    p = tmp_path / CONFIG_FILENAME
    p.write_text(yaml.safe_dump({"vk": {"access_token": "tok"}}))

    cfg = ConfigFile(config_dir=str(tmp_path), filename=CONFIG_FILENAME)
    config = cfg.load()

    assert config.vk.access_token == "tok"
    assert config.vk.group_id == ""  # default
    assert config.defaults.publish_delay_hours == 24  # default
    assert config.defaults.thumbnail is True  # default
    assert config.download.output_dir == "~/Downloads"  # default


def test_load_malformed_yaml_raises_config_error(tmp_path: Path):
    p = tmp_path / CONFIG_FILENAME
    p.write_text("{{bad: yaml")

    cfg = ConfigFile(config_dir=str(tmp_path), filename=CONFIG_FILENAME)
    try:
        cfg.load()
        pytest.fail("Should have raised ConfigError")
    except ConfigError:
        pass


def test_load_top_level_not_mapping_raises_config_error(tmp_path: Path):
    p = tmp_path / CONFIG_FILENAME
    p.write_text(yaml.safe_dump([1, 2, 3]))

    cfg = ConfigFile(config_dir=str(tmp_path), filename=CONFIG_FILENAME)
    try:
        cfg.load()
        pytest.fail("Should have raised ConfigError")
    except ConfigError:
        pass


def test_save_creates_dirs_and_file(tmp_path: Path):
    config = AppConfig(
        vk=VkConfig(access_token="savetest", group_id="1", app_id="2"),
    )
    cfg = ConfigFile(config_dir=str(tmp_path / ".config" / "vk_uploader"), filename=CONFIG_FILENAME)
    cfg.save(config)

    assert cfg.path.exists()
    loaded = cfg.load()
    assert loaded.vk.access_token == "savetest"
    assert loaded.vk.group_id == "1"


def test_save_sets_restrictive_permissions(tmp_path: Path):
    config = AppConfig()
    cfg = ConfigFile(config_dir=str(tmp_path), filename=CONFIG_FILENAME)
    cfg.save(config)

    mode = cfg.path.stat().st_mode
    expected = stat.S_IRUSR | stat.S_IWUSR
    assert stat.S_IMODE(mode) == expected


def test_round_trip_preserves_all_fields(tmp_path: Path, sample_config: AppConfig):
    cfg = ConfigFile(config_dir=str(tmp_path), filename=CONFIG_FILENAME)
    cfg.save(sample_config)
    loaded = cfg.load()

    assert loaded.vk == sample_config.vk
    assert loaded.defaults == sample_config.defaults
    assert loaded.download == sample_config.download


def test_resolve_output_dir_expands_tilde():
    cfg = ConfigFile(config_dir="/tmp/test")
    config = AppConfig(download=DownloadConfig(output_dir="~/Downloads"))
    result = cfg.resolve_output_dir(config)
    assert result == Path.home() / "Downloads"


def test_save_omits_empty_optional_fields(tmp_path: Path):
    config = AppConfig(
        vk=VkConfig(access_token="tok"),
    )
    cfg = ConfigFile(config_dir=str(tmp_path), filename=CONFIG_FILENAME)
    cfg.save(config)

    raw = yaml.safe_load(cfg.path.read_text())
    assert "expires_at" not in raw["vk"]
    assert "user_id" not in raw["vk"]


def test_load_translation_defaults(tmp_path: Path):
    p = tmp_path / CONFIG_FILENAME
    p.write_text(yaml.safe_dump({"defaults": {"translation": True, "lang": "de"}}))

    cfg = ConfigFile(config_dir=str(tmp_path), filename=CONFIG_FILENAME)
    config = cfg.load()
    assert config.defaults.translation is True
    assert config.defaults.lang == "de"


def test_translation_defaults_when_missing(tmp_path: Path):
    p = tmp_path / CONFIG_FILENAME
    p.write_text(yaml.safe_dump({"defaults": {}}))

    cfg = ConfigFile(config_dir=str(tmp_path), filename=CONFIG_FILENAME)
    config = cfg.load()
    assert config.defaults.translation is False
    assert config.defaults.lang == "ru"


def test_yaml_null_becomes_empty_string(tmp_path: Path):
    p = tmp_path / CONFIG_FILENAME
    p.write_text(yaml.safe_dump({"vk": {"access_token": None, "group_id": None, "app_id": None}}))

    cfg = ConfigFile(config_dir=str(tmp_path), filename=CONFIG_FILENAME)
    config = cfg.load()
    assert config.vk.access_token == ""
    assert config.vk.group_id == ""
    assert config.vk.app_id == ""
