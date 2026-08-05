"""Tests for cli.py argument parsing."""

from __future__ import annotations

import sys
from unittest import mock

import pytest

from vk_uploader.cli import cmd_setup, main, parse_args
from vk_uploader.models import UsageError, parse_bool


class TestParseArgs:
    def test_positional_url_only(self):
        url, overrides = parse_args(["https://youtube.com/watch?v=abc"])
        assert url == "https://youtube.com/watch?v=abc"
        assert overrides == {}

    def test_ylink_key(self):
        url, overrides = parse_args(["ylink=https://youtube.com/watch?v=abc"])
        assert url == "https://youtube.com/watch?v=abc"
        assert overrides == {}

    def test_mixed_overrides(self):
        url, overrides = parse_args([
            "https://youtube.com/watch?v=abc",
            "thumbnail=false",
            "publish_delay_hours=72",
            "subtitles=true",
        ])
        assert url == "https://youtube.com/watch?v=abc"
        assert overrides == {
            "thumbnail": "false", "publish_delay_hours": "72", "subtitles": "true",
        }

    def test_album_override(self):
        url, overrides = parse_args([
            "https://youtube.com/watch?v=abc",
            "album=true",
        ])
        assert overrides == {"album": "true"}

    def test_album_override_name(self):
        url, overrides = parse_args([
            "https://youtube.com/watch?v=abc",
            "album=My Favorites",
        ])
        assert overrides == {"album": "My Favorites"}

    def test_only_overrides_raises_usage_error(self):
        with pytest.raises(UsageError, match="YouTube URL is required"):
            parse_args(["thumbnail=false"])

    def test_unknown_key_raises_usage_error(self):
        with pytest.raises(UsageError, match="Unknown option"):
            parse_args(["https://youtube.com/watch?v=abc", "foo=bar"])

    def test_empty_key_raises_usage_error(self):
        with pytest.raises(UsageError, match="Invalid argument"):
            parse_args(["=value"])

    def test_duplicate_url_positional_raises(self):
        with pytest.raises(UsageError, match="Only one YouTube URL"):
            parse_args(["https://a.com", "https://b.com"])

    def test_duplicate_url_ylink_raises(self):
        with pytest.raises(UsageError, match="URL specified both"):
            parse_args(["https://a.com", "ylink=https://b.com"])

    def test_no_args_shows_help_and_exits(self):
        with pytest.raises(SystemExit):
            parse_args(["--help"])

    def test_version_flag(self):
        with pytest.raises(SystemExit):
            parse_args(["--version"])


class TestParseBool:
    def test_true_values(self):
        assert parse_bool("true", "x") is True
        assert parse_bool("1", "x") is True
        assert parse_bool("yes", "x") is True
        assert parse_bool("on", "x") is True

    def test_false_values(self):
        assert parse_bool("false", "x") is False
        assert parse_bool("0", "x") is False
        assert parse_bool("no", "x") is False
        assert parse_bool("off", "x") is False

    def test_invalid_raises(self):
        with pytest.raises(UsageError):
            parse_bool("maybe", "myflag")


