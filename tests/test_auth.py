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


class TestEnsureToken:
    def test_none_token_triggers_auth(self, mocker, tmp_path):
        """ensure_token should trigger OAuth when token is 'None' (YAML null)."""
        from vk_uploader.auth import ensure_token
        from vk_uploader.config import ConfigFile
        from vk_uploader.models import AppConfig, VkConfig

        console = mocker.MagicMock()
        console.input.return_value = "456"  # group_id prompt
        config = AppConfig(vk=VkConfig(access_token="None", app_id="123"))
        cfg = ConfigFile(config_dir=str(tmp_path), filename="test.yaml")

        mocker.patch("vk_uploader.auth.input")
        mock_flow = mocker.patch("vk_uploader.auth.run_oauth_flow",
            return_value=mocker.MagicMock(access_token="real-token", expires_at=None, user_id="1"))

        ensure_token(console, cfg, config)
        mock_flow.assert_called_once()
        assert config.vk.access_token == "real-token"

    def test_invalid_token_triggers_reauth(self, mocker, tmp_path):
        """When token exists but is rejected by VK API, trigger re-auth."""
        from vk_uploader.auth import ensure_token
        from vk_uploader.config import ConfigFile
        from vk_uploader.models import AppConfig, VkConfig

        console = mocker.MagicMock()
        config = AppConfig(
            vk=VkConfig(access_token="bad-token", app_id="123", group_id="456"),
        )
        cfg = ConfigFile(config_dir=str(tmp_path), filename="test.yaml")
        mock_save = mocker.patch.object(cfg, "save")

        # Mock _verify_token to return False (invalid token).
        mocker.patch("vk_uploader.auth._verify_token", return_value=False)
        mocker.patch("vk_uploader.auth.input")
        mock_flow = mocker.patch("vk_uploader.auth.run_oauth_flow",
            return_value=mocker.MagicMock(access_token="new-token", expires_at=None, user_id="1"))

        ensure_token(console, cfg, config)
        mock_flow.assert_called_once()
        assert config.vk.access_token == "new-token"
        # Should have saved after clearing bad token + after saving new token.
        assert mock_save.call_count >= 2

    def test_valid_token_skips_auth(self, mocker, tmp_path):
        """When token is valid, skip OAuth entirely."""
        from vk_uploader.auth import ensure_token
        from vk_uploader.config import ConfigFile
        from vk_uploader.models import AppConfig, VkConfig

        console = mocker.MagicMock()
        config = AppConfig(
            vk=VkConfig(access_token="good-token", app_id="123", group_id="456"),
        )
        cfg = ConfigFile(config_dir=str(tmp_path), filename="test.yaml")

        mocker.patch("vk_uploader.auth._verify_token", return_value=True)
        mock_flow = mocker.patch("vk_uploader.auth.run_oauth_flow")

        ensure_token(console, cfg, config)
        mock_flow.assert_not_called()
        assert config.vk.access_token == "good-token"

    def test_prompts_for_group_id_when_missing(self, mocker, tmp_path):
        """When group_id is empty, prompt user and save it."""
        from vk_uploader.auth import ensure_token
        from vk_uploader.config import ConfigFile
        from vk_uploader.models import AppConfig, VkConfig

        console = mocker.MagicMock()
        console.input.return_value = "999888777"
        config = AppConfig(
            vk=VkConfig(access_token="good-token", app_id="123", group_id=""),
        )
        cfg = ConfigFile(config_dir=str(tmp_path), filename="test.yaml")

        mocker.patch("vk_uploader.auth._verify_token", return_value=True)
        mocker.patch("vk_uploader.auth.run_oauth_flow")

        ensure_token(console, cfg, config)
        assert config.vk.group_id == "999888777"
        console.input.assert_any_call("Enter your VK Group ID: ")

    def test_empty_group_id_input_raises(self, mocker, tmp_path):
        """When group_id is empty and user provides empty input, raise AuthError."""
        from vk_uploader.auth import ensure_token
        from vk_uploader.config import ConfigFile
        from vk_uploader.models import AppConfig, VkConfig

        console = mocker.MagicMock()
        console.input.return_value = ""  # empty
        config = AppConfig(
            vk=VkConfig(access_token="good-token", app_id="123", group_id=""),
        )
        cfg = ConfigFile(config_dir=str(tmp_path), filename="test.yaml")

        mocker.patch("vk_uploader.auth._verify_token", return_value=True)
        mocker.patch("vk_uploader.auth.run_oauth_flow")

        with pytest.raises(AuthError, match="Group ID"):
            ensure_token(console, cfg, config)

    def test_group_id_already_set_skips_prompt(self, mocker, tmp_path):
        """When group_id is already in config, skip the prompt."""
        from vk_uploader.auth import ensure_token
        from vk_uploader.config import ConfigFile
        from vk_uploader.models import AppConfig, VkConfig

        console = mocker.MagicMock()
        config = AppConfig(
            vk=VkConfig(access_token="good-token", app_id="123", group_id="12345"),
        )
        cfg = ConfigFile(config_dir=str(tmp_path), filename="test.yaml")

        mocker.patch("vk_uploader.auth._verify_token", return_value=True)
        mocker.patch("vk_uploader.auth.run_oauth_flow")

        ensure_token(console, cfg, config)
        # console.input should NOT have been called for group_id
        group_id_calls = [
            c for c in console.input.call_args_list
            if "Group ID" in str(c)
        ]
        assert len(group_id_calls) == 0


class TestVerifyToken:
    def test_valid_token_returns_true(self, mocker):
        from vk_uploader.auth import _verify_token

        mock_resp = mocker.MagicMock()
        mock_resp.json.return_value = {"response": [{"id": 1}]}
        mocker.patch("requests.post", return_value=mock_resp)

        assert _verify_token("good-token") is True

    def test_error_code_5_returns_false(self, mocker):
        from vk_uploader.auth import _verify_token

        mock_resp = mocker.MagicMock()
        mock_resp.json.return_value = {"error": {"error_code": 5, "error_msg": "bad"}}
        mocker.patch("requests.post", return_value=mock_resp)

        assert _verify_token("bad-token") is False

    def test_network_error_returns_true(self, mocker):
        from vk_uploader.auth import _verify_token

        mocker.patch("requests.post", side_effect=Exception("timeout"))

        # Network error — don't invalidate token.
        assert _verify_token("token") is True
