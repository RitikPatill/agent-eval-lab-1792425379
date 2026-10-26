.PHONY: dev test lint typecheck demo ui record

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
	@test -n "$$ANTHROPIC_API_KEY" || (echo "Error: ANTHROPIC_API_KEY is not set." && exit 1)
	@echo "Installing dependencies..."
	pip install -e ".[examples]"
	@echo "Seeding database..."
	python scripts/seed.py
	@echo "Starting API server (port 8000) and Streamlit UI (port 8501)..."
	uvicorn agent_eval_lab.api:app --reload --port 8000 & echo $$! > /tmp/agent_eval_api.pid
	streamlit run src/agent_eval_lab/ui.py
	@kill $$(cat /tmp/agent_eval_api.pid) 2>/dev/null || true

record:
	bash record_demo.sh
