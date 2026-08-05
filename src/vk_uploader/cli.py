"""CLI argument parsing and main entry point."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from vk_uploader.config import ConfigFile, normalize_path
from vk_uploader.logging_setup import create_console
from vk_uploader.models import (
    AppConfig,
    AuthError,
    BotDetectionError,
    ConfigError,
    DefaultsConfig,
    DownloadConfig,
    DownloadError,
    JobContext,
    PipelineStage,
    UsageError,
    VkConfig,
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
    "links_file",
    "cleanup_after_upload",
})

_OVERRIDE_ALIASES = {
    "cleanup": "cleanup_after_upload",
}


def parse_args(argv: list[str]) -> tuple[str, dict[str, str]]:
    """Parse CLI args into (youtube_url, overrides_dict).

    Supports:
      vk_uploader <youtube_url> [key=value ...]
      vk_uploader ylink=<youtube_url> [key=value ...]
      vk_uploader links_file=<path> [key=value ...]

    When links_file is present, url may be empty string (URLs come from file).
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
            key = _normalize_override_key(key.strip().lower())
            value = value.strip()
            if not key:
                raise UsageError(f"Invalid argument: {arg!r}")
            if key == "links_file" and not value:
                raise UsageError("links_file must not be empty.")
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

    if "links_file" in overrides and url is not None:
        raise UsageError("links_file cannot be combined with a YouTube URL or ylink=...")

    if url is None and "links_file" not in overrides:
        raise UsageError(
            "YouTube URL is required.\nUsage: vk_uploader <youtube_url> [key=value ...]"
        )

    return url or "", overrides


