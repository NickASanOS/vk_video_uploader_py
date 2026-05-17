"""OAuth2 Implicit Flow for VK — desktop (blank.html) approach."""

from __future__ import annotations

import webbrowser
from typing import NamedTuple
from urllib.parse import parse_qs, urlparse

from rich.console import Console

from vk_uploader.config import ConfigFile
from vk_uploader.models import AppConfig, AuthError


class AuthResult(NamedTuple):
    access_token: str
    expires_at: str | None  # ISO 8601
    user_id: str | None


_VK_BLANK = "https://oauth.vk.com/blank.html"


def run_oauth_flow(app_id: str) -> AuthResult:
    """Open browser for VK OAuth, ask user to paste the redirect URL.

    Desktop VK apps can only use https://oauth.vk.com/blank.html as
    redirect_uri. After authorization the browser lands on blank.html
    with the token in the URL fragment. The user copies the full URL
    and pastes it here.
    """
    auth_url = (
        "https://oauth.vk.com/authorize?"
        f"client_id={app_id}&"
        f"redirect_uri={_VK_BLANK}&"
        "display=page&"
        "scope=video&"
        "response_type=token&"
        "v=5.199"
    )

    webbrowser.open(auth_url)
    print()
    print("After authorization, your browser will show a blank page.")
    print("Copy the FULL URL from the address bar and paste it below.")
    print("It should look like: https://oauth.vk.com/blank.html#access_token=...")
    print()

    redirect_url = input("Paste the redirect URL: ").strip()

    parsed = urlparse(redirect_url)
    if parsed.fragment:
        params = parse_qs(parsed.fragment)
    else:
        # Maybe the user pasted just the fragment?
        query_str = redirect_url.split("#", 1)[-1] if "#" in redirect_url else redirect_url
        params = parse_qs(query_str)

    access_token_list = params.get("access_token", [])
    error_list = params.get("error", [])

    if error_list:
        err_desc = params.get("error_description", ["Unknown error"])
        raise AuthError(f"OAuth error: {error_list[0]} — {err_desc[0]}")

    if not access_token_list or not access_token_list[0]:
        raise AuthError(
            "No access_token found in the URL. "
            "Make sure you copied the full URL from the address bar."
        )

    expires_in = params.get("expires_in", ["0"])[0]
    expires_at = None
    try:
        ei = int(expires_in)
        if ei > 0:
            from datetime import datetime, timedelta
            expires_at = (datetime.now() + timedelta(seconds=ei)).isoformat()
    except (ValueError, TypeError):
        pass

    return AuthResult(
        access_token=access_token_list[0],
        expires_at=expires_at,
        user_id=params.get("user_id", [None])[0],
    )


def ensure_token(console: Console, config_file: ConfigFile, config: AppConfig) -> None:
    """Check token validity; if missing or expired, run OAuth flow and save."""
    from datetime import datetime

    token = config.vk.access_token.strip()
    if token:
        expires_str = config.vk.expires_at
        if expires_str:
            try:
                expires = datetime.fromisoformat(expires_str)
                if datetime.now() > expires:
                    console.print("[yellow]Token expired, re-authorizing...[/yellow]")
                    token = ""
            except (ValueError, TypeError):
                pass

    if not token:
        app_id = config.vk.app_id.strip()
        if not app_id:
            console.print("VK App ID is required for authorization.")
            app_id = console.input("Enter your VK App ID: ").strip()
            if not app_id:
                raise AuthError("VK App ID is required.")
            config.vk.app_id = app_id

        console.print("Opening browser for VK authorization...")
        result = run_oauth_flow(app_id)

        config.vk.access_token = result.access_token
        config.vk.expires_at = result.expires_at
        config.vk.user_id = result.user_id
        config_file.save(config)
        console.print("[green]Token saved to config.[/green]")
