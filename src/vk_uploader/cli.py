"""CLI argument parsing and main entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console

from vk_uploader.config import ConfigFile
from vk_uploader.logging_setup import create_console
from vk_uploader.models import (
    AuthError,
    BotDetectionError,
    ConfigError,
    DownloadError,
    JobContext,
    PipelineStage,
    UsageError,
    parse_bool,
)
from vk_uploader.pipeline import run_pipeline
from vk_uploader.vk_api import VkApiError

_VALID_OVERRIDES = frozenset({
    "ylink",
    "thumbnail",
    "publish_delay_hours",
    "output_dir",
    "token",
    "group_id",
    "wallpost",
    "title",
    "description",
    "video_format",
    "translation",
    "subtitles",
    "lang",
    "cookies_from_browser",
    "album",
})


def parse_args(argv: list[str]) -> tuple[str, dict[str, str]]:
    """Parse CLI args into (youtube_url, overrides_dict).

    Supports:
      vk_uploader <youtube_url> [key=value ...]
      vk_uploader ylink=<youtube_url> [key=value ...]
    """
    url: str | None = None
    overrides: dict[str, str] = {}

    for arg in argv:
        if arg in ("--help", "-h"):
            _print_usage()
            sys.exit(0)
        if arg in ("--version", "-V"):
            from vk_uploader import __version__
            print(f"vk_uploader {__version__}")
            sys.exit(0)

        if "=" not in arg:
            if url is not None:
                raise UsageError("Only one YouTube URL may be provided.")
            url = arg
        else:
            key, _, value = arg.partition("=")
            # If the key part looks like a URL (contains ://), this is a URL
            # with a query string, not a key=value override.
            if "://" in key:
                if url is not None:
                    raise UsageError("Only one YouTube URL may be provided.")
                url = arg
                continue
            key = key.strip().lower()
            value = value.strip()
            if not key:
                raise UsageError(f"Invalid argument: {arg!r}")
            if key == "ylink":
                if url is not None:
                    raise UsageError("URL specified both positionally and as ylink=...")
                url = value
            elif key in _VALID_OVERRIDES:
                overrides[key] = value
            else:
                raise UsageError(
                    f"Unknown option: {key!r}. Valid options: {sorted(_VALID_OVERRIDES)}"
                )

    if url is None:
        raise UsageError(
            "YouTube URL is required.\nUsage: vk_uploader <youtube_url> [key=value ...]"
        )

    return url, overrides


def main() -> None:
    console = create_console()

    try:
        args = sys.argv[1:]
        if not args:
            _print_usage()
            sys.exit(0)

        url, overrides = parse_args(args)

        config_file = ConfigFile()
        config = config_file.load()

        # --- Auth (may reload config — apply overrides AFTER) ---
        from vk_uploader.auth import ensure_token

        old_token = config.vk.access_token
        ensure_token(console, config_file, config)
        # Only reload if the token was changed (avoids wiping CLI overrides).
        if config.vk.access_token != old_token:
            config = config_file.load()

        # --- Merge CLI overrides onto config (after potential reload) ---
        if "thumbnail" in overrides:
            config.defaults.thumbnail = parse_bool(overrides["thumbnail"], "thumbnail")
        if "publish_delay_hours" in overrides:
            try:
                val = int(overrides["publish_delay_hours"])
                if val < 0:
                    raise UsageError(
                        f"publish_delay_hours must be >= 0, got: {val}"
                    )
                config.defaults.publish_delay_hours = val
            except ValueError:
                raise UsageError(
                    f"publish_delay_hours must be an integer, "
                    f"got: {overrides['publish_delay_hours']!r}"
                ) from None
        if "output_dir" in overrides:
            config.download.output_dir = overrides["output_dir"]
        if "token" in overrides:
            config.vk.access_token = overrides["token"]
        if "group_id" in overrides:
            config.vk.group_id = overrides["group_id"]
        if "wallpost" in overrides:
            config.defaults.wallpost = parse_bool(overrides["wallpost"], "wallpost")
        if "video_format" in overrides:
            config.download.video_format = overrides["video_format"]
        if "translation" in overrides:
            config.defaults.translation = parse_bool(overrides["translation"], "translation")
        if "subtitles" in overrides:
            config.defaults.subtitles = parse_bool(overrides["subtitles"], "subtitles")
        if "lang" in overrides:
            config.defaults.lang = overrides["lang"]
        if "cookies_from_browser" in overrides:
            config.defaults.cookies_from_browser = overrides["cookies_from_browser"]

        title_override = overrides.get("title")
        description_override = overrides.get("description")
        album_spec = overrides.get("album")

        # --- Validate ---
        token = config.vk.access_token.strip()
        if not token:
            console.print("[red]VK access token is required.[/red]")
            console.print("Run vk_uploader without arguments to configure.")
            sys.exit(1)

        group_id = config.vk.group_id.strip()
        if not group_id:
            console.print("[red]VK group_id is required in config.[/red]")
            sys.exit(1)

        output_dir = config_file.resolve_output_dir(config)

        # --- Build JobContext ---
        ctx = JobContext(
            youtube_url=url,
            output_dir=output_dir,
            group_id=group_id,
            publish_delay_hours=config.defaults.publish_delay_hours,
            thumbnail_enabled=config.defaults.thumbnail,
            wallpost=config.defaults.wallpost,
            title_override=title_override,
            description_override=description_override,
            album_spec=album_spec,
        )

        # --- Run pipeline (with bot-detection retry) ---
        while True:
            try:
                run_pipeline(console, ctx, config)
                break
            except BotDetectionError:
                if config.defaults.cookies_from_browser:
                    # Already configured but still failing — propagate.
                    raise
                browser = _prompt_browser(console)
                if browser is None:
                    raise
                config.defaults.cookies_from_browser = browser
                config_file.save(config)
                console.print(
                    f"[green]Saved cookies_from_browser={browser} to config."
                    f" Retrying...[/green]"
                )
                continue

        if ctx.stage == PipelineStage.ERROR:
            sys.exit(1)

    except UsageError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(2)
    except ConfigError as e:
        console.print(f"[red]Config error: {e}[/red]")
        sys.exit(1)
    except AuthError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except BotDetectionError as e:
        console.print("[red]YouTube bot detection — browser cookies required.[/red]")
        console.print(f"[dim]{e}[/dim]")
        sys.exit(1)
    except (VkApiError, DownloadError) as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)
    except Exception:
        console.print_exception()
        sys.exit(1)


def _print_usage() -> None:
    print("vk_uploader — upload YouTube videos to VK")
    print()
    print("Usage: vk_uploader <youtube_url> [key=value ...]")
    print()
    print("Supported options:")
    print("  ylink=<url>              YouTube video URL (alternative to positional)")
    print("  thumbnail=true|false     Enable/disable YouTube thumbnail upload")
    print("  publish_delay_hours=<n>  Hours to delay video publication (default: 24)")
    print("  output_dir=<path>        Download directory (default: ~/Downloads)")
    print("  video_format=<fmt>       yt-dlp format string (default: bv*+ba[ext=m4a]/bv*+ba/b)")
    print("  token=<str>              VK access token (override config)")
    print("  group_id=<str>           VK group/community ID")
    print("  wallpost=true|false      Publish to community wall (default: false)")
    print("  translation=true|false   Translate title/description (default: false)")
    print("  subtitles=true|false     Download and translate subtitles (default: false)")
    print("  lang=<code>              Target language for translation/subtitles (default: ru)")
    print("  album=true|<name>        Add video to album (interactive or by name)")
    print("  title=<str>              Video title (default: from YouTube)")
    print("  description=<str>        Video description (default: from YouTube)")
    print()
    print("Config file: ~/.config/vk_uploader/config.yaml")
    print()
    print("Supported browsers for cookies (yt-dlp --cookies-from-browser):")
    print("  firefox, chrome, chromium, brave, edge, opera, vivaldi")
    print()
    print("Use cookies_from_browser=<browser> to avoid YouTube bot detection.")


_BROWSER_DIRS: dict[str, list[str]] = {
    "firefox": ["~/.mozilla/firefox", "~/.config/mozilla/firefox"],
    "chrome": ["~/.config/google-chrome"],
    "chromium": ["~/.config/chromium", "~/snap/chromium/common/chromium"],
    "brave": ["~/.config/Brave-Browser"],
    "edge": ["~/.config/microsoft-edge"],
    "opera": ["~/.config/opera"],
    "vivaldi": ["~/.config/vivaldi"],
}


def _detect_browsers() -> list[str]:
    """Return a list of browser names that appear to be installed."""
    found: list[str] = []
    for name, path_patterns in _BROWSER_DIRS.items():
        for pattern in path_patterns:
            p = Path(pattern).expanduser()
            if p.is_dir():
                found.append(name)
                break
    return found


def _prompt_browser(console: Console) -> str | None:
    """Detect available browsers and ask the user which one to use for cookies.

    Returns the browser name (yt-dlp compatible), or None if cancelled.
    """
    available = _detect_browsers()

    console.print("\n[yellow]YouTube requires browser authentication.[/yellow]")
    console.print(
        "yt-dlp can use your browser cookies to prove you're not a bot."
    )

    if available:
        console.print(f"\nDetected browsers: [bold]{', '.join(available)}[/bold]")
        console.print(
            "[dim]Type a browser name (or press Enter for 'firefox'),"
            " or 'skip' to abort:[/dim]"
        )
    else:
        console.print(
            "\n[dim]No browsers auto-detected."
            " Supported: firefox, chrome, chromium, brave, edge, opera, vivaldi[/dim]"
        )
        console.print("[dim]Enter a browser name, or 'skip' to abort:[/dim]")

    # Default to the first detected browser, or firefox.
    default = available[0] if available else "firefox"

    try:
        choice = input(f"Browser [{default}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None

    if choice in ("skip", "no", "none", "q", ""):
        # Empty input with no available browsers means skip.
        if choice == "" and available:
            return default
        if choice == "":
            return None
        return None

    if choice == "":
        return default

    # Validate: must be one of the known browser names.
    if choice in _BROWSER_DIRS:
        return choice

    console.print(f"[red]Unknown browser: {choice!r}."
                  f" Supported: {', '.join(sorted(_BROWSER_DIRS))}[/red]")
    return None
