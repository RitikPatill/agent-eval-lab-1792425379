from __future__ import annotations

import typer
from sqlmodel import select

app = typer.Typer()


@app.command()
def main() -> None:
    typer.echo("Agent Eval Lab — use 'agent-eval run --help' for the run command")


@app.command()
def run(
    suite: str = typer.Option(..., help="Suite name"),
    agent: str = typer.Option(..., help="Agent name (must exist in DB)"),
    rubric: str = typer.Option(..., help="Rubric name"),
) -> None:
    """Execute an eval run synchronously."""
    from agent_eval_lab.db import get_session, init_db
    from agent_eval_lab.models import AgentVersion, Rubric, Run, Suite
    from agent_eval_lab.runner import execute_run

    init_db()
    session_gen = get_session()
    session = next(session_gen)

    suite_obj = session.exec(select(Suite).where(Suite.name == suite)).first()
    if suite_obj is None:
        typer.echo(f"Suite '{suite}' not found.", err=True)
        raise typer.Exit(code=1)

    rubric_obj = session.exec(select(Rubric).where(Rubric.name == rubric)).first()
    if rubric_obj is None:
        typer.echo(f"Rubric '{rubric}' not found.", err=True)
        raise typer.Exit(code=1)

    agent_obj = session.exec(select(AgentVersion).where(AgentVersion.name == agent)).first()
    if agent_obj is None:
        typer.echo(f"Agent '{agent}' not found.", err=True)
        raise typer.Exit(code=1)

    eval_run = Run(
        suite_id=suite_obj.id,  # type: ignore[arg-type]
        rubric_id=rubric_obj.id,  # type: ignore[arg-type]
        agent_version_id=agent_obj.id,  # type: ignore[arg-type]
        status="pending",
    )
    session.add(eval_run)
    session.commit()
    session.refresh(eval_run)

    typer.echo(f"Starting run {eval_run.id} ...")
    execute_run(eval_run.id, session)  # type: ignore[arg-type]

    session.refresh(eval_run)
    typer.echo(f"Run {eval_run.id} finished with status: {eval_run.status}")
