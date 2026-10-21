from __future__ import annotations

from collections.abc import Generator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlmodel import Session, select

from agent_eval_lab.db import get_session, init_db
from agent_eval_lab.models import AgentVersion, EvalCase, Rubric, Run, Suite
from agent_eval_lab.schemas import (
    AgentVersionCreate,
    AgentVersionSchema,
    CaseResultSchema,
    EvalCaseSchema,
    RunCreate,
    RunDetail,
    RunSchema,
    RubricCreate,
    RubricSchema,
    ScoreSchema,
    SuiteCreate,
    SuiteDetail,
    SuiteSummary,
)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    init_db()
    yield


app = FastAPI(title="Agent Eval Lab", version="0.1.0", lifespan=lifespan)

SessionDep = Annotated[Session, Depends(get_session)]


# ---------------------------------------------------------------------------
# /suites
# ---------------------------------------------------------------------------


@app.get("/suites", response_model=list[SuiteSummary])
def list_suites(session: SessionDep) -> list[SuiteSummary]:
    suites = session.exec(select(Suite)).all()
    return [
        SuiteSummary(
            id=s.id,  # type: ignore[arg-type]
            name=s.name,
            description=s.description,
            cases_count=len(s.cases),
        )
        for s in suites
    ]


@app.post("/suites", response_model=SuiteSummary, status_code=201)
def create_suite(body: SuiteCreate, session: SessionDep) -> SuiteSummary:
    suite = Suite(name=body.name, description=body.description)
    session.add(suite)
    session.commit()
    session.refresh(suite)
    return SuiteSummary(
        id=suite.id,  # type: ignore[arg-type]
        name=suite.name,
        description=suite.description,
        cases_count=0,
    )


@app.get("/suites/{suite_id}", response_model=SuiteDetail)
def get_suite(suite_id: int, session: SessionDep) -> SuiteDetail:
    suite = session.get(Suite, suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail="Suite not found")
    return SuiteDetail(
        id=suite.id,  # type: ignore[arg-type]
        name=suite.name,
        description=suite.description,
        cases_count=len(suite.cases),
    )


@app.get("/suites/{suite_id}/cases", response_model=list[EvalCaseSchema])
def list_cases(suite_id: int, session: SessionDep) -> list[EvalCaseSchema]:
    suite = session.get(Suite, suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail="Suite not found")
    cases = session.exec(select(EvalCase).where(EvalCase.suite_id == suite_id)).all()
    return [
        EvalCaseSchema(
            id=c.id,  # type: ignore[arg-type]
            suite_id=c.suite_id,
            input_json=c.input_json,
            expected_json=c.expected_json,
            tags=c.tags,
        )
        for c in cases
    ]


# ---------------------------------------------------------------------------
# /rubrics
# ---------------------------------------------------------------------------


@app.get("/rubrics", response_model=list[RubricSchema])
def list_rubrics(session: SessionDep) -> list[RubricSchema]:
    rubrics = session.exec(select(Rubric)).all()
    return [
        RubricSchema(id=r.id, name=r.name, criteria_yaml=r.criteria_yaml)  # type: ignore[arg-type]
        for r in rubrics
    ]


@app.post("/rubrics", response_model=RubricSchema, status_code=201)
def create_rubric(body: RubricCreate, session: SessionDep) -> RubricSchema:
    rubric = Rubric(name=body.name, criteria_yaml=body.criteria_yaml)
    session.add(rubric)
    session.commit()
    session.refresh(rubric)
    return RubricSchema(id=rubric.id, name=rubric.name, criteria_yaml=rubric.criteria_yaml)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# /agents
# ---------------------------------------------------------------------------


@app.get("/agents", response_model=list[AgentVersionSchema])
def list_agents(session: SessionDep) -> list[AgentVersionSchema]:
    agents = session.exec(select(AgentVersion)).all()
    return [
        AgentVersionSchema(
            id=a.id,  # type: ignore[arg-type]
            name=a.name,
            adapter_type=a.adapter_type,
            config_json=a.config_json,
        )
        for a in agents
    ]


@app.post("/agents", response_model=AgentVersionSchema, status_code=201)
def create_agent(body: AgentVersionCreate, session: SessionDep) -> AgentVersionSchema:
    agent = AgentVersion(name=body.name, adapter_type=body.adapter_type, config_json=body.config_json)
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return AgentVersionSchema(
        id=agent.id,  # type: ignore[arg-type]
        name=agent.name,
        adapter_type=agent.adapter_type,
        config_json=agent.config_json,
    )


# ---------------------------------------------------------------------------
# /runs
# ---------------------------------------------------------------------------


@app.get("/runs", response_model=list[RunSchema])
def list_runs(session: SessionDep, status: str | None = None) -> list[RunSchema]:
    stmt = select(Run)
    if status is not None:
        stmt = stmt.where(Run.status == status)
    runs = session.exec(stmt).all()
    return [
        RunSchema(
            id=r.id,  # type: ignore[arg-type]
            suite_id=r.suite_id,
            rubric_id=r.rubric_id,
            agent_version_id=r.agent_version_id,
            status=r.status,
            started_at=r.started_at.isoformat() if r.started_at else None,
        )
        for r in runs
    ]


@app.post("/runs", response_model=RunSchema, status_code=201)
def create_run(body: RunCreate, session: SessionDep) -> RunSchema:
    # Validate FKs exist
    if session.get(Suite, body.suite_id) is None:
        raise HTTPException(status_code=404, detail="Suite not found")
    if session.get(Rubric, body.rubric_id) is None:
        raise HTTPException(status_code=404, detail="Rubric not found")
    if session.get(AgentVersion, body.agent_version_id) is None:
        raise HTTPException(status_code=404, detail="AgentVersion not found")

    run = Run(
        suite_id=body.suite_id,
        rubric_id=body.rubric_id,
        agent_version_id=body.agent_version_id,
        status="pending",
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return RunSchema(
        id=run.id,  # type: ignore[arg-type]
        suite_id=run.suite_id,
        rubric_id=run.rubric_id,
        agent_version_id=run.agent_version_id,
        status=run.status,
        started_at=run.started_at.isoformat() if run.started_at else None,
    )


@app.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: int, session: SessionDep) -> RunDetail:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    case_results = [
        CaseResultSchema(
            id=cr.id,  # type: ignore[arg-type]
            run_id=cr.run_id,
            case_id=cr.case_id,
            output_json=cr.output_json,
            trace_json=cr.trace_json,
            latency_ms=cr.latency_ms,
            tokens=cr.tokens,
            scores=[
                ScoreSchema(
                    id=s.id,  # type: ignore[arg-type]
                    case_result_id=s.case_result_id,
                    criterion=s.criterion,
                    value=s.value,
                    reasoning=s.reasoning,
                )
                for s in cr.scores
            ],
        )
        for cr in run.case_results
    ]

    return RunDetail(
        id=run.id,  # type: ignore[arg-type]
        suite_id=run.suite_id,
        rubric_id=run.rubric_id,
        agent_version_id=run.agent_version_id,
        status=run.status,
        started_at=run.started_at.isoformat() if run.started_at else None,
        case_results=case_results,
    )
