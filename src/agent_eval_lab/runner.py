from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlmodel import Session, select

from agent_eval_lab.adapters import get_adapter
from agent_eval_lab.models import AgentVersion, CaseResult, EvalCase, Run

logger = logging.getLogger(__name__)


def execute_run(run_id: int, session: Session) -> None:
    """Load run → iterate suite cases → call adapter → persist CaseResult.

    Does NOT score (that's M4). Sets run.status = "running" then "done"/"failed".
    """
    run = session.get(Run, run_id)
    if run is None:
        raise ValueError(f"Run {run_id} not found")

    run.status = "running"
    run.started_at = datetime.now(tz=timezone.utc)
    session.add(run)
    session.commit()

    agent_version = session.get(AgentVersion, run.agent_version_id)
    if agent_version is None:
        run.status = "failed"
        session.add(run)
        session.commit()
        raise ValueError(f"AgentVersion {run.agent_version_id} not found")

    adapter = get_adapter(agent_version)

    cases = session.exec(select(EvalCase).where(EvalCase.suite_id == run.suite_id)).all()

    try:
        for case in cases:
            try:
                output = adapter.run(case.input)
                cr = CaseResult(
                    run_id=run.id,  # type: ignore[arg-type]
                    case_id=case.id,  # type: ignore[arg-type]
                    output_json=json.dumps({"final_response": output.final_response}),
                    trace_json=json.dumps([t.model_dump() for t in output.turns]),
                    latency_ms=output.latency_ms,
                    tokens=output.tokens,
                )
            except Exception:
                logger.exception("Adapter failed for case %s", case.id)
                cr = CaseResult(
                    run_id=run.id,  # type: ignore[arg-type]
                    case_id=case.id,  # type: ignore[arg-type]
                    output_json="{}",
                    trace_json="[]",
                    latency_ms=None,
                    tokens=None,
                )
            session.add(cr)

        session.commit()
        run.status = "done"
    except Exception:
        logger.exception("Run %s failed", run_id)
        run.status = "failed"

    session.add(run)
    session.commit()