class TestMain:
    def test_no_args_shows_usage(self):
        with mock.patch.object(sys, "argv", ["vk_uploader"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    def test_setup_dispatches(self, mocker):
        """vk_uploader setup → calls cmd_setup."""
        mocker.patch.object(sys, "argv", ["vk_uploader", "setup"])
        mocker.patch("vk_uploader.cli.create_console")
        mock_setup = mocker.patch("vk_uploader.cli.cmd_setup")
        main()
        mock_setup.assert_called_once()

    def test_usage_error_exit_code_2(self, mocker):
        mocker.patch.object(
            sys, "argv", ["vk_uploader", "thumbnail=false"]
        )
        mocker.patch("vk_uploader.cli.create_console")
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2

    def test_subtitles_true_without_lang_exits(self, mocker):
        """subtitles=true without lang → error."""
        from vk_uploader.models import AppConfig, DefaultsConfig, DownloadConfig, VkConfig

        config = AppConfig(
            vk=VkConfig(access_token="tok", group_id="456", app_id="123"),
            defaults=DefaultsConfig(subtitles=True, lang=""),
            download=DownloadConfig(),
        )

        mocker.patch.object(sys, "argv", ["vk_uploader", "https://youtube.com/watch?v=abc"])
        mocker.patch("vk_uploader.cli.create_console")
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mocker.patch("vk_uploader.auth.ensure_token")

        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1

    def test_translation_true_without_lang_exits(self, mocker):
        """translation=true without lang → error."""
        from vk_uploader.models import AppConfig, DefaultsConfig, DownloadConfig, VkConfig

        config = AppConfig(
            vk=VkConfig(access_token="tok", group_id="456", app_id="123"),
            defaults=DefaultsConfig(translation=True, lang=""),
            download=DownloadConfig(),
        )

        mocker.patch.object(sys, "argv", ["vk_uploader", "https://youtube.com/watch?v=abc"])
        mocker.patch("vk_uploader.cli.create_console")
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mocker.patch("vk_uploader.auth.ensure_token")

        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1

    def test_subtitles_with_lang_passes(self, mocker):
        """subtitles=true with lang=ru → proceeds to pipeline."""
        from vk_uploader.models import AppConfig, DefaultsConfig, DownloadConfig, VkConfig

        config = AppConfig(
            vk=VkConfig(access_token="tok", group_id="456", app_id="123"),
            defaults=DefaultsConfig(subtitles=True, lang="ru"),
            download=DownloadConfig(),
        )

        mocker.patch.object(sys, "argv", ["vk_uploader", "https://youtube.com/watch?v=abc"])
        mocker.patch("vk_uploader.cli.create_console")
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mocker.patch("vk_uploader.auth.ensure_token")
        mock_pipeline = mocker.patch("vk_uploader.cli.run_pipeline")

        main()
        mock_pipeline.assert_called_once()

    def test_token_override_skips_oauth_and_reaches_pipeline(self, mocker):
        """token= is a one-shot override and should not trigger config OAuth."""
        from pathlib import Path

        from vk_uploader.models import AppConfig, DownloadConfig, VkConfig

        config = AppConfig(
            vk=VkConfig(access_token="", group_id="456", app_id="123"),
            download=DownloadConfig(),
        )

        mocker.patch.object(
            sys,
            "argv",
            ["vk_uploader", "https://youtube.com/watch?v=abc", "token=cli-token"],
        )
        mocker.patch("vk_uploader.cli.create_console")
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mock_cf.resolve_output_dir.return_value = Path("/tmp/videos")
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mock_ensure = mocker.patch("vk_uploader.auth.ensure_token")
        mock_pipeline = mocker.patch("vk_uploader.cli.run_pipeline")

        main()

        mock_ensure.assert_not_called()
        passed_config = mock_pipeline.call_args.args[2]
        assert passed_config.vk.access_token == "cli-token"

    def test_group_override_skips_group_prompt_in_auth(self, mocker):
        """group_id= should satisfy upload validation without being requested in setup."""
        from pathlib import Path

        from vk_uploader.models import AppConfig, DownloadConfig, VkConfig

        config = AppConfig(
            vk=VkConfig(access_token="tok", group_id="", app_id="123"),
            download=DownloadConfig(),
        )

        mocker.patch.object(
            sys,
            "argv",
            ["vk_uploader", "https://youtube.com/watch?v=abc", "group_id=999"],
        )
        mocker.patch("vk_uploader.cli.create_console")
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mock_cf.resolve_output_dir.return_value = Path("/tmp/videos")
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mock_ensure = mocker.patch("vk_uploader.auth.ensure_token")
        mock_pipeline = mocker.patch("vk_uploader.cli.run_pipeline")

        main()

        mock_ensure.assert_called_once()
        assert mock_ensure.call_args.kwargs["require_group"] is False
        ctx = mock_pipeline.call_args.args[1]
        assert ctx.group_id == "999"


class TestCmdSetup:
    def test_complete_config_prints_summary(self, mocker):
        """cmd_setup with complete config → prints summary, no errors."""
        from vk_uploader.models import AppConfig, DefaultsConfig, DownloadConfig, VkConfig

        config = AppConfig(
            vk=VkConfig(access_token="tok123", group_id="456", app_id="123", user_id="1"),
            defaults=DefaultsConfig(cookies_from_browser="firefox"),
            download=DownloadConfig(),
        )

        console = mocker.MagicMock()
        console.input.return_value = ""
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mocker.patch("vk_uploader.auth.ensure_token")
        mocker.patch("vk_uploader.auth._verify_token", return_value=True)
        mocker.patch("vk_uploader.cli._detect_browsers", return_value=["firefox"])

        cmd_setup(console)

        # Should have printed summary (Table objects created).
        assert console.print.call_count > 0

    def test_cookies_prompt_shown_when_not_set(self, mocker):
        """cmd_setup prompts for cookies_from_browser when not configured."""
        from vk_uploader.models import AppConfig, DefaultsConfig, DownloadConfig, VkConfig

        config = AppConfig(
            vk=VkConfig(access_token="tok123", group_id="456", app_id="123", user_id="1"),
            defaults=DefaultsConfig(cookies_from_browser=""),
            download=DownloadConfig(),
        )

        console = mocker.MagicMock()
        console.input.side_effect = ["", "firefox"]
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mocker.patch("vk_uploader.auth.ensure_token")
        mocker.patch("vk_uploader.auth._verify_token", return_value=True)
        mocker.patch("vk_uploader.cli._detect_browsers", return_value=["firefox", "chrome"])

        cmd_setup(console)

        # Should have saved cookies_from_browser.
        assert config.defaults.cookies_from_browser == "firefox"
        mock_cf.save.assert_called()

    def test_setup_saves_output_dir(self, mocker):
        """cmd_setup saves custom download output directory."""
        from vk_uploader.models import AppConfig, DefaultsConfig, DownloadConfig, VkConfig

        config = AppConfig(
            vk=VkConfig(access_token="tok123", group_id="456", app_id="123", user_id="1"),
            defaults=DefaultsConfig(cookies_from_browser="firefox"),
            download=DownloadConfig(),
        )

        console = mocker.MagicMock()
        console.input.return_value = "/tmp/videos"
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mocker.patch("vk_uploader.auth.ensure_token")
        mocker.patch("vk_uploader.auth._verify_token", return_value=True)

        cmd_setup(console)

        assert config.download.output_dir == "/tmp/videos"
        mock_cf.save.assert_called_with(config)

    def test_invalid_token_exits(self, mocker):
        """cmd_setup with invalid token → exits with code 1."""
        from vk_uploader.models import AppConfig, DefaultsConfig, DownloadConfig, VkConfig

        config = AppConfig(
            vk=VkConfig(access_token="bad", group_id="456", app_id="123"),
            defaults=DefaultsConfig(),
            download=DownloadConfig(),
        )

        console = mocker.MagicMock()
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mocker.patch("vk_uploader.auth.ensure_token")
        mocker.patch("vk_uploader.auth._verify_token", return_value=False)

        with pytest.raises(SystemExit) as exc:
            cmd_setup(console)
        assert exc.value.code == 1
