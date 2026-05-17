"""CLI argument parsing and main entry point."""

from __future__ import annotations

import sys

from vk_uploader.config import ConfigFile
from vk_uploader.logging_setup import create_console
from vk_uploader.models import DownloadError, JobContext, PipelineStage, UsageError
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

        # --- Merge CLI overrides onto config ---
        if "thumbnail" in overrides:
            config.defaults.thumbnail = _parse_bool(overrides["thumbnail"], "thumbnail")
        if "publish_delay_hours" in overrides:
            try:
                config.defaults.publish_delay_hours = int(overrides["publish_delay_hours"])
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
            config.defaults.wallpost = _parse_bool(overrides["wallpost"], "wallpost")
        if "video_format" in overrides:
            config.download.video_format = overrides["video_format"]

        title_override = overrides.get("title")
        description_override = overrides.get("description")

        # --- Validate ---
        token = config.vk.access_token.strip()
        if not token:
            from vk_uploader.auth import ensure_token
            ensure_token(console, config_file, config)
            config = config_file.load()  # reload after auth
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
        )

        # --- Run pipeline ---
        run_pipeline(console, ctx, config)

        if ctx.stage == PipelineStage.ERROR:
            sys.exit(1)

    except UsageError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(2)
    except (VkApiError, DownloadError) as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)
    except Exception:
        console.print_exception()
        sys.exit(1)


def _parse_bool(value: str, name: str) -> bool:
    v = value.lower()
    if v in ("true", "1", "yes", "on"):
        return True
    if v in ("false", "0", "no", "off"):
        return False
    raise UsageError(f"{name} must be true or false, got: {value!r}")


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
    print("  video_format=<fmt>       yt-dlp format string (default: bv*+ba/b)")
    print("  token=<str>              VK access token (override config)")
    print("  group_id=<str>           VK group/community ID")
    print("  wallpost=true|false      Publish to community wall (default: false)")
    print("  title=<str>              Video title (default: from YouTube)")
    print("  description=<str>        Video description (default: from YouTube)")
    print()
    print("Config file: ~/.config/vk_uploader/config.yaml")
