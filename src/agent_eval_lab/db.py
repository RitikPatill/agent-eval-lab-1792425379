from __future__ import annotations

import os
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv("DB_URL", "sqlite:///agent_eval_lab.db")

engine = create_engine(DATABASE_URL, echo=False)


def init_db() -> None:
    """Create all tables if they don't exist yet."""
    # Import models so their metadata is registered before create_all
    import agent_eval_lab.models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """Yield a database session (use as a dependency or context manager)."""
    with Session(engine) as session:
        yield session


if __name__ == "__main__":
    init_db()
    print("Database initialised at", DATABASE_URL)
