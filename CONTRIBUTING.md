# Contributing

## Setup

```bash
git clone git@github.com:NickASanOS/vk_video_uploader_py.git
cd vk_video_uploader_py
make install-dev
```

## Development workflow

| Command | What it does |
|---------|-------------|
| `make test` | Run tests (`pytest -v`) |
| `make lint` | Check code style (`ruff`) |
| `make lint-fix` | Auto-fix lint issues (`ruff --fix`) |
| `make typecheck` | Run type checking (`mypy`) |
| `make check` | Run all three: lint, typecheck, test |
| `make clean` | Remove virtualenv and caches |

Run `make check` before pushing.

## Project structure

```
src/vk_uploader/
├── cli.py              # CLI parsing + entry point
├── config.py           # YAML config load/save
├── models.py           # Dataclasses, enums, exceptions
├── auth.py             # VK OAuth2 Implicit Flow
├── vk_api.py           # VK API client
├── ytdlp_downloader.py # yt-dlp wrapper
├── thumbnail.py        # Thumbnail download helper
├── pipeline.py         # Download → upload orchestration
└── logging_setup.py    # Rich console setup
```

## CI

CI runs on every push to `main` and every pull request:
- **lint**: `ruff check src/ tests/`
- **typecheck**: `mypy src/`
- **test**: `pytest tests/` on Python 3.11, 3.12, 3.13
