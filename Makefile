.PHONY: dev test lint typecheck demo ui

dev:
	pip install -e ".[dev]"
	pre-commit install

test:
	pytest -q

lint:
	ruff check . --fix

typecheck:
	mypy src/

ui:
	streamlit run src/agent_eval_lab/ui.py

demo:
	@echo "Installing example dependencies..."
	pip install -e ".[examples]"
	@echo "Seeding database..."
	python scripts/seed.py
	@echo "Starting API server and Streamlit UI..."
	uvicorn agent_eval_lab.api:app --reload --port 8000 &
	streamlit run src/agent_eval_lab/ui.py
