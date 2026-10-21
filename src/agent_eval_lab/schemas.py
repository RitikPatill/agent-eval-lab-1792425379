from __future__ import annotations

from pydantic import BaseModel


class TurnSchema(BaseModel):
    role: str  # "user" | "assistant" | "tool"
    content: str
    tool_calls: list[dict] = []  # type: ignore[type-arg]


class AgentOutput(BaseModel):
    turns: list[TurnSchema]
    final_response: str
    latency_ms: int
    tokens: int | None = None


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class SuiteCreate(BaseModel):
    name: str
    description: str = ""


class RubricCreate(BaseModel):
    name: str
    criteria_yaml: str


class AgentVersionCreate(BaseModel):
    name: str
    adapter_type: str = "http"  # "http" | "python"
    config_json: str = "{}"


class RunCreate(BaseModel):
    suite_id: int
    rubric_id: int
    agent_version_id: int


# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------


class SuiteSummary(BaseModel):
    id: int
    name: str
    description: str
    cases_count: int = 0


class SuiteDetail(BaseModel):
    id: int
    name: str
    description: str
    cases_count: int = 0


class EvalCaseSchema(BaseModel):
    id: int
    suite_id: int
    input_json: str
    expected_json: str
    tags: str


class RubricSchema(BaseModel):
    id: int
    name: str
    criteria_yaml: str


class AgentVersionSchema(BaseModel):
    id: int
    name: str
    adapter_type: str
    config_json: str


class ScoreSchema(BaseModel):
    id: int
    case_result_id: int
    criterion: str
    value: float
    reasoning: str


class CaseResultSchema(BaseModel):
    id: int
    run_id: int
    case_id: int
    output_json: str
    trace_json: str
    latency_ms: int | None
    tokens: int | None
    scores: list[ScoreSchema] = []


class RunSchema(BaseModel):
    id: int
    suite_id: int
    rubric_id: int
    agent_version_id: int
    status: str
    started_at: str | None = None


class RunDetail(BaseModel):
    id: int
    suite_id: int
    rubric_id: int
    agent_version_id: int
    status: str
    started_at: str | None = None
    case_results: list[CaseResultSchema] = []
