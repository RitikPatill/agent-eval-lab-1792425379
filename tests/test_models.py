"""Unit tests for SQLModel entities — uses an in-memory SQLite DB."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from sqlmodel import Session, SQLModel, create_engine, select

from agent_eval_lab.models import (
    AgentVersion,
    CaseResult,
    EvalCase,
    Rubric,
    Run,
    Score,
    Suite,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_ENGINE = create_engine("sqlite:///:memory:")


@pytest.fixture(autouse=True)
def setup_db():
    SQLModel.metadata.create_all(TEST_ENGINE)
    yield
    SQLModel.metadata.drop_all(TEST_ENGINE)


@pytest.fixture()
def session():
    with Session(TEST_ENGINE) as s:
        yield s


# ---------------------------------------------------------------------------
# Helpers used by seed-idempotency test
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent.parent / "data"


def _load_suite(path: Path, session: Session) -> Suite:
    data = yaml.safe_load(path.read_text())
    meta = data["suite"]
    existing = session.exec(select(Suite).where(Suite.name == meta["name"])).first()
    if existing:
        return existing
    suite = Suite(name=meta["name"], description=meta.get("description", ""))
    session.add(suite)
    session.flush()
    for raw in data.get("cases", []):
        tc = EvalCase(
            suite_id=suite.id,  # type: ignore[arg-type]
            input_json=json.dumps(raw["input"]),
            expected_json=json.dumps(raw.get("expected", {})),
            tags=json.dumps(raw.get("tags", [])),
        )
        session.add(tc)
    return suite


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_create_suite(session: Session) -> None:
    suite = Suite(name="my_suite", description="test suite")
    session.add(suite)
    session.commit()

    result = session.exec(select(Suite).where(Suite.name == "my_suite")).one()
    assert result.name == "my_suite"
    assert result.description == "test suite"
    assert result.id is not None


def test_create_eval_case(session: Session) -> None:
    suite = Suite(name="suite_a")
    session.add(suite)
    session.flush()

    input_data = {"role": "user", "content": "Hello"}
    tc = EvalCase(
        suite_id=suite.id,  # type: ignore[arg-type]
        input_json=json.dumps(input_data),
        expected_json=json.dumps({"contains": ["hi"]}),
        tags=json.dumps(["greeting"]),
    )
    session.add(tc)
    session.commit()

    result = session.exec(select(EvalCase).where(EvalCase.suite_id == suite.id)).one()
    assert result.input == input_data
    assert result.tag_list == ["greeting"]


def test_create_rubric(session: Session) -> None:
    criteria = [{"name": "helpful", "guidance": "1=bad, 5=great"}]
    rubric = Rubric(name="rubric_v1", criteria_yaml=yaml.dump(criteria))
    session.add(rubric)
    session.commit()

    result = session.exec(select(Rubric).where(Rubric.name == "rubric_v1")).one()
    assert result.criteria_yaml == yaml.dump(criteria)
    assert result.criteria[0]["name"] == "helpful"


def test_run_lifecycle(session: Session) -> None:
    suite = Suite(name="s1")
    rubric = Rubric(name="r1", criteria_yaml="[]")
    agent = AgentVersion(
        name="agent_v1",
        adapter_type="http",
        config_json=json.dumps({"url": "http://localhost:8000"}),
    )
    session.add_all([suite, rubric, agent])
    session.flush()

    run = Run(
        suite_id=suite.id,  # type: ignore[arg-type]
        rubric_id=rubric.id,  # type: ignore[arg-type]
        agent_version_id=agent.id,  # type: ignore[arg-type]
        status="pending",
    )
    session.add(run)
    session.commit()

    result = session.exec(select(Run).where(Run.status == "pending")).one()
    assert result.status == "pending"
    assert result.id is not None


def test_score_chain(session: Session) -> None:
    # Full chain: Suite → EvalCase → AgentVersion → Run → CaseResult → Score
    suite = Suite(name="chain_suite")
    rubric = Rubric(name="chain_rubric", criteria_yaml="[]")
    agent = AgentVersion(name="chain_agent", adapter_type="python", config_json=json.dumps({}))
    session.add_all([suite, rubric, agent])
    session.flush()

    tc = EvalCase(
        suite_id=suite.id,  # type: ignore[arg-type]
        input_json=json.dumps({"role": "user", "content": "test"}),
    )
    session.add(tc)
    session.flush()

    run = Run(
        suite_id=suite.id,  # type: ignore[arg-type]
        rubric_id=rubric.id,  # type: ignore[arg-type]
        agent_version_id=agent.id,  # type: ignore[arg-type]
        status="running",
    )
    session.add(run)
    session.flush()

    cr = CaseResult(
        run_id=run.id,  # type: ignore[arg-type]
        case_id=tc.id,  # type: ignore[arg-type]
        output_json=json.dumps({"content": "I can help"}),
        latency_ms=250,
        tokens=42,
    )
    session.add(cr)
    session.flush()

    score = Score(
        case_result_id=cr.id,  # type: ignore[arg-type]
        criterion="helpful",
        value=4.5,
        reasoning="Good response.",
    )
    session.add(score)
    session.commit()

    result = session.exec(select(Score).where(Score.criterion == "helpful")).one()
    assert result.value == 4.5
    assert result.reasoning == "Good response."


def test_seed_idempotent(session: Session) -> None:
    suite_yaml = DATA_DIR / "customer_support_suite.yaml"
    _load_suite(suite_yaml, session)
    session.commit()
    _load_suite(suite_yaml, session)
    session.commit()

    suites = session.exec(select(Suite)).all()
    assert len(suites) == 1
