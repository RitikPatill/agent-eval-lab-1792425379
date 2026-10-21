from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool


@pytest.fixture(autouse=True)
def use_in_memory_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force all DB operations to use a shared in-memory SQLite database.

    StaticPool ensures every Session/Connection reuses the same underlying
    sqlite3 connection, which is required for :memory: to share data across
    multiple Session instances (e.g. the one used by lifespan vs. the one
    created per-request in the FastAPI dependency).
    """
    monkeypatch.setenv("DB_URL", "sqlite:///:memory:")

    import agent_eval_lab.db as db_module
    from sqlmodel import create_engine

    db_module.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    db_module.init_db()
