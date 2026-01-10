
check:
	uv run ruff format .
	uv run ruff check . --fix --unsafe-fixes
	uv run mypy src --explicit-package-bases