"""Tests for auth.py."""

from __future__ import annotations

import pytest

from vk_uploader.auth import AuthError, AuthResult, run_oauth_flow


class TestRunOauthFlow:
    def test_parses_access_token_from_blank_url(self, mocker):
        mocker.patch("vk_uploader.auth.webbrowser.open")
        url = (
            "https://oauth.vk.com/blank.html"
            "#access_token=tok123&expires_in=0&user_id=42"
        )
        mocker.patch("vk_uploader.auth.input", return_value=url)

        result = run_oauth_flow("12345")
        assert isinstance(result, AuthResult)
        assert result.access_token == "tok123"
        assert result.user_id == "42"
        assert result.expires_at is None  # expires_in=0 means no expiry

    def test_parses_token_with_expiry(self, mocker):
        mocker.patch("vk_uploader.auth.webbrowser.open")
        url = (
            "https://oauth.vk.com/blank.html"
            "#access_token=tok456&expires_in=86400&user_id=1"
        )
        mocker.patch("vk_uploader.auth.input", return_value=url)

        result = run_oauth_flow("12345")
        assert result.access_token == "tok456"
        assert result.expires_at is not None

    def test_parses_token_from_fragment_only(self, mocker):
        mocker.patch("vk_uploader.auth.webbrowser.open")
        fragment = "access_token=tok789&expires_in=0&user_id=99"
        mocker.patch("vk_uploader.auth.input", return_value=fragment)

        result = run_oauth_flow("12345")
        assert result.access_token == "tok789"

    def test_raises_on_oauth_error(self, mocker):
        mocker.patch("vk_uploader.auth.webbrowser.open")
        url = (
            "https://oauth.vk.com/blank.html"
            "#error=access_denied&error_description=User+denied"
        )
        mocker.patch("vk_uploader.auth.input", return_value=url)

        try:
            run_oauth_flow("12345")
            pytest.fail("Should have raised AuthError")
        except AuthError as e:
            assert "access_denied" in str(e)

    def test_raises_when_no_token(self, mocker):
        mocker.patch("vk_uploader.auth.webbrowser.open")
        mocker.patch("vk_uploader.auth.input", return_value="https://oauth.vk.com/blank.html")

        try:
            run_oauth_flow("12345")
            pytest.fail("Should have raised AuthError")
        except AuthError as e:
            assert "No access_token" in str(e)
