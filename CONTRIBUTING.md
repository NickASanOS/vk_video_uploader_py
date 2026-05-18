# Contributing

Contributions are welcome. All changes go through Pull Requests — direct
pushes to `main` are blocked.

## Development setup

```bash
# Fork the repository on GitHub, then clone your fork
git clone git@github.com:YOUR_USERNAME/vk_video_uploader_py.git
cd vk_video_uploader_py
make install-dev
```

## Workflow

```bash
# 1. Create a feature branch
git checkout -b feature/my-change

# 2. Make changes, write tests

# 3. Run full checks
make check

# 4. Commit and push to YOUR fork
git add -A
git commit -m "Add: short description"
git push -u origin feature/my-change

# 5. Open a Pull Request on GitHub from your branch to NickASanOS/main
```

## Guidelines

- Python 3.11+. Match the existing style (`ruff check` must pass).
- Type annotations required (`mypy src/` must pass).
- Tests for new functionality (`pytest tests/` must pass).
- Keep the PR focused. One feature or fix per PR.
- The maintainer reviews and merges. Feedback may be given via review comments.

## Project structure

```
src/vk_uploader/
├── cli.py              # CLI parsing + entry point
├── config.py           # YAML config load/save
├── models.py           # Dataclasses, enums, exceptions
├── auth.py             # VK OAuth2 Implicit Flow
├── vk_api.py           # VK API client
├── ytdlp_downloader.py # yt-dlp wrapper (standalone binary)
├── thumbnail.py        # Thumbnail download helper
├── translate.py        # Translation via deep-translator
├── pipeline.py         # Download → translate → upload orchestration
└── logging_setup.py    # Rich console setup

tests/
├── test_auth.py
├── test_cli.py
├── test_config.py
├── test_thumbnail.py
├── test_translate.py
├── test_vk_api.py
└── test_ytdlp_downloader.py
```

## Commands

| Command | Purpose |
|---------|---------|
| `make check` | Run lint + typecheck + tests |
| `make test` | Run tests only |
| `make lint` | Run ruff only |
| `make lint-fix` | Auto-fix lint issues |
| `make typecheck` | Run mypy only |
