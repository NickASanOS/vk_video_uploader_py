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

    def test_cleanup_after_upload_override(self):
        url, overrides = parse_args([
            "https://youtube.com/watch?v=abc",
            "cleanup_after_upload=true",
        ])
        assert url == "https://youtube.com/watch?v=abc"
        assert overrides == {"cleanup_after_upload": "true"}

    def test_links_file_cannot_be_combined_with_url(self):
        with pytest.raises(UsageError, match="links_file cannot be combined"):
            parse_args([
                "https://youtube.com/watch?v=abc",
                "links_file=/tmp/links.txt",
            ])

    def test_links_file_cannot_be_combined_with_ylink(self):
        with pytest.raises(UsageError, match="links_file cannot be combined"):
            parse_args([
                "ylink=https://youtube.com/watch?v=abc",
                "links_file=/tmp/links.txt",
            ])

    def test_empty_links_file_raises_usage_error(self):
        with pytest.raises(UsageError, match="links_file must not be empty"):
            parse_args(["links_file="])

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


class TestPromptBrowser:
    def test_empty_choice_uses_detected_default(self, mocker):
        from vk_uploader.cli import _prompt_browser

        mocker.patch("vk_uploader.cli._detect_browsers", return_value=["firefox"])
        mocker.patch("vk_uploader.cli.input", return_value="")

        assert _prompt_browser(mocker.MagicMock()) == "firefox"

    def test_empty_choice_without_detected_browser_skips(self, mocker):
        from vk_uploader.cli import _prompt_browser

        mocker.patch("vk_uploader.cli._detect_browsers", return_value=[])
        mocker.patch("vk_uploader.cli.input", return_value="")

        assert _prompt_browser(mocker.MagicMock()) is None


# ── Batch mode tests ─────────────────────────────────────────────────────────


class TestParseLineArgs:
    """Unit tests for _parse_line_args — single-line parsing."""

    def test_simple_url(self):
        from vk_uploader.cli import _parse_line_args

        url, ov = _parse_line_args(
            "https://youtube.com/watch?v=abc", "f.txt", 1
        )
        assert url == "https://youtube.com/watch?v=abc"
        assert ov == {}

    def test_url_with_overrides(self):
        from vk_uploader.cli import _parse_line_args

        url, ov = _parse_line_args(
            "https://youtube.com/watch?v=abc subtitles=true lang=ru", "f.txt", 1
        )
        assert url == "https://youtube.com/watch?v=abc"
        assert ov == {"subtitles": "true", "lang": "ru"}

    def test_ylink_key(self):
        from vk_uploader.cli import _parse_line_args

        url, ov = _parse_line_args(
            "ylink=https://youtube.com/watch?v=abc wallpost=true", "f.txt", 1
        )
        assert url == "https://youtube.com/watch?v=abc"
        assert ov == {"wallpost": "true"}

    def test_quoted_title(self):
        from vk_uploader.cli import _parse_line_args

        url, ov = _parse_line_args(
            'https://youtube.com/watch?v=abc title="My Custom Title"', "f.txt", 1
        )
        assert ov == {"title": "My Custom Title"}

    def test_quoted_title_single_quotes(self):
        from vk_uploader.cli import _parse_line_args

        url, ov = _parse_line_args(
            "https://youtube.com/watch?v=abc title='Single Quoted'", "f.txt", 1
        )
        assert ov == {"title": "Single Quoted"}

    def test_description_with_spaces(self):
        from vk_uploader.cli import _parse_line_args

        url, ov = _parse_line_args(
            'https://youtube.com/watch?v=abc description="A long description here"',
            "f.txt",
            1,
        )
        assert ov == {"description": "A long description here"}

    def test_missing_url_raises(self):
        from vk_uploader.cli import _parse_line_args

        with pytest.raises(UsageError, match="YouTube URL is required"):
            _parse_line_args("subtitles=true", "f.txt", 3)

    def test_duplicate_url_raises(self):
        from vk_uploader.cli import _parse_line_args

        with pytest.raises(UsageError, match="only one YouTube URL"):
            _parse_line_args(
                "https://a.com https://b.com", "f.txt", 5
            )

    def test_unknown_key_raises(self):
        from vk_uploader.cli import _parse_line_args

        with pytest.raises(UsageError, match="unknown option"):
            _parse_line_args(
                "https://youtube.com/watch?v=abc foo=bar", "f.txt", 1
            )

    def test_invalid_quoting_raises(self):
        from vk_uploader.cli import _parse_line_args

        with pytest.raises(UsageError, match="invalid quoting"):
            _parse_line_args(
                'https://youtube.com/watch?v=abc title="unclosed', "f.txt", 1
            )

    def test_url_with_query_params(self):
        """YouTube URL with = in query string is not parsed as override."""
        from vk_uploader.cli import _parse_line_args

        url, ov = _parse_line_args(
            "https://www.youtube.com/watch?v=abc&list=xyz", "f.txt", 1
        )
        assert url == "https://www.youtube.com/watch?v=abc&list=xyz"
        assert ov == {}

    def test_cleanup_after_upload_line_override(self):
        from vk_uploader.cli import _parse_line_args

        url, ov = _parse_line_args(
            "https://youtube.com/watch?v=abc cleanup_after_upload=true", "f.txt", 1
        )
        assert url == "https://youtube.com/watch?v=abc"
        assert ov == {"cleanup_after_upload": "true"}

    def test_line_number_in_errors(self):
        from vk_uploader.cli import _parse_line_args

        with pytest.raises(UsageError, match="links.txt:42"):
            _parse_line_args("subtitles=true", "links.txt", 42)


