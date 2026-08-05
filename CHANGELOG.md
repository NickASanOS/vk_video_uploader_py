# Changelog

All notable changes to vk_uploader.

## Unreleased

### Added
- Batch uploads via `links_file=<path>`, with one video job per line and
  command-level plus line-level overrides.
- `cleanup_after_upload=true|false` to remove local video and subtitle files
  after a successful upload.

### Fixed
- `token=` now works as a one-run CLI override without triggering OAuth or saving
  the token to config.
- `group_id=` CLI overrides now satisfy upload validation without prompting during
  token checks.
- Batch mode now honors command-level `token=` and `group_id=` overrides before
  auth prompts.
- VK token verification now reports network/API response failures explicitly
  instead of treating them as a valid token.
- Subtitle sidecar matching no longer picks up files from similarly prefixed
  videos.
- SRT batch translation now splits on the full internal separator, avoiding false
  splits on literal `[TSRT]` text.
- YouTube bot detection during the download subprocess now triggers the same
  browser-cookie retry path as metadata extraction.
- Cached video files no longer block subtitle download when subtitles are newly
  requested.
- Downloader output selection is now limited to files matching the current
  YouTube video id, avoiding accidental uploads of unrelated files from the output
  directory.
- Thumbnail fallback no longer starts with a non-existent language-suffixed
  YouTube maxres URL.
- yt-dlp environment setup now keeps common tool paths available when `PATH` is
  empty or missing.
- VK token verification now uses the shared VK API client/version instead of a
  separate hard-coded `users.get` request.
- Batch link files with invalid UTF-8 now fail with a clear usage error instead
  of a traceback.
- Thumbnail download retries no longer hide unexpected programming errors.
- Cached yt-dlp downloads are now detected across common video file extensions.

### Changed
- Subtitle download now requests the target language plus English fallback
  variants, allowing the pipeline to translate fallback subtitles to the target
  language when needed.
- Metadata translation failures now print a non-fatal warning while keeping the
  original title/description fallback.

## [0.0.7] — 2026-05-22

### Added
- Interactive `vk_uploader setup` wizard with token verification and browser-cookie setup.
- Runtime VK token validation before upload, with re-authorization for invalid or expired tokens.
- Required `lang` validation when translation or subtitles are enabled.

### Fixed
- Release checks now pass under ruff and strict mypy.

## [0.0.5] — 2026-05-20

### Added
- Subtitle download from YouTube (`subtitles` config option, CLI `subtitles=true|false`).
- SRT parsing, writing, and translation with batching (reuses existing `translate_text()`).
- Subtitle language selection: target (`lang`) > English > any available.
- `video_id` extraction from YouTube URL stored in `DownloadResult`.

### Changed
- Thumbnail: prioritized `img.youtube.com/vi/<id>/maxresdefault.jpg` over yt-dlp's
  language-suffixed URL (which can 404).
- Thumbnail download: fallback to yt-dlp URL if `img.youtube.com` fails.

### Fixed
- CLI overrides no longer wiped by `config = config_file.load()` after `ensure_token`.

## [0.0.4] — 2026-05-19

### Fixed
- Test `test_none_token_triggers_auth`: missing `input()` mock caused CI failure.

### Added
- Contributing guide, PR template, CODEOWNERS, branch protection rules.
- PyYAML type stubs for mypy (`types-PyYAML` in dev deps).

### Changed
- Upload pipeline: improved error handling and progress reporting.

## [0.0.3] — 2026-05-18

### Fixed
- OAuth now requests `video,wall` scopes — wall posting works again.
- YAML `null` access_token no longer becomes literal `"None"` string.
- AV1+MP4 merge failure (disabled `-movflags +faststart`).
- Cached video re-download: existing merged files are reused.
- Thumbnail errors no longer crash the pipeline (non-fatal, shown in summary).

### Added
- Final protocol/summary after each run (download, translation, upload, thumbnail, wall post).
- 56 tests (2 new: YAML null handling, token "None" validation).
- CI: Node.js 24 opt-in, no deprecation warnings.

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

[0.0.7]: https://github.com/NickASanOS/vk_video_uploader_py/releases/tag/v0.0.7
[0.0.6]: https://github.com/NickASanOS/vk_video_uploader_py/releases/tag/v0.0.6
[0.0.5]: https://github.com/NickASanOS/vk_video_uploader_py/releases/tag/v0.0.5
[0.0.4]: https://github.com/NickASanOS/vk_video_uploader_py/releases/tag/v0.0.4
[0.0.3]: https://github.com/NickASanOS/vk_video_uploader_py/releases/tag/v0.0.3
[0.0.2]: https://github.com/NickASanOS/vk_video_uploader_py/releases/tag/v0.0.2
[0.0.1]: https://github.com/NickASanOS/vk_video_uploader_py/releases/tag/v0.0.1