def main() -> None:
    console = create_console()

    try:
        args = sys.argv[1:]
        if not args:
            _print_usage()
            sys.exit(0)

        # --- Dispatch: setup command ---
        if args[0] == "setup":
            cmd_setup(console)
            return

        url, overrides = parse_args(args)

        # ── Batch mode: links_file=<path> ──
        links_file = overrides.pop("links_file", None)
        if links_file is not None:
            _batch_main(console, links_file, overrides)
            return

        config_file = ConfigFile()
        config = config_file.load()

        # --- Auth (may reload config; one-shot token= must not be persisted) ---
        from vk_uploader.auth import ensure_token

        if "token" not in overrides:
            old_token = config.vk.access_token
            ensure_token(
                console,
                config_file,
                config,
                require_group="group_id" not in overrides,
            )
            # Only reload if the token was changed (avoids wiping CLI overrides).
            if config.vk.access_token != old_token:
                config = config_file.load()

        # --- Merge CLI overrides onto config (after potential reload) ---
        _apply_overrides(config, overrides)
        title_override = overrides.get("title")
        description_override = overrides.get("description")
        album_spec = overrides.get("album")

        # --- Validate ---
        _validate_config(console, config)

        output_dir = config_file.resolve_output_dir(config)

        # --- Build JobContext ---
        ctx = JobContext(
            youtube_url=url,
            output_dir=output_dir,
            group_id=config.vk.group_id,
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


# ── setup command ────────────────────────────────────────────────────────────


def cmd_setup(console: Console) -> None:
    """Interactive configuration wizard.

    Checks all required config values, prompts for missing ones,
    validates the token against VK API, and prints a summary.
    """
    from vk_uploader.auth import ensure_token

    config_file = ConfigFile()
    config = config_file.load()

    console.print()
    console.print("[bold]── VK Uploader Setup ──[/bold]")
    console.print()

    # Fill in missing auth values (app_id, token, group_id).
    ensure_token(console, config_file, config)

    # Reload to get the latest saved state.
    config = config_file.load()

    # Verify token.
    console.print()
    console.print("[dim]Verifying token...[/dim]", end=" ")
    from vk_uploader.auth import _verify_token
    if _verify_token(config.vk.access_token):
        console.print("[green]✓[/green]")
    else:
        console.print("[red]✗ (token invalid — re-run setup)[/red]")
        sys.exit(1)

    _configure_output_dir(console, config_file, config)

    # --- Browser cookies (optional, helps avoid YouTube bot detection) ---
    if not config.defaults.cookies_from_browser:
        console.print()
        available = _detect_browsers()
        if available:
            console.print(
                f"[dim]Detected browsers: [bold]{', '.join(available)}[/bold][/dim]"
            )
            console.print(
                "[dim]Set cookies_from_browser to avoid YouTube bot detection.[/dim]"
            )
            choice = console.input(
                f"Browser name (or Enter to skip) [{available[0]}]: "
            ).strip().lower()
            if not choice:
                pass  # skip
            elif choice in _BROWSER_DIRS:
                config.defaults.cookies_from_browser = choice
                config_file.save(config)
                console.print(f"[green]cookies_from_browser={choice} saved.[/green]")
            else:
                console.print(f"[yellow]Unknown browser '{choice}' — skipped.[/yellow]")
        else:
            console.print(
                "[dim]No browsers detected. Set cookies_from_browser=<name> to avoid"
                " YouTube bot detection.[/dim]"
            )

    # ── Print summary ──
    console.print()
    console.print("[bold]Configuration summary:[/bold]")
    console.print()

    table = Table(show_header=False, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()

    def _row(label: str, value: str) -> None:
        table.add_row(label, value)

    _row("App ID", config.vk.app_id or "[red](not set)[/red]")
    token_display = (
        config.vk.access_token[:12] + "..."
        if config.vk.access_token
        else "[red](not set)[/red]"
    )
    token_value = f"[green]{token_display}[/green]" if config.vk.access_token else token_display
    _row("Token", token_value)
    _row("Group ID", config.vk.group_id or "[red](not set)[/red]")
    _row("Expires", config.vk.expires_at or "(never)")
    _row("User ID", config.vk.user_id or "(unknown)")
    console.print(table)

    console.print()
    console.print("[dim]Defaults:[/dim]")
    table2 = Table(show_header=False, padding=(0, 2))
    table2.add_column(style="dim")
    table2.add_column()
    table2.add_row("Output dir", config.download.output_dir)
    table2.add_row("Publish delay", f"{config.defaults.publish_delay_hours}h")
    table2.add_row(
        "Thumbnail",
        "[green]on[/green]" if config.defaults.thumbnail else "[dim]off[/dim]",
    )
    table2.add_row(
        "Wall post",
        "[green]on[/green]" if config.defaults.wallpost else "[dim]off[/dim]",
    )
    table2.add_row(
        "Subtitles",
        (
            f"[green]on[/green] → {config.defaults.lang}"
            if config.defaults.subtitles
            else "[dim]off[/dim]"
        ),
    )
    table2.add_row(
        "Translation",
        (
            f"[green]on[/green] → {config.defaults.lang}"
            if config.defaults.translation
            else "[dim]off[/dim]"
        ),
    )
    table2.add_row("Language", config.defaults.lang or "(not set)")
    table2.add_row("Cookies", config.defaults.cookies_from_browser or "(none)")
    table2.add_row(
        "Cleanup",
        "[green]on[/green]" if config.defaults.cleanup_after_upload else "[dim]off[/dim]",
    )
    console.print(table2)

    console.print()
    console.print(f"[dim]Config file: {config_file.path}[/dim]")
    console.print()
    console.print("[green]Setup complete. Run: vk_uploader <youtube_url> [key=value ...][/green]")


# ── helpers ───────────────────────────────────────────────────────────────────


def _configure_output_dir(
    console: Console, config_file: ConfigFile, config: AppConfig
) -> None:
    """Prompt for the download directory and persist it in config."""
    current = config.download.output_dir.strip() or "~/Downloads"

    console.print()
    raw_value = console.input(f"Download directory [{current}]: ").strip()
    output_dir = str(normalize_path(raw_value or current))

    if output_dir != config.download.output_dir:
        config.download.output_dir = output_dir

    config_file.save(config)


def _apply_overrides(config: AppConfig, overrides: dict[str, str]) -> None:
    """Merge CLI key=value overrides onto config in-place."""
    if "thumbnail" in overrides:
        config.defaults.thumbnail = parse_bool(overrides["thumbnail"], "thumbnail")
    if "publish_delay_hours" in overrides:
        try:
            val = int(overrides["publish_delay_hours"])
            if val < 0:
                raise UsageError(f"publish_delay_hours must be >= 0, got: {val}")
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
    if "cleanup_after_upload" in overrides:
        config.defaults.cleanup_after_upload = parse_bool(
            overrides["cleanup_after_upload"], "cleanup_after_upload"
        )


def _validate_config(console: Console, config: AppConfig) -> None:
    """Validate required config values; print error and exit if missing."""
    errors = _check_config(config)
    if errors:
        for msg in errors:
            console.print(f"[red]{msg}[/red]")
        sys.exit(1)


def _check_config(config: AppConfig) -> list[str]:
    """Validate config; return list of error messages (empty if valid)."""
    errors: list[str] = []
    token = config.vk.access_token.strip()
    if not token:
        errors.append("VK access token is required.")
        errors.append("Run vk_uploader setup to configure.")

    group_id = config.vk.group_id.strip()
    if not group_id:
        errors.append("VK Group ID is required.")
        errors.append("Run vk_uploader setup to configure.")

    if config.defaults.subtitles or config.defaults.translation:
        lang = config.defaults.lang.strip()
        if not lang:
            errors.append(
                "lang is required when subtitles=true or translation=true."
            )
            errors.append(
                "Pass lang=<code> to specify the target language"
                " (e.g. lang=ru, lang=en)."
            )
    return errors


# ── usage ─────────────────────────────────────────────────────────────────────


def _print_usage() -> None:
    print("vk_uploader — upload YouTube videos to VK")
    print()
    print("Usage:")
    print("  vk_uploader setup               Interactive configuration wizard")
    print("  vk_uploader <youtube_url> [key=value ...]")
    print("  vk_uploader links_file=<path> [key=value ...]")
    print()
    print("Batch mode (links_file):")
    print("  Upload multiple videos from a text file, one URL per line.")
    print("  Per-line overrides use the same key=value syntax.")
    print("  Precedence: config.yaml < command-level overrides < line-level overrides.")
    print()
    print("  File format:")
    print("    <youtube_url> [key=value ...]")
    print("    ylink=<youtube_url> [key=value ...]")
    print("    # comments")
    print()
    print("  Example links.txt:")
    print("    https://www.youtube.com/watch?v=DsLQptIzUuM subtitles=true")
    print("    https://www.youtube.com/watch?v=1f5gEQHy2cg wallpost=true")
    print("    ylink=https://www.youtube.com/watch?v=abc title=\"Custom Title\"")
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
    print("  lang=<code>              Target language for translation/subtitles")
    print("  album=true|<name>        Add video to album (interactive or by name)")
    print("  title=<str>              Video title (default: from YouTube)")
    print("  description=<str>        Video description (default: from YouTube)")
    print(
        "  cleanup_after_upload=true|false"
        "  Remove local files after successful upload (default: false)"
    )
    print()
    print("Config file: ~/.config/vk_uploader/config.yaml")
    print()
    print("Supported browsers for cookies (yt-dlp --cookies-from-browser):")
    print("  firefox, chrome, chromium, brave, edge, opera, vivaldi")
    print()
    print("Use cookies_from_browser=<browser> to avoid YouTube bot detection.")


# ── batch mode ────────────────────────────────────────────────────────────────


def parse_links_file(path: str) -> list[tuple[int, str, dict[str, str]]]:
    """Parse a links file. Returns list of (line_number, url, overrides).

    Raises UsageError on malformed lines.
    """
    jobs: list[tuple[int, str, dict[str, str]]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line_num, raw in enumerate(f, 1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                url, overrides = _parse_line_args(line, path, line_num)
                jobs.append((line_num, url, overrides))
    except OSError as e:
        raise UsageError(f"{path}: cannot read links file: {e.strerror}") from e
    if not jobs:
        raise UsageError(f"{path}: no valid job lines found")
    return jobs


def _parse_line_args(
    line: str, path: str, line_num: int
) -> tuple[str, dict[str, str]]:
    """Parse a single line from a links file.

    Uses shlex for shell-like quoting (title="My Video", etc.).
    Same semantics as parse_args() for key=value handling.
    """
    try:
        tokens = shlex.split(line)
    except ValueError as e:
        raise UsageError(f"{path}:{line_num}: invalid quoting: {e}") from e

    url: str | None = None
    overrides: dict[str, str] = {}

    for token in tokens:
        if "=" not in token:
            if url is not None:
                raise UsageError(
                    f"{path}:{line_num}: only one YouTube URL per line"
                )
            url = token
            continue

        key, _, value = token.partition("=")
        # URL with query string (contains :// → not a key=value override).
        if "://" in key:
            if url is not None:
                raise UsageError(
                    f"{path}:{line_num}: only one YouTube URL per line"
                )
            url = token
            continue

        key = _normalize_override_key(key.strip().lower())
        value = value.strip()
        if not key:
            raise UsageError(
                f"{path}:{line_num}: invalid argument: {token!r}"
            )
        if key == "ylink":
            if url is not None:
                raise UsageError(
                    f"{path}:{line_num}: URL specified both"
                    " positionally and as ylink=..."
                )
            url = value
        elif key in _VALID_OVERRIDES:
            overrides[key] = value
        else:
            raise UsageError(
                f"{path}:{line_num}: unknown option: {key!r}"
            )

    if url is None:
        raise UsageError(f"{path}:{line_num}: YouTube URL is required")

    return url, overrides


def _normalize_override_key(key: str) -> str:
    """Return the canonical override key for CLI aliases."""
    return _OVERRIDE_ALIASES.get(key, key)


def _copy_config(config: AppConfig) -> AppConfig:
    """Deep-copy AppConfig for per-line isolation in batch mode."""
    return AppConfig(
        vk=VkConfig(
            access_token=config.vk.access_token,
            group_id=config.vk.group_id,
            app_id=config.vk.app_id,
            expires_at=config.vk.expires_at,
            user_id=config.vk.user_id,
        ),
        defaults=DefaultsConfig(
            publish_delay_hours=config.defaults.publish_delay_hours,
            thumbnail=config.defaults.thumbnail,
            wallpost=config.defaults.wallpost,
            translation=config.defaults.translation,
            subtitles=config.defaults.subtitles,
            lang=config.defaults.lang,
            cookies_from_browser=config.defaults.cookies_from_browser,
            cleanup_after_upload=config.defaults.cleanup_after_upload,
        ),
        download=DownloadConfig(
            output_dir=config.download.output_dir,
            video_format=config.download.video_format,
        ),
    )


def _batch_main(
    console: Console,
    links_file: str,
    global_overrides: dict[str, str],
) -> None:
    """Process multiple upload jobs from a links file."""
    from vk_uploader.auth import ensure_token

    # Parse before auth so file/format errors fail quickly without prompting.
    jobs = parse_links_file(links_file)

    config_file = ConfigFile()
    config = config_file.load()

    batch_supplies_token = "token" in global_overrides or all(
        "token" in overrides for _, _, overrides in jobs
    )
    batch_supplies_group = "group_id" in global_overrides or all(
        "group_id" in overrides for _, _, overrides in jobs
    )

    # ── Auth (once for all jobs; one-shot token= must not be persisted) ──
    if not batch_supplies_token:
        old_token = config.vk.access_token
        ensure_token(
            console,
            config_file,
            config,
            require_group=not batch_supplies_group,
        )
        if config.vk.access_token != old_token:
            config = config_file.load()

    # ── Apply command-level overrides to base config ──
    _apply_overrides(config, global_overrides)

    # ── Process jobs sequentially ──
    succeeded: list[tuple[int, str]] = []
    failed: list[tuple[int, str, str]] = []

    total = len(jobs)

    for idx, (line_num, url, line_overrides) in enumerate(jobs, 1):
        console.print(
            f"\n[bold]── Job {idx}/{total} (line {line_num}) ──[/bold]"
        )
        console.print(f"  URL: [dim]{url}[/dim]")

        # Isolate config: copy base (with global overrides), then apply line overrides.
        job_config = _copy_config(config)
        _apply_overrides(job_config, line_overrides)

        # Validate
        errors = _check_config(job_config)
        if errors:
            console.print(f"[red]  Config error: {errors[0]}[/red]")
            failed.append((line_num, url, errors[0]))
            continue

        title_override = line_overrides.get("title", global_overrides.get("title"))
        description_override = line_overrides.get(
            "description", global_overrides.get("description")
        )
        album_spec = line_overrides.get("album", global_overrides.get("album"))

        output_dir = config_file.resolve_output_dir(job_config)

        ctx = JobContext(
            youtube_url=url,
            output_dir=output_dir,
            group_id=job_config.vk.group_id,
            publish_delay_hours=job_config.defaults.publish_delay_hours,
            thumbnail_enabled=job_config.defaults.thumbnail,
            wallpost=job_config.defaults.wallpost,
            title_override=title_override,
            description_override=description_override,
            album_spec=album_spec,
        )

        # ── Run pipeline with bot-detection retry ──
        while True:
            try:
                run_pipeline(console, ctx, job_config)
                break
            except BotDetectionError:
                if job_config.defaults.cookies_from_browser:
                    raise
                browser = _prompt_browser(console)
                if browser is None:
                    raise
                job_config.defaults.cookies_from_browser = browser
                config.defaults.cookies_from_browser = browser
                config_file.save(config)
                console.print(
                    f"[green]Saved cookies_from_browser={browser}"
                    f" to config. Retrying...[/green]"
                )
                continue

        if ctx.stage == PipelineStage.ERROR:
            failed.append(
                (line_num, url, ctx.error_message or "unknown error")
            )
        else:
            succeeded.append((line_num, url))

    # ── Batch summary ──
    console.print()
    console.print("[bold]══ Batch Summary ══[/bold]")
    console.print(
        f"  Total:   {total}\n"
        f"  Success: [green]{len(succeeded)}[/green]\n"
        f"  Failed:  [red]{len(failed)}[/red]"
    )

    if failed:
        console.print("\n[bold red]Failed jobs:[/bold red]")
        for line_num, url, reason in failed:
            console.print(f"  Line {line_num}: [dim]{url}[/dim] — {reason}")
        sys.exit(1)


# ── browser helpers ───────────────────────────────────────────────────────────


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
