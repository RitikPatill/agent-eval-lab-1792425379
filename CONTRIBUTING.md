# Contributing

## Prerequisites

- Python 3.11+
- `make`

## Setup

```bash
git clone https://github.com/your-org/agent-eval-lab && cd agent-eval-lab
make dev    # installs dev deps (pip install -e ".[dev]") + pre-commit hooks
```

## Running tests

```bash
make test          # pytest
make lint          # ruff check + autofix
make typecheck     # mypy strict
```

All three must pass before opening a PR.

## Pre-commit hooks

Installed automatically by `make dev`. Runs `ruff` and `mypy` on every commit. To bypass for a quick experiment:

```bash
git commit --no-verify
```

Do not bypass on commits intended for review.

## Project layout

```
src/agent_eval_lab/   — main package (see ARCHITECTURE.md for per-file roles)
examples/             — LangGraph customer-support agent (v1 + v2)
tests/                — pytest suite
data/                 — sample YAML suites and rubrics
docs/                 — demo.gif, screenshot.png, demo.tape
scripts/              — seed.py (idempotent DB seeder)
```

## Adding a new adapter

Adapters live in `src/agent_eval_lab/adapters.py`. Implement the `Adapter` protocol:

```python
class MyAdapter:
    def __init__(self, config: dict) -> None:
        ...

    def __call__(self, input_json: dict) -> AgentOutput:
        ...
```

Then register an agent version via `POST /agents` with `adapter_type` matching your class name (e.g. `"MyAdapter"`). The runner resolves adapter classes by name from the module.

## Adding a new scorer

Scorers live in `src/agent_eval_lab/scorers.py`. Add a class with a `score` method:

```python
class MyScorer:
    def score(self, case_result: CaseResult, criterion: dict) -> Score:
        ...
```

Wire it into the scorer dispatch dict in `src/agent_eval_lab/runner.py`:

```python
SCORER_REGISTRY = {
    "llm_judge": JudgeScorer,
    "deterministic": DeterministicScorer,
    "my_scorer": MyScorer,   # ← add here
}
```

## PR checklist

- [ ] Tests pass (`make test`)
- [ ] Lint clean (`make lint`)
- [ ] Type-check clean (`make typecheck`)
- [ ] Added/updated tests for new behaviour
- [ ] Updated relevant docs if the change affects the adapter or scorer contracts
