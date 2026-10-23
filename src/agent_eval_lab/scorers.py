from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
from dataclasses import dataclass

from sqlmodel import Session

from agent_eval_lab.models import CaseResult, EvalCase, Score

logger = logging.getLogger(__name__)


@dataclass
class ScorerResult:
    score: float  # 1.0–5.0
    reasoning: str


def _llm_judge(criterion: dict, case: EvalCase, case_result: CaseResult) -> ScorerResult:
    import anthropic  # lazy import — keeps module importable without the package

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("JUDGE_MODEL", "claude-haiku-4-5-20251001")

    output = case_result.output
    final_response = output.get("final_response", "")

    prompt = (
        f"You are an impartial judge evaluating an AI agent's response.\n\n"
        f"Test case input:\n{json.dumps(case.input, indent=2)}\n\n"
        f"Agent response:\n{final_response}\n\n"
        f"Criterion: {criterion['name']}\n"
        f"Scoring guidance: {criterion.get('guidance', '')}\n\n"
        f"Score the response on a scale of 1-5 according to the guidance above.\n"
        f"Reply with ONLY a JSON object in this exact format:\n"
        f'{{\"score\": <integer 1-5>, \"reasoning\": \"<brief explanation>\"}}'
    )

    message = client.messages.create(
        model=model,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text
    # Strip ```json ... ``` wrapper if present
    text = re.sub(r"^```(?:json)?\n?|\n?```$", "", text.strip())

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned non-JSON: {text!r}") from exc

    score = float(parsed["score"])
    reasoning = str(parsed["reasoning"])
    return ScorerResult(score=score, reasoning=reasoning)


def _regex_score(criterion: dict, case: EvalCase, case_result: CaseResult) -> ScorerResult:
    output = case_result.output
    final_response = output.get("final_response", "")

    pattern = criterion.get("pattern")
    if pattern:
        match = re.search(pattern, final_response, re.IGNORECASE)
        if match:
            return ScorerResult(score=5.0, reasoning=f"Pattern {pattern!r} matched.")
        else:
            return ScorerResult(score=1.0, reasoning=f"Pattern {pattern!r} did not match.")

    # Fall back to expected["contains"]
    expected_contains: list[str] = case.expected.get("contains", [])
    if not expected_contains:
        return ScorerResult(score=3.0, reasoning="No pattern or contains list to check.")

    matched = [s for s in expected_contains if re.search(re.escape(s), final_response, re.IGNORECASE)]
    unmatched = [s for s in expected_contains if s not in matched]

    ratio = len(matched) / len(expected_contains)
    score = ratio * 4.0 + 1.0  # maps [0,1] → [1,5]
    score = max(1.0, min(5.0, score))

    reasoning = f"Matched {len(matched)}/{len(expected_contains)}: {matched}. Missing: {unmatched}."
    return ScorerResult(score=score, reasoning=reasoning)


def _json_schema_score(criterion: dict, case: EvalCase, case_result: CaseResult) -> ScorerResult:
    import jsonschema  # lazy import

    schema = criterion.get("schema", {})
    output = case_result.output

    try:
        jsonschema.validate(output, schema)
        return ScorerResult(score=5.0, reasoning="Output matches JSON schema.")
    except jsonschema.ValidationError as exc:
        return ScorerResult(score=1.0, reasoning=f"Schema validation failed: {exc.message}")


def _tool_call_score(criterion: dict, case: EvalCase, case_result: CaseResult) -> ScorerResult:
    expected_tools: list[str] = criterion.get("tools", [])
    trace = case_result.trace

    actual_tools: list[str] = [
        tc["name"]
        for turn in trace
        for tc in (turn.get("tool_calls") or [])
    ]

    # Check if expected_tools is a subsequence of actual_tools
    it = iter(actual_tools)
    is_subsequence = all(tool in it for tool in expected_tools)

    if is_subsequence:
        return ScorerResult(
            score=5.0,
            reasoning=f"Expected tool sequence {expected_tools} found in actual {actual_tools}.",
        )
    else:
        return ScorerResult(
            score=1.0,
            reasoning=f"Expected tool sequence {expected_tools} not found in actual {actual_tools}.",
        )


def score_criterion(
    criterion: dict,
    case: EvalCase,
    case_result: CaseResult,
) -> ScorerResult:
    scorer_type = criterion.get("type", "llm_judge")

    if scorer_type == "regex":
        return _regex_score(criterion, case, case_result)
    elif scorer_type == "json_schema":
        return _json_schema_score(criterion, case, case_result)
    elif scorer_type == "tool_call_sequence":
        return _tool_call_score(criterion, case, case_result)
    else:
        return _llm_judge(criterion, case, case_result)


def score_case_result(
    case_result: CaseResult,
    case: EvalCase,
    criteria: list[dict],
    session: Session,
) -> None:
    """Score all criteria for a case result in parallel, persist Score rows."""
    futures: dict[concurrent.futures.Future[ScorerResult], dict] = {}

    with concurrent.futures.ThreadPoolExecutor() as executor:
        for criterion in criteria:
            future = executor.submit(score_criterion, criterion, case, case_result)
            futures[future] = criterion

    for future, criterion in futures.items():
        try:
            result = future.result()
            score = Score(
                case_result_id=case_result.id,  # type: ignore[arg-type]
                criterion=criterion["name"],
                value=result.score,
                reasoning=result.reasoning,
            )
            session.add(score)
        except Exception:
            logger.exception(
                "Scoring criterion %r failed for case_result %s",
                criterion.get("name"),
                case_result.id,
            )

    session.commit()
