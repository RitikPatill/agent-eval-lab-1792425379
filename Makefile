.PHONY: dev test lint typecheck demo

dev:
	pip install -e ".[dev]"
	pre-commit install

test:
	pytest -q

lint:
	ruff check . --fix

typecheck:
	mypy src/

demo:
	@echo "Demo coming in M7. Run 'make dev' first."
