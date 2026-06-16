from __future__ import annotations

import typer

app = typer.Typer(name="tender-insights", no_args_is_help=True)


@app.callback()
def main() -> None:
    """tender-insights command group."""
