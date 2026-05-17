# Changelog

All notable changes to vk_uploader.

## [Unreleased]

### Added
- Translation feature: translate video title and description via Google Translate
  (`deep-translator`, no API key required). Config fields: `translation` (bool),
  `lang` (str, default `ru`). CLI: `translation=true lang=de`.

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

[0.0.1]: https://github.com/NickASanOS/vk_video_uploader_py/releases/tag/v0.0.1
