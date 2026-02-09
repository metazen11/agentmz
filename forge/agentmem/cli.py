"""CLI commands for agent memory management.

Usage:
    forge mem process    - Process pending observations
    forge mem search     - Search observations
    forge mem stats      - Show statistics
    forge mem pending    - Count pending observations
"""

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Agent memory management commands")
console = Console()


@app.command()
def process(
    limit: int = typer.Option(100, help="Max observations to process"),
) -> None:
    """Process pending observations (classify and embed)."""
    from forge.agentmem.worker import process_pending

    console.print(f"[blue]Processing up to {limit} pending observations...[/blue]")

    try:
        stats = process_pending(limit=limit)

        console.print(f"[green]Updated:[/green] {stats['updated']}")
        console.print(f"[yellow]Deleted (routine):[/yellow] {stats['deleted']}")
        console.print(f"[red]Errors:[/red] {stats['errors']}")
        console.print(f"[blue]Remaining:[/blue] {stats['remaining']}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, help="Max results"),
) -> None:
    """Search observations by semantic similarity."""
    from forge.agentmem.retrieval import search_similar

    console.print(f"[blue]Searching for:[/blue] {query}")

    try:
        results = search_similar(query=query, limit=limit)

        if not results:
            console.print("[yellow]No matching observations found[/yellow]")
            return

        table = Table(title=f"Search Results ({len(results)})")
        table.add_column("ID", style="dim")
        table.add_column("Type", style="cyan")
        table.add_column("Tool", style="green")
        table.add_column("Title")
        table.add_column("Similarity", style="magenta")

        for obs in results:
            table.add_row(
                str(obs["id"]),
                obs["obs_type"] or "",
                obs["tool"],
                obs["title"] or "",
                f"{obs['similarity']:.2f}",
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def stats() -> None:
    """Show observation statistics."""
    from forge.agentmem.store import count_by_type, count_pending

    try:
        pending = count_pending()
        by_type = count_by_type()

        console.print("\n[bold]Observation Statistics[/bold]\n")

        table = Table()
        table.add_column("Type", style="cyan")
        table.add_column("Count", style="green")

        table.add_row("Pending", str(pending))
        for obs_type, count in sorted(by_type.items()):
            table.add_row(obs_type, str(count))

        total = pending + sum(by_type.values())
        table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]")

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def pending() -> None:
    """Count pending observations."""
    from forge.agentmem.store import count_pending

    try:
        count = count_pending()
        console.print(f"[blue]Pending observations:[/blue] {count}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def show(
    obs_id: int = typer.Argument(..., help="Observation ID"),
) -> None:
    """Show full details for an observation."""
    from forge.agentmem.retrieval import get_observation_details

    try:
        details = get_observation_details([obs_id])

        if not details:
            console.print(f"[yellow]Observation {obs_id} not found[/yellow]")
            return

        obs = details[0]
        console.print(f"\n[bold]Observation #{obs['id']}[/bold]\n")
        console.print(f"[cyan]Session:[/cyan] {obs['session_id']}")
        console.print(f"[cyan]Tool:[/cyan] {obs['tool']}")
        console.print(f"[cyan]Type:[/cyan] {obs['obs_type']}")
        console.print(f"[cyan]Title:[/cyan] {obs['title']}")
        console.print(f"[cyan]Success:[/cyan] {obs['success']}")
        console.print(f"[cyan]Exit Code:[/cyan] {obs['exit_code']}")
        console.print(f"[cyan]Duration:[/cyan] {obs['duration_ms']}ms")
        console.print(f"\n[cyan]Args:[/cyan]\n{obs['args_summary']}")
        console.print(f"\n[cyan]Output:[/cyan]\n{obs['output_summary']}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def worker(
    interval: int = typer.Option(10, help="Seconds between processing passes"),
    iterations: int = typer.Option(None, help="Max iterations (None = run forever)"),
) -> None:
    """Run the background worker continuously."""
    from forge.agentmem.worker import run_worker

    console.print(f"[blue]Starting worker (interval={interval}s)...[/blue]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    try:
        run_worker(interval_seconds=interval, max_iterations=iterations)
    except KeyboardInterrupt:
        console.print("\n[yellow]Worker stopped[/yellow]")


if __name__ == "__main__":
    app()
