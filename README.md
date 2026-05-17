# vk_uploader

Upload YouTube videos to VK with optional delayed publication.

## Install

```bash
pip install -e .
```

Requires Python 3.11+.

## Quick start

```bash
# First run — configure VK credentials via OAuth
vk_uploader https://www.youtube.com/watch?v=EXAMPLE

# Override config values via CLI
vk_uploader https://www.youtube.com/watch?v=EXAMPLE thumbnail=false publish_delay_hours=48

# Use ylink= syntax
vk_uploader ylink=https://www.youtube.com/watch?v=EXAMPLE output_dir=/tmp/videos
```

## Config

Config file is stored at `~/.config/vk_uploader/config.yaml`:

```yaml
vk:
  access_token: "..."
  group_id: "123456789"
  app_id: "987654321"
  expires_at: "2026-12-31T00:00:00"
  user_id: "111"

defaults:
  publish_delay_hours: 24
  thumbnail: true
  wallpost: false

download:
  output_dir: "~/Downloads"
  video_format: "bv*+ba/b"
```

## CLI options

| Option | Description | Default |
|--------|-------------|---------|
| `ylink=` | YouTube URL (alternative to positional) | — |
| `thumbnail=` | Enable thumbnail upload (`true`/`false`) | `true` |
| `publish_delay_hours=` | Hours to delay publication | `24` |
| `output_dir=` | Download directory | `~/Downloads` |
| `video_format=` | yt-dlp format string | `bv*+ba/b` |
| `token=` | VK access token (override config) | — |
| `group_id=` | VK group/community ID | — |
| `wallpost=` | Publish to community wall | `false` |
| `title=` | Video title (default: from YouTube) | — |
| `description=` | Video description (default: from YouTube) | — |

## Dev

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Tests
pytest tests/ -v

# Lint
ruff check src/ tests/

# Type check
mypy src/
```
