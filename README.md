# vk_uploader

CLI tool to download YouTube videos and upload them to VK with delayed publishing.

## Requirements

- **Linux** (primary supported platform)
- **Python 3.11+**
- **yt-dlp** (installed automatically as a dependency)
- **VK App** with `video` scope ([create one](https://vk.com/editapp))
- **VK Community** (group) to upload videos to

## Install

```bash
git clone git@github.com:NickASanOS/vk_video_uploader_py.git
cd vk_video_uploader_py
python3 -m venv .venv
.venv/bin/pip install .
```

After install, the `vk_uploader` command is available:

```bash
.venv/bin/vk_uploader --help
```

To make it available system-wide without activating the venv each time:

```bash
ln -s $(pwd)/.venv/bin/vk_uploader ~/.local/bin/vk_uploader
```

(Ensure `~/.local/bin` is in your `PATH`.)

## Quick start

### 1. Create VK App

Go to [vk.com/editapp](https://vk.com/editapp), create a **Standalone** application.  
Note your **App ID**.

### 2. First run — authorize

```bash
vk_uploader https://www.youtube.com/watch?v=YOUR_VIDEO
```

- Browser opens with VK authorization page
- Log in and allow access
- Copy the full URL from the address bar (`https://oauth.vk.com/blank.html#access_token=...`)
- Paste it into the terminal
- Token is saved to `~/.config/vk_uploader/config.yaml`

### 3. Next runs

Token is saved — no need to re-authorize. Just pass a YouTube URL:

```bash
vk_uploader https://www.youtube.com/watch?v=YOUR_VIDEO
```

## CLI options

All options can be set in config or overridden via `key=value` arguments:

```bash
vk_uploader <url> thumbnail=false publish_delay_hours=48 output_dir=/tmp/videos
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `ylink=` | URL | — | YouTube URL (alternative to positional) |
| `thumbnail=` | bool | `true` | Download and upload YouTube thumbnail |
| `publish_delay_hours=` | int | `24` | Hours to delay publication |
| `output_dir=` | path | `~/Downloads` | Download directory |
| `video_format=` | str | `bv*+ba/b` | yt-dlp format string |
| `token=` | str | — | VK access token (override config) |
| `group_id=` | str | — | VK community ID |
| `wallpost=` | bool | `false` | Publish to community wall |
| `title=` | str | — | Video title (default: from YouTube) |
| `description=` | str | — | Video description (default: from YouTube) |

## Config file

`~/.config/vk_uploader/config.yaml`:

```yaml
vk:
  access_token: "vk1.a..."
  group_id: "123456789"
  app_id: "987654321"
  expires_at: "2026-05-18T13:51:25"
  user_id: "111"

defaults:
  publish_delay_hours: 24
  thumbnail: true
  wallpost: false

download:
  output_dir: "~/Downloads"
  video_format: "bv*+ba/b"
```

## Development

```bash
# Setup
make install-dev

# Run checks
make check          # lint + typecheck + test
make test           # pytest only
make lint           # ruff only
make typecheck      # mypy only
make lint-fix       # auto-fix lint issues
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

MIT
