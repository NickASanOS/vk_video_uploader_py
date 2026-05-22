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
        "scope=video,wall&"
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
    """Check token validity; if missing, expired, or invalid, run OAuth flow and save."""
    from datetime import datetime

    token = config.vk.access_token.strip()
    # Guard against "None"/"null" string from YAML null → str(None).
    if token and token.lower() in ("none", "null"):
        token = ""

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

    if token:
        # Verify token is actually valid with a lightweight API call.
        console.print("[dim]Verifying VK token...[/dim]")
        if not _verify_token(token):
            console.print("[yellow]Token is invalid, re-authorizing...[/yellow]")
            token = ""
            config.vk.access_token = ""
            config_file.save(config)

    if not token:
        app_id = config.vk.app_id.strip()
        if not app_id:
            console.print("VK App ID is required for authorization.")
            app_id = console.input("Enter your VK App ID: ").strip()
            if not app_id:
                raise AuthError("VK App ID is required.")
            config.vk.app_id = app_id

        console.print()
        console.print(
            "[bold]Make sure you are logged into VK in your default browser, "
            "then press ENTER.[/bold]"
        )
        input()

        console.print("Opening browser for VK authorization...")
        result = run_oauth_flow(app_id)

        config.vk.access_token = result.access_token
        config.vk.expires_at = result.expires_at
        config.vk.user_id = result.user_id
        config_file.save(config)
        console.print("[green]Token saved to config.[/green]")

    # --- Group ID ---
    group_id = config.vk.group_id.strip()
    if not group_id:
        console.print(
            "\nVK Group ID is required. You can find it in any community post URL:\n"
            "  wall-123456789_...  →  group_id is 123456789"
        )
        group_id = console.input("Enter your VK Group ID: ").strip()
        if not group_id:
            raise AuthError("VK Group ID is required.")
        config.vk.group_id = group_id
        config_file.save(config)
        console.print("[green]Group ID saved to config.[/green]")


def _verify_token(token: str) -> bool:
    """Check whether a VK access token is still valid via users.get."""
    import requests

    try:
        resp = requests.post(
            "https://api.vk.com/method/users.get",
            data={"access_token": token, "v": "5.199"},
            timeout=10,
        )
        data: dict[str, object] = resp.json()
        if "error" in data:
            err: dict[str, object] = data["error"]  # type: ignore[assignment]
            code = err.get("error_code", -1)
            # 5 = user authorization failed (bad token)
            return int(code) != 5  # type: ignore[arg-type]
        return "response" in data
    except Exception:
        # Network error — don't invalidate the token, let the main flow handle it.
        return True
