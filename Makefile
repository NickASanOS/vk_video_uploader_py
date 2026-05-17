.PHONY: install-dev test lint typecheck clean check release

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

install-dev: $(VENV)/bin/activate
	$(PIP) install -e ".[dev]" types-PyYAML

$(VENV)/bin/activate:
	python3 -m venv $(VENV)

test: install-dev
	$(PYTHON) -m pytest tests/ -v

lint: install-dev
	$(VENV)/bin/ruff check src/ tests/

lint-fix: install-dev
	$(VENV)/bin/ruff check src/ tests/ --fix

typecheck: install-dev
	$(VENV)/bin/mypy src/

check: lint typecheck test
	@echo "All checks passed."

clean:
	rm -rf $(VENV) .mypy_cache .pytest_cache .ruff_cache build/ dist/ *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

release: check
	@test -n "$(VER)" || (echo "Usage: make release VER=1.2.3" && exit 1)
	sed -i 's/^version = ".*"/version = "$(VER)"/' pyproject.toml
	sed -i 's/^__version__ = ".*"/__version__ = "$(VER)"/' src/vk_uploader/__init__.py
	git add pyproject.toml src/vk_uploader/__init__.py
	git commit -m "Release v$(VER)"
	git tag "v$(VER)"
	@echo "Release v$(VER) prepared. Run 'git push && git push --tags' to publish."
