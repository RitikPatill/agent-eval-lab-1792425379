"""Tests for the FastAPI endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    # conftest autouse fixture has already swapped the engine to in-memory
    from agent_eval_lab.api import app

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# /suites
# ---------------------------------------------------------------------------


def test_list_suites_empty(client: TestClient) -> None:
    resp = client.get("/suites")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_and_list_suite(client: TestClient) -> None:
    resp = client.post("/suites", json={"name": "my_suite", "description": "A test suite"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "my_suite"
    assert data["description"] == "A test suite"
    assert data["id"] is not None

    resp2 = client.get("/suites")
    assert resp2.status_code == 200
    assert len(resp2.json()) == 1
    assert resp2.json()[0]["name"] == "my_suite"


def test_get_suite_not_found(client: TestClient) -> None:
    resp = client.get("/suites/999")
    assert resp.status_code == 404


def test_get_suite_detail(client: TestClient) -> None:
    create = client.post("/suites", json={"name": "detail_suite"})
    suite_id = create.json()["id"]
    resp = client.get(f"/suites/{suite_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "detail_suite"
    assert resp.json()["cases_count"] == 0


def test_list_suite_cases_empty(client: TestClient) -> None:
    create = client.post("/suites", json={"name": "cases_suite"})
    suite_id = create.json()["id"]
    resp = client.get(f"/suites/{suite_id}/cases")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# /rubrics
# ---------------------------------------------------------------------------


def test_create_rubric(client: TestClient) -> None:
    resp = client.post(
        "/rubrics",
        json={"name": "rubric_v1", "criteria_yaml": "- name: helpful\n  guidance: '1=bad'"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "rubric_v1"
    assert "helpful" in data["criteria_yaml"]


def test_list_rubrics(client: TestClient) -> None:
    client.post("/rubrics", json={"name": "r1", "criteria_yaml": "[]"})
    resp = client.get("/rubrics")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# /agents
# ---------------------------------------------------------------------------


def test_create_agent_version(client: TestClient) -> None:
    resp = client.post(
        "/agents",
        json={"name": "my_agent", "adapter_type": "http", "config_json": '{"url": "http://localhost:8000"}'},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "my_agent"
    assert data["adapter_type"] == "http"


def test_list_agents(client: TestClient) -> None:
    client.post("/agents", json={"name": "agent_a", "adapter_type": "python", "config_json": "{}"})
    resp = client.get("/agents")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# /runs
# ---------------------------------------------------------------------------


def _create_prerequisites(client: TestClient) -> tuple[int, int, int]:
    suite_id = client.post("/suites", json={"name": "run_suite"}).json()["id"]
    rubric_id = client.post("/rubrics", json={"name": "run_rubric", "criteria_yaml": "[]"}).json()["id"]
    agent_id = client.post(
        "/agents",
        json={"name": "run_agent", "adapter_type": "http", "config_json": '{"url": "http://localhost"}'},
    ).json()["id"]
    return suite_id, rubric_id, agent_id


def test_create_run_returns_pending(client: TestClient) -> None:
    suite_id, rubric_id, agent_id = _create_prerequisites(client)
    resp = client.post(
        "/runs",
        json={"suite_id": suite_id, "rubric_id": rubric_id, "agent_version_id": agent_id},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["suite_id"] == suite_id


def test_list_runs(client: TestClient) -> None:
    suite_id, rubric_id, agent_id = _create_prerequisites(client)
    client.post(
        "/runs",
        json={"suite_id": suite_id, "rubric_id": rubric_id, "agent_version_id": agent_id},
    )
    resp = client.get("/runs")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_runs_filter_by_status(client: TestClient) -> None:
    suite_id, rubric_id, agent_id = _create_prerequisites(client)
    client.post(
        "/runs",
        json={"suite_id": suite_id, "rubric_id": rubric_id, "agent_version_id": agent_id},
    )
    resp = client.get("/runs?status=pending")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp2 = client.get("/runs?status=done")
    assert resp2.status_code == 200
    assert resp2.json() == []


def test_get_run_not_found_returns_404(client: TestClient) -> None:
    resp = client.get("/runs/9999")
    assert resp.status_code == 404


def test_get_run_detail(client: TestClient) -> None:
    suite_id, rubric_id, agent_id = _create_prerequisites(client)
    run_id = client.post(
        "/runs",
        json={"suite_id": suite_id, "rubric_id": rubric_id, "agent_version_id": agent_id},
    ).json()["id"]
    resp = client.get(f"/runs/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == run_id
    assert data["status"] == "pending"
    assert data["case_results"] == []


def test_create_run_with_invalid_suite_returns_404(client: TestClient) -> None:
    _, rubric_id, agent_id = _create_prerequisites(client)
    resp = client.post(
        "/runs",
        json={"suite_id": 9999, "rubric_id": rubric_id, "agent_version_id": agent_id},
    )
    assert resp.status_code == 404
