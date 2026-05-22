# vk_uploader

CLI tool to download YouTube videos and upload them to VK with delayed publishing.

## Requirements

- **Linux** (primary supported platform)
- **Python 3.11+**
- **yt-dlp** — standalone binary, required. [Nightly builds](https://github.com/yt-dlp/yt-dlp-nightly-builds/releases)
- **ffmpeg** 7.x+ — for video/audio merging. System or [static build](https://github.com/BtbN/FFmpeg-Builds)
- **deno** (optional) — enables all YouTube formats via EJS challenge solver
- **VK App** with `video` scope ([create one](https://dev.vk.com/en/admin/create-app))
- **VK Community** (group) to upload videos to

### Install dependencies

```bash
# yt-dlp (nightly standalone binary)
curl -L https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp_linux \
  -o ~/.local/bin/yt-dlp && chmod +x ~/.local/bin/yt-dlp

# ffmpeg 7.x (static build from BtbN, recommended for 4K AV1 support)
wget https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linux64-gpl.tar.xz
tar xf ffmpeg-master-latest-linux64-gpl.tar.xz -C ~
rm ffmpeg-master-latest-linux64-gpl.tar.xz
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

Go to [dev.vk.com/en/admin/create-app](https://dev.vk.com/en/admin/create-app), create a **Standalone** application.  
Note your **App ID**.

### 2. Run setup wizard

```bash
vk_uploader setup
```

The wizard will guide you through:
- **App ID** — your VK application ID
- **OAuth authorization** — opens browser, you log in and paste the redirect URL
- **Group ID** — your VK community ID (find it in any post URL: `wall-123456789_...`)
- **Token verification** — validates the token against VK API
- **Browser cookies** (optional) — detects installed browsers, helps avoid YouTube bot detection

All values are saved to `~/.config/vk_uploader/config.yaml`.

### 3. Upload a video

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
| `lang=` | str | — | Target language — **required** when `translation=true` or `subtitles=true` |
| `subtitles=` | bool | `false` | Download and translate subtitles (saved locally, not uploaded to VK) |
| `album=` | str | — | Add video to album: `true` (interactive) or album name |
| `cookies_from_browser=` | str | — | Browser to extract cookies from (firefox, chrome, ...) |
| `title=` | str | — | Video title (default: from YouTube) |
| `description=` | str | — | Video description (default: from YouTube) |

If `translation=true` or `subtitles=true` is set, `lang=<code>` must also be provided
(e.g. `lang=ru`, `lang=en`). The tool will exit with an error if `lang` is missing.

Subtitles are downloaded as `.srt` files and translated to the target language,
but are **not uploaded to VK** (VK API does not support SRT subtitle upload).

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
  subtitles: false
  lang: ""           # required when translation or subtitles is true
  cookies_from_browser: ""  # e.g. "firefox", "chrome"

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
