"""Tests for cli.py argument parsing."""

from __future__ import annotations

import sys
from unittest import mock

import pytest

from vk_uploader.cli import _parse_bool, main, parse_args
from vk_uploader.models import UsageError


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
        ])
        assert url == "https://youtube.com/watch?v=abc"
        assert overrides == {"thumbnail": "false", "publish_delay_hours": "72"}

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
        assert _parse_bool("true", "x") is True
        assert _parse_bool("1", "x") is True
        assert _parse_bool("yes", "x") is True
        assert _parse_bool("on", "x") is True

    def test_false_values(self):
        assert _parse_bool("false", "x") is False
        assert _parse_bool("0", "x") is False
        assert _parse_bool("no", "x") is False
        assert _parse_bool("off", "x") is False

    def test_invalid_raises(self):
        with pytest.raises(UsageError):
            _parse_bool("maybe", "myflag")


class TestMain:
    def test_no_args_shows_usage(self):
        with mock.patch.object(sys, "argv", ["vk_uploader"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    def test_usage_error_exit_code_2(self, mocker):
        mocker.patch.object(
            sys, "argv", ["vk_uploader", "thumbnail=false"]
        )
        mocker.patch("vk_uploader.cli.create_console")
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2