class TestParseLinksFile:
    """Tests for parse_links_file — full file parsing."""

    def test_parses_multiple_jobs(self, tmp_path):
        from vk_uploader.cli import parse_links_file

        f = tmp_path / "links.txt"
        f.write_text(
            "https://youtube.com/watch?v=abc subtitles=true\n"
            "# a comment\n"
            "https://youtube.com/watch?v=def wallpost=true\n"
            "\n"
            "ylink=https://youtube.com/watch?v=ghi album=MyVids\n"
        )

        jobs = parse_links_file(str(f))
        assert len(jobs) == 3
        assert jobs[0] == (1, "https://youtube.com/watch?v=abc", {"subtitles": "true"})
        assert jobs[1] == (3, "https://youtube.com/watch?v=def", {"wallpost": "true"})
        assert jobs[2] == (5, "https://youtube.com/watch?v=ghi", {"album": "MyVids"})

    def test_empty_file_raises(self, tmp_path):
        from vk_uploader.cli import parse_links_file

        f = tmp_path / "empty.txt"
        f.write_text("# only a comment\n")

        with pytest.raises(UsageError, match="no valid job lines"):
            parse_links_file(str(f))

    def test_all_blank_lines_raises(self, tmp_path):
        from vk_uploader.cli import parse_links_file

        f = tmp_path / "blanks.txt"
        f.write_text("\n\n   \n")

        with pytest.raises(UsageError, match="no valid job lines"):
            parse_links_file(str(f))

    def test_malformed_line_includes_path_and_number(self, tmp_path):
        from vk_uploader.cli import parse_links_file

        f = tmp_path / "bad.txt"
        f.write_text("https://a.com\nfoo=bar\n")

        with pytest.raises(UsageError, match="bad.txt:2"):
            parse_links_file(str(f))

    def test_file_not_found(self):
        from vk_uploader.cli import parse_links_file

        with pytest.raises(UsageError, match="cannot read links file"):
            parse_links_file("/nonexistent/path.txt")


