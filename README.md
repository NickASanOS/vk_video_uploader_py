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
- **Download directory** — where video, thumbnail, and subtitle files are saved (`~/Downloads` by default)
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
| `video_format=` | str | `bv*+ba[ext=m4a]/bv*+ba/b` | yt-dlp format string |
| `token=` | str | — | VK access token (one-run override; not saved to config) |
| `group_id=` | str | — | VK community ID (override config) |
| `wallpost=` | bool | `false` | Publish to community wall |
| `translation=` | bool | `false` | Translate title/description |
| `lang=` | str | — | Target language — **required** when `translation=true` or `subtitles=true` |
| `subtitles=` | bool | `false` | Download and translate subtitles (saved locally, not uploaded to VK) |
| `album=` | str | — | Add video to album: `true` (interactive) or album name |
| `cookies_from_browser=` | str | — | Browser to extract cookies from (firefox, chrome, ...) |
| `title=` | str | — | Video title (default: from YouTube) |
| `description=` | str | — | Video description (default: from YouTube) |
| `cleanup_after_upload=` | bool | `false` | Remove local video file after successful upload |

If `translation=true` or `subtitles=true` is set, `lang=<code>` must also be provided
(e.g. `lang=ru`, `lang=en`). The tool will exit with an error if `lang` is missing.

Subtitles are downloaded as `.srt` files. The downloader asks yt-dlp for the target
language first and English as a fallback; if the best available subtitle is not in
the target language, it is translated locally to `lang=<code>`.
Subtitles are **not uploaded to VK** (VK API does not support SRT subtitle upload).

## Batch uploads

Upload multiple videos from a text file using `links_file=<path>`:

```bash
vk_uploader links_file=/path/to/links.txt
vk_uploader links_file=/path/to/links.txt publish_delay_hours=48 thumbnail=false
```

### File format

One job per line. Same `key=value` syntax as CLI overrides:

```text
<youtube_url> [key=value ...]
ylink=<youtube_url> [key=value ...]
# comments
```

Example `links.txt`:

```text
https://www.youtube.com/watch?v=DsLQptIzUuM subtitles=true lang=ru
https://www.youtube.com/watch?v=1f5gEQHy2cg wallpost=true
ylink=https://www.youtube.com/watch?v=abc title="Custom Title"
# This is a comment
```

### Precedence

```
config.yaml < command-level overrides < line-level overrides
```

Options passed on the command line (e.g. `publish_delay_hours=48`) apply to all
jobs unless a line overrides them.

### Shell-like quoting

Values with spaces can be quoted:

```text
https://youtube.com/watch?v=abc title="My Video Title" description='A description'
```

### Parsing rules

- Blank lines are ignored.
- Lines starting with `#` are comments.
- Malformed lines are reported with file path and line number.
- The file must contain at least one valid job line.

### Behavior

- Config and VK auth are loaded once for all jobs.
- Each job gets an isolated config — per-line settings do not leak between jobs.
- Jobs are processed sequentially.
- A summary is printed at the end with succeeded/failed counts.
- Exit code is non-zero if any job fails.

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
  cleanup_after_upload: false  # remove local files after upload

download:
  output_dir: "~/Downloads"
  video_format: "bv*+ba[ext=m4a]/bv*+ba/b"
```

## CI

GitHub Actions runs on pushes and pull requests to `main`:

- `ruff check src/ tests/`
- `mypy src/`
- `pytest tests/ -v` on Python 3.11, 3.12, and 3.13

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
