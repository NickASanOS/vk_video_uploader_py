# Changelog

All notable changes to vk_uploader.

## [0.0.2] — 2026-05-18

### Added
- Translation feature: Google Translate via `deep-translator` (no API key).
  Config: `translation` (bool), `lang` (str, default `ru`). CLI: `translation=true lang=de`.
- YouTube link appended to video description.
- Deno runtime support for yt-dlp EJS challenges.
- Custom ffmpeg detection: `~/ffmpeg-*/bin/ffmpeg` with priority over system ffmpeg.
- Progress bar shows merge/conversion stage instead of stuck at 100%.

### Changed
- Switched from pip yt-dlp library to standalone yt-dlp binary (`~/.local/bin/yt-dlp`).
- Default format now prefers M4A/AAC audio (`bv*+ba[ext=m4a]/bv*+ba/b`) for reliable MP4 merging.
- 54 tests (up from 46).

## [0.0.1] — 2026-05-17

### Added
- Download YouTube videos via yt-dlp as native Python library
- Upload videos to VK with delayed publication (configurable, default 24h)
- YouTube thumbnail download and upload to VK (`video.getThumbUploadUrl` / `video.saveUploadedThumb`)
- OAuth2 Implicit Flow authorization via `oauth.vk.com/blank.html`
- YAML config file at `~/.config/vk_uploader/config.yaml`
- CLI override support: `key=value` syntax for any config parameter
- Progress bars for both download (via Rich) and VK upload (via requests-toolbelt)
- Full CI pipeline: lint (ruff), typecheck (mypy), tests (pytest) on 3.11–3.13
- 46 unit and integration tests

[0.0.2]: https://github.com/NickASanOS/vk_video_uploader_py/releases/tag/v0.0.2
[0.0.1]: https://github.com/NickASanOS/vk_video_uploader_py/releases/tag/v0.0.1