class TestCopyConfig:
    """Tests for _copy_config — config isolation."""

    def test_deep_copy_isolation(self):
        from vk_uploader.cli import _apply_overrides, _copy_config
        from vk_uploader.models import AppConfig, DefaultsConfig, DownloadConfig, VkConfig

        base = AppConfig(
            vk=VkConfig(access_token="tok", group_id="123", app_id="456"),
            defaults=DefaultsConfig(
                thumbnail=True, subtitles=False, lang="ru",
            ),
            download=DownloadConfig(),
        )

        copy1 = _copy_config(base)
        _apply_overrides(copy1, {"subtitles": "true", "lang": "en"})

        # copy1 changed
        assert copy1.defaults.subtitles is True
        assert copy1.defaults.lang == "en"

        # base unchanged
        assert base.defaults.subtitles is False
        assert base.defaults.lang == "ru"

        # copy2 from base is clean
        copy2 = _copy_config(base)
        assert copy2.defaults.subtitles is False
        assert copy2.defaults.lang == "ru"

    def test_copy_preserves_nested_values(self):
        from vk_uploader.cli import _copy_config
        from vk_uploader.models import AppConfig, DefaultsConfig, DownloadConfig, VkConfig

        original = AppConfig(
            vk=VkConfig(
                access_token="tok123", group_id="999",
                app_id="111", expires_at="2026-12-31", user_id="42",
            ),
            defaults=DefaultsConfig(
                publish_delay_hours=48, thumbnail=False, wallpost=True,
                translation=True, subtitles=True, lang="de",
                cookies_from_browser="firefox",
            ),
            download=DownloadConfig(output_dir="/tmp/vids", video_format="best"),
        )

        copy = _copy_config(original)
        assert copy.vk.access_token == "tok123"
        assert copy.vk.group_id == "999"
        assert copy.defaults.publish_delay_hours == 48
        assert copy.defaults.cookies_from_browser == "firefox"
        assert copy.download.output_dir == "/tmp/vids"


