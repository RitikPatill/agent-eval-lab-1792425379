import typer

app = typer.Typer()


@app.command()
def main() -> None:
    typer.echo("Agent Eval Lab — use 'agent-eval run --help' (coming soon)")
