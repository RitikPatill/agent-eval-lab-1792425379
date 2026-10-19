"""Seed script — populates the DB with sample suite + rubric.

Run from repo root:
    python scripts/seed.py

Idempotent: safe to run multiple times.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from sqlmodel import Session, select

# Allow running without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_eval_lab.db import get_session, init_db
from agent_eval_lab.models import EvalCase, Rubric, Suite


def load_suite_from_yaml(path: Path, session: Session) -> Suite:
    data = yaml.safe_load(path.read_text())
    suite_meta = data["suite"]
    name = suite_meta["name"]

    existing = session.exec(select(Suite).where(Suite.name == name)).first()
    if existing:
        print(f"  Suite '{name}' already exists — skipping.")
        return existing

    suite = Suite(name=name, description=suite_meta.get("description", ""))
    session.add(suite)
    session.flush()  # get suite.id

    for raw in data.get("cases", []):
        tc = EvalCase(
            suite_id=suite.id,  # type: ignore[arg-type]
            input_json=json.dumps(raw["input"]),
            expected_json=json.dumps(raw.get("expected", {})),
            tags=json.dumps(raw.get("tags", [])),
        )
        session.add(tc)

    print(f"  Inserted suite '{name}' with {len(data.get('cases', []))} cases.")
    return suite


def load_rubric_from_yaml(path: Path, session: Session) -> Rubric:
    data = yaml.safe_load(path.read_text())
    rubric_meta = data["rubric"]
    name = rubric_meta["name"]

    existing = session.exec(select(Rubric).where(Rubric.name == name)).first()
    if existing:
        print(f"  Rubric '{name}' already exists — skipping.")
        return existing

    criteria_yaml = yaml.dump(data.get("criteria", []))
    rubric = Rubric(name=name, criteria_yaml=criteria_yaml)
    session.add(rubric)

    print(f"  Inserted rubric '{name}' with {len(data.get('criteria', []))} criteria.")
    return rubric


if __name__ == "__main__":
    init_db()
    session_gen = get_session()
    session = next(session_gen)
    try:
        load_suite_from_yaml(Path("data/customer_support_suite.yaml"), session)
        load_rubric_from_yaml(Path("data/customer_support_rubric.yaml"), session)
        session.commit()
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass

    print("Seeded.")
