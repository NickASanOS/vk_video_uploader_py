# vk_uploader

CLI tool to download YouTube videos and upload them to VK with delayed publishing.

## Requirements

- **Linux** (primary supported platform)
- **Python 3.11+**
- **yt-dlp** — standalone binary, required. [Install](https://github.com/yt-dlp/yt-dlp#installation)
- **ffmpeg** 7.x+ — for video/audio merging. System or [static build](https://github.com/BtbN/FFmpeg-Builds)
- **deno** (optional) — enables all YouTube formats via EJS challenge solver
- **VK App** with `video` scope ([create one](https://vk.com/editapp))
- **VK Community** (group) to upload videos to

### Install dependencies

```bash
# yt-dlp (standalone binary)
curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
  -o ~/.local/bin/yt-dlp && chmod +x ~/.local/bin/yt-dlp

# ffmpeg 7.x (static build from BtbN, recommended for 4K AV1 support)
mkdir -p ~/ffmpeg && cd ~/ffmpeg
wget https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linux64-gpl.tar.xz
tar xf ffmpeg-master-latest-linux64-gpl.tar.xz
# vk_uploader auto-detects ~/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg

# deno (optional, for better YouTube format availability)
curl -fsSL https://deno.land/install.sh | sh
# Ensure ~/.deno/bin is in your PATH
```

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

To make it available system-wide:

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
| `translation=` | bool | `false` | Translate title/description |
| `lang=` | str | `ru` | Target language for translation |
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
  translation: false
  lang: ru

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