class TestBatchMain:
    """Integration tests for _batch_main."""

    def test_dispatches_to_batch_main(self, mocker, tmp_path):
        """vk_uploader links_file=... → _batch_main called."""
        f = tmp_path / "links.txt"
        f.write_text("https://youtube.com/watch?v=abc\n")

        mocker.patch.object(sys, "argv", [
            "vk_uploader", f"links_file={f}",
        ])
        mocker.patch("vk_uploader.cli.create_console")
        mock_batch = mocker.patch("vk_uploader.cli._batch_main")

        main()
        mock_batch.assert_called_once()

    def test_command_level_overrides_passed_to_batch(self, mocker, tmp_path):
        """Global overrides like publish_delay_hours=48 go to _batch_main."""
        f = tmp_path / "links.txt"
        f.write_text("https://youtube.com/watch?v=abc\n")

        mocker.patch.object(sys, "argv", [
            "vk_uploader", f"links_file={f}", "publish_delay_hours=48",
        ])
        mocker.patch("vk_uploader.cli.create_console")
        mock_batch = mocker.patch("vk_uploader.cli._batch_main")

        main()
        _, _, global_ov = mock_batch.call_args[0]
        assert "publish_delay_hours" in global_ov
        assert global_ov["publish_delay_hours"] == "48"

    def test_links_file_removed_from_overrides(self, mocker, tmp_path):
        """links_file is NOT in the overrides dict passed to _batch_main."""
        f = tmp_path / "links.txt"
        f.write_text("https://youtube.com/watch?v=abc\n")

        mocker.patch.object(sys, "argv", [
            "vk_uploader", f"links_file={f}", "thumbnail=false",
        ])
        mocker.patch("vk_uploader.cli.create_console")
        mock_batch = mocker.patch("vk_uploader.cli._batch_main")

        main()
        _, _, global_ov = mock_batch.call_args[0]
        assert "links_file" not in global_ov
        assert global_ov == {"thumbnail": "false"}

    def test_batch_main_parses_file_before_auth(self, mocker, tmp_path):
        """Malformed links file fails before auth/setup side effects."""
        f = tmp_path / "links.txt"
        f.write_text("https://youtube.com/watch?v=abc\nfoo=bar\n")

        mock_config_file = mocker.patch("vk_uploader.cli.ConfigFile")
        mock_ensure_token = mocker.patch("vk_uploader.auth.ensure_token")

        from vk_uploader.cli import _batch_main

        with pytest.raises(UsageError, match="links.txt:2"):
            _batch_main(mocker.MagicMock(), str(f), {})

        mock_config_file.assert_not_called()
        mock_ensure_token.assert_not_called()

    def test_batch_main_success_path(self, mocker, tmp_path):
        """_batch_main runs pipeline for each job and prints summary."""
        from vk_uploader.models import (
            AppConfig,
            DefaultsConfig,
            DownloadConfig,
            PipelineStage,
            VkConfig,
        )

        f = tmp_path / "links.txt"
        f.write_text(
            "https://youtube.com/watch?v=abc subtitles=true lang=en\n"
            "https://youtube.com/watch?v=def wallpost=true\n"
        )

        config = AppConfig(
            vk=VkConfig(access_token="tok", group_id="456", app_id="123"),
            defaults=DefaultsConfig(),
            download=DownloadConfig(),
        )

        console = mocker.MagicMock()
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mock_cf.resolve_output_dir.return_value = tmp_path
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mocker.patch("vk_uploader.auth.ensure_token")

        # Simulate successful pipeline runs.
        def _fake_pipeline(console, ctx, cfg):
            ctx.stage = PipelineStage.COMPLETED

        mock_pipeline = mocker.patch(
            "vk_uploader.cli.run_pipeline", side_effect=_fake_pipeline
        )

        from vk_uploader.cli import _batch_main

        _batch_main(console, str(f), {})

        assert mock_pipeline.call_count == 2
        # Summary printed — find the summary line among all console.print calls.
        summary_calls = [
            c[0][0] for c in console.print.call_args_list
            if len(c[0]) > 0 and isinstance(c[0][0], str) and "Success" in c[0][0]
        ]
        assert len(summary_calls) >= 1
        assert "2" in summary_calls[0]

    def test_batch_token_and_group_overrides_skip_auth_prompts(self, mocker, tmp_path):
        """Batch command-level auth overrides behave like single-run overrides."""
        from vk_uploader.models import (
            AppConfig,
            DefaultsConfig,
            DownloadConfig,
            PipelineStage,
            VkConfig,
        )

        f = tmp_path / "links.txt"
        f.write_text("https://youtube.com/watch?v=abc\n")

        config = AppConfig(
            vk=VkConfig(access_token="", group_id="", app_id="123"),
            defaults=DefaultsConfig(),
            download=DownloadConfig(),
        )

        console = mocker.MagicMock()
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mock_cf.resolve_output_dir.return_value = tmp_path
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mock_ensure = mocker.patch("vk_uploader.auth.ensure_token")

        seen_configs = []

        def _fake_pipeline(console, ctx, cfg):
            seen_configs.append(cfg)
            ctx.stage = PipelineStage.COMPLETED

        mocker.patch("vk_uploader.cli.run_pipeline", side_effect=_fake_pipeline)

        from vk_uploader.cli import _batch_main

        _batch_main(
            console,
            str(f),
            {"token": "cli-token", "group_id": "999"},
        )

        mock_ensure.assert_not_called()
        assert seen_configs[0].vk.access_token == "cli-token"
        assert seen_configs[0].vk.group_id == "999"

    def test_batch_line_level_auth_overrides_skip_auth_prompts(self, mocker, tmp_path):
        """Line-level auth overrides should not force setup when every job has them."""
        from vk_uploader.models import (
            AppConfig,
            DefaultsConfig,
            DownloadConfig,
            PipelineStage,
            VkConfig,
        )

        f = tmp_path / "links.txt"
        f.write_text(
            "https://youtube.com/watch?v=abc token=line-token-1 group_id=111\n"
            "https://youtube.com/watch?v=def token=line-token-2 group_id=222\n"
        )

        config = AppConfig(
            vk=VkConfig(access_token="", group_id="", app_id="123"),
            defaults=DefaultsConfig(),
            download=DownloadConfig(),
        )

        console = mocker.MagicMock()
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mock_cf.resolve_output_dir.return_value = tmp_path
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mock_ensure = mocker.patch("vk_uploader.auth.ensure_token")

        seen_configs = []

        def _fake_pipeline(console, ctx, cfg):
            seen_configs.append(cfg)
            ctx.stage = PipelineStage.COMPLETED

        mocker.patch("vk_uploader.cli.run_pipeline", side_effect=_fake_pipeline)

        from vk_uploader.cli import _batch_main

        _batch_main(console, str(f), {})

        mock_ensure.assert_not_called()
        assert [cfg.vk.access_token for cfg in seen_configs] == [
            "line-token-1",
            "line-token-2",
        ]
        assert [cfg.vk.group_id for cfg in seen_configs] == ["111", "222"]

    def test_command_level_metadata_overrides_apply_to_batch_jobs(self, mocker, tmp_path):
        """Global title/description/album apply unless line overrides them."""
        from vk_uploader.models import (
            AppConfig,
            DefaultsConfig,
            DownloadConfig,
            PipelineStage,
            VkConfig,
        )

        f = tmp_path / "links.txt"
        f.write_text(
            "https://youtube.com/watch?v=one\n"
            "https://youtube.com/watch?v=two title=\"Line Title\" album=LineAlbum\n"
        )

        config = AppConfig(
            vk=VkConfig(access_token="tok", group_id="456", app_id="123"),
            defaults=DefaultsConfig(),
            download=DownloadConfig(),
        )

        console = mocker.MagicMock()
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mock_cf.resolve_output_dir.return_value = tmp_path
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mocker.patch("vk_uploader.auth.ensure_token")

        seen_contexts = []

        def _fake_pipeline(console, ctx, cfg):
            seen_contexts.append(ctx)
            ctx.stage = PipelineStage.COMPLETED

        mocker.patch("vk_uploader.cli.run_pipeline", side_effect=_fake_pipeline)

        from vk_uploader.cli import _batch_main

        _batch_main(
            console,
            str(f),
            {
                "title": "Global Title",
                "description": "Global Description",
                "album": "GlobalAlbum",
            },
        )

        assert len(seen_contexts) == 2
        assert seen_contexts[0].title_override == "Global Title"
        assert seen_contexts[0].description_override == "Global Description"
        assert seen_contexts[0].album_spec == "GlobalAlbum"
        assert seen_contexts[1].title_override == "Line Title"
        assert seen_contexts[1].description_override == "Global Description"
        assert seen_contexts[1].album_spec == "LineAlbum"

    def test_bot_detection_retry_saves_browser_for_later_batch_jobs(
        self, mocker, tmp_path
    ):
        """Browser selected after bot detection is saved and reused by next jobs."""
        from vk_uploader.models import (
            AppConfig,
            BotDetectionError,
            DefaultsConfig,
            DownloadConfig,
            PipelineStage,
            VkConfig,
        )

        f = tmp_path / "links.txt"
        f.write_text(
            "https://youtube.com/watch?v=one\n"
            "https://youtube.com/watch?v=two\n"
        )

        config = AppConfig(
            vk=VkConfig(access_token="tok", group_id="456", app_id="123"),
            defaults=DefaultsConfig(cookies_from_browser=""),
            download=DownloadConfig(),
        )

        console = mocker.MagicMock()
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mock_cf.resolve_output_dir.return_value = tmp_path
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mocker.patch("vk_uploader.auth.ensure_token")
        mocker.patch("vk_uploader.cli._prompt_browser", return_value="firefox")

        seen_browsers = []

        def _fake_pipeline(console, ctx, cfg):
            seen_browsers.append(cfg.defaults.cookies_from_browser)
            if len(seen_browsers) == 1:
                raise BotDetectionError("bot detection")
            ctx.stage = PipelineStage.COMPLETED

        mocker.patch("vk_uploader.cli.run_pipeline", side_effect=_fake_pipeline)

        from vk_uploader.cli import _batch_main

        _batch_main(console, str(f), {})

        assert seen_browsers == ["", "firefox", "firefox"]
        saved_config = mock_cf.save.call_args.args[0]
        assert saved_config.defaults.cookies_from_browser == "firefox"

    def test_batch_main_with_failures(self, mocker, tmp_path):
        """_batch_main continues on failure, prints failed jobs, exits 1."""
        from vk_uploader.models import (
            AppConfig,
            DefaultsConfig,
            DownloadConfig,
            PipelineStage,
            VkConfig,
        )

        f = tmp_path / "links.txt"
        f.write_text(
            "https://youtube.com/watch?v=ok\n"
            "https://youtube.com/watch?v=fail\n"
        )

        config = AppConfig(
            vk=VkConfig(access_token="tok", group_id="456", app_id="123"),
            defaults=DefaultsConfig(),
            download=DownloadConfig(),
        )

        console = mocker.MagicMock()
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mock_cf.resolve_output_dir.return_value = tmp_path
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mocker.patch("vk_uploader.auth.ensure_token")

        call_count = 0

        def _fake_pipeline(console, ctx, cfg):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                ctx.stage = PipelineStage.ERROR
                ctx.error_message = "VK upload failed"
            else:
                ctx.stage = PipelineStage.COMPLETED

        mocker.patch(
            "vk_uploader.cli.run_pipeline", side_effect=_fake_pipeline
        )

        from vk_uploader.cli import _batch_main

        with pytest.raises(SystemExit) as exc:
            _batch_main(console, str(f), {})
        assert exc.value.code == 1

    def test_config_validation_failure_skips_job(self, mocker, tmp_path):
        """Job with missing lang when subtitles=true is skipped."""
        from vk_uploader.models import (
            AppConfig,
            DefaultsConfig,
            DownloadConfig,
            VkConfig,
        )

        f = tmp_path / "links.txt"
        f.write_text(
            "https://youtube.com/watch?v=abc subtitles=true\n"
        )

        config = AppConfig(
            vk=VkConfig(access_token="tok", group_id="456", app_id="123"),
            defaults=DefaultsConfig(lang=""),  # no lang
            download=DownloadConfig(),
        )

        console = mocker.MagicMock()
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mock_cf.resolve_output_dir.return_value = tmp_path
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mocker.patch("vk_uploader.auth.ensure_token")
        mock_pipeline = mocker.patch("vk_uploader.cli.run_pipeline")

        from vk_uploader.cli import _batch_main

        with pytest.raises(SystemExit) as exc:
            _batch_main(console, str(f), {})
        assert exc.value.code == 1
        # Pipeline should NOT have been called (config invalid).
        mock_pipeline.assert_not_called()

    def test_existing_single_url_still_works(self, mocker):
        """Backwards compatibility: single URL without links_file works."""
        from vk_uploader.models import AppConfig, DefaultsConfig, DownloadConfig, VkConfig

        config = AppConfig(
            vk=VkConfig(access_token="tok", group_id="456", app_id="123"),
            defaults=DefaultsConfig(),
            download=DownloadConfig(),
        )

        mocker.patch.object(sys, "argv", [
            "vk_uploader", "https://youtube.com/watch?v=abc",
        ])
        mocker.patch("vk_uploader.cli.create_console")
        mock_cf = mocker.MagicMock()
        mock_cf.load.return_value = config
        mocker.patch("vk_uploader.cli.ConfigFile", return_value=mock_cf)
        mocker.patch("vk_uploader.auth.ensure_token")
        mock_pipeline = mocker.patch("vk_uploader.cli.run_pipeline")

        main()
        mock_pipeline.assert_called_once()
