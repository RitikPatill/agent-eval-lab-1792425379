import json
from datetime import datetime
from typing import List, Optional

import yaml
from sqlmodel import Field, Relationship, SQLModel


class Suite(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: str = ""

    cases: List["EvalCase"] = Relationship(back_populates="suite")
    runs: List["Run"] = Relationship(back_populates="suite")


class EvalCase(SQLModel, table=True):
    """A single test case within a Suite.

    Named EvalCase (not TestCase) to avoid pytest collection conflicts.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    suite_id: int = Field(foreign_key="suite.id")
    # JSON-encoded dicts
    input_json: str = "{}"
    expected_json: str = "{}"
    # JSON-encoded list of strings
    tags: str = "[]"

    suite: Optional[Suite] = Relationship(back_populates="cases")
    results: List["CaseResult"] = Relationship(back_populates="case")

    @property
    def input(self) -> dict:  # type: ignore[type-arg]
        return json.loads(self.input_json)  # type: ignore[no-any-return]

    @property
    def expected(self) -> dict:  # type: ignore[type-arg]
        return json.loads(self.expected_json)  # type: ignore[no-any-return]

    @property
    def tag_list(self) -> List[str]:
        return json.loads(self.tags)  # type: ignore[no-any-return]


class Rubric(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    # Raw YAML text — parse with .criteria property
    criteria_yaml: str = ""

    runs: List["Run"] = Relationship(back_populates="rubric")

    @property
    def criteria(self) -> List[dict]:  # type: ignore[type-arg]
        return yaml.safe_load(self.criteria_yaml) or []  # type: ignore[no-any-return]


class AgentVersion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    # "http" or "python"
    adapter_type: str = "http"
    # JSON-encoded adapter config (url, module path, etc.)
    config_json: str = "{}"

    runs: List["Run"] = Relationship(back_populates="agent_version")

    @property
    def config(self) -> dict:  # type: ignore[type-arg]
        return json.loads(self.config_json)  # type: ignore[no-any-return]


class Run(SQLModel, table=True):
    __tablename__ = "eval_run"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    suite_id: int = Field(foreign_key="suite.id")
    rubric_id: int = Field(foreign_key="rubric.id")
    agent_version_id: int = Field(foreign_key="agentversion.id")
    # "pending" | "running" | "done" | "failed"
    status: str = "pending"
    started_at: Optional[datetime] = None

    suite: Optional[Suite] = Relationship(back_populates="runs")
    rubric: Optional[Rubric] = Relationship(back_populates="runs")
    agent_version: Optional[AgentVersion] = Relationship(back_populates="runs")
    case_results: List["CaseResult"] = Relationship(back_populates="run")


class CaseResult(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="eval_run.id")
    case_id: int = Field(foreign_key="evalcase.id")
    # JSON-encoded agent output
    output_json: str = "{}"
    # JSON-encoded full conversation trace
    trace_json: str = "[]"
    latency_ms: Optional[int] = None
    tokens: Optional[int] = None

    run: Optional[Run] = Relationship(back_populates="case_results")
    case: Optional[EvalCase] = Relationship(back_populates="results")
    scores: List["Score"] = Relationship(back_populates="case_result")

    @property
    def output(self) -> dict:  # type: ignore[type-arg]
        return json.loads(self.output_json)  # type: ignore[no-any-return]

    @property
    def trace(self) -> list:  # type: ignore[type-arg]
        return json.loads(self.trace_json)  # type: ignore[no-any-return]


class Score(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    case_result_id: int = Field(foreign_key="caseresult.id")
    criterion: str = ""
    # 1–5 rubric score
    value: float = 0.0
    reasoning: str = ""

    case_result: Optional[CaseResult] = Relationship(back_populates="scores")
