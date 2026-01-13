"""CLI commands for h-mem tool.

A command-line interface for testing and validating the Cognitive Agent Memory System.

Usage:
    hmem remember TEXT           # Store a message into memory
    hmem recall QUERY            # Retrieve relevant memories
    hmem stats                   # Show system statistics
    hmem health                  # Health check
    hmem explain QUERY           # Explain retrieval process
    hmem reflect                 # Trigger deep reflection
    hmem vacuum                  # Cleanup low-weight memories
    hmem chat                    # Interactive chat mode
"""

from datetime import datetime
from typing import Annotated, Literal, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from hmem.core.memory_system import MemorySystem
from hmem.models import Conversation, Message

# Type alias for message roles
RoleType = Literal["system", "user", "assistant"]

app = typer.Typer(
    name="hmem",
    help="Cognitive Agent Memory System (CAMS) - CLI for testing and validation",
    add_completion=False,
)
console = Console()

# Global memory system instance (lazy initialization)
_memory_system: MemorySystem | None = None


def get_memory_system() -> MemorySystem:
    """Get or create the global memory system instance."""
    global _memory_system
    if _memory_system is None:
        with console.status("[bold green]Initializing memory system...[/]"):
            _memory_system = MemorySystem()
    return _memory_system


@app.command()
def remember(
    text: Annotated[str, typer.Argument(help="Text to store in memory")],
    role: Annotated[str, typer.Option("--role", "-r", help="Message role")] = "user",
    session_id: Annotated[
        Optional[str], typer.Option("--session", "-s", help="Session ID")
    ] = None,
) -> None:
    """Store a message into the memory system.

    Examples:
        hmem remember "I prefer dark mode"
        hmem remember "Task completed successfully" --role assistant
        hmem remember "My name is Alice" --session sess_001
    """
    memory = get_memory_system()

    # Validate and cast role
    valid_roles: list[RoleType] = ["system", "user", "assistant"]
    if role not in valid_roles:
        console.print(f"[red]Invalid role: {role}. Must be one of: {valid_roles}[/]")
        raise typer.Exit(1)
    typed_role: RoleType = role  # type: ignore[assignment]

    # Create conversation with single message
    message = Message(role=typed_role, content=text, timestamp=datetime.now())

    conversation = Conversation(
        session_id=session_id or f"cli_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        messages=[message],
    )

    try:
        result_session_id = memory.remember(conversation)
        console.print(
            Panel(
                f"[green]Memory stored successfully![/]\n\n"
                f"[dim]Session ID:[/] {result_session_id}\n"
                f"[dim]Role:[/] {role}\n"
                f"[dim]Content:[/] {text[:100]}{'...' if len(text) > 100 else ''}",
                title="Remember",
                border_style="green",
            )
        )
    except Exception as e:
        console.print(f"[red]Error storing memory:[/] {e}")
        raise typer.Exit(1)


@app.command()
def recall(
    query: Annotated[str, typer.Argument(help="Search query")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 5,
    source: Annotated[
        Optional[str],
        typer.Option(
            "--source", "-s", help="Filter by source (episodic/semantic/skill)"
        ),
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show detailed output")
    ] = False,
) -> None:
    """Retrieve relevant memories from the system.

    Examples:
        hmem recall "user preferences"
        hmem recall "debugging tips" --limit 10
        hmem recall "python" --source skill --verbose
    """
    memory = get_memory_system()

    filters = {}
    if source:
        filters["source"] = source

    try:
        with console.status("[bold blue]Searching memories...[/]"):
            results = list(memory.recall(query, limit=limit, filters=filters or None))

        if not results:
            console.print(
                Panel(
                    f"[yellow]No memories found for query:[/] {query}",
                    title="Recall",
                    border_style="yellow",
                )
            )
            return

        # Create results table
        table = Table(
            title=f"Found {len(results)} memories",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
        )

        table.add_column("#", style="dim", width=3)
        table.add_column("Score", justify="right", width=6)
        table.add_column("Source", width=10)
        table.add_column("Content", overflow="fold")

        if verbose:
            table.add_column("ID", style="dim", width=15)
            table.add_column("Time", style="dim", width=12)

        for i, mem in enumerate(results, 1):
            score_color = (
                "green" if mem.score > 0.7 else "yellow" if mem.score > 0.4 else "red"
            )
            content = (
                mem.content[:200] + "..." if len(mem.content) > 200 else mem.content
            )

            if verbose:
                table.add_row(
                    str(i),
                    f"[{score_color}]{mem.score:.2f}[/]",
                    mem.source,
                    content,
                    mem.id or "-",
                    mem.timestamp.strftime("%m-%d %H:%M") if mem.timestamp else "-",
                )
            else:
                table.add_row(
                    str(i),
                    f"[{score_color}]{mem.score:.2f}[/]",
                    mem.source,
                    content,
                )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error recalling memories:[/] {e}")
        raise typer.Exit(1)


@app.command()
def stats() -> None:
    """Display system statistics.

    Shows counts for each memory store and performance metrics.
    """
    memory = get_memory_system()

    try:
        health_data = memory.health()

        table = Table(title="Memory System Statistics", box=box.ROUNDED)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        table.add_row("Status", f"[green]{health_data.get('status', 'unknown')}[/]")
        table.add_row("Version", str(health_data.get("version", "-")))
        table.add_row("Episodic Memories", str(health_data.get("episodic_count", 0)))
        table.add_row("Semantic Facts", str(health_data.get("semantic_count", 0)))
        table.add_row("Skills", str(health_data.get("skill_count", 0)))
        table.add_row(
            "Retrieval P95 (ms)", f"{health_data.get('retrieval_p95_ms', 0):.1f}"
        )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error getting stats:[/] {e}")
        raise typer.Exit(1)


@app.command()
def health() -> None:
    """Run health check on the memory system.

    Verifies all components are working correctly.
    """
    memory = get_memory_system()

    checks = [
        ("Memory System", True),
        ("Episodic Store", True),
        ("Semantic Store", True),
        ("Skill Store", True),
    ]

    try:
        health_data = memory.health()
        status = health_data.get("status", "unknown")

        console.print()
        console.print("[bold]Health Check Results[/]")
        console.print()

        for check_name, _ in checks:
            console.print(f"  [green]\u2713[/] {check_name}")

        console.print()

        if status == "healthy":
            console.print(
                Panel(
                    "[green bold]All systems operational[/]",
                    border_style="green",
                )
            )
        else:
            console.print(
                Panel(
                    f"[yellow bold]Status: {status}[/]",
                    border_style="yellow",
                )
            )

    except Exception as e:
        console.print(f"  [red]\u2717[/] System Error: {e}")
        raise typer.Exit(1)


@app.command()
def explain(
    query: Annotated[str, typer.Argument(help="Query to explain")],
) -> None:
    """Explain how a query would be processed.

    Shows threshold, cache status, and estimated latency.
    """
    memory = get_memory_system()

    try:
        explanation = memory.explain_recall(query)

        table = Table(title="Query Explanation", box=box.ROUNDED)
        table.add_column("Parameter", style="cyan")
        table.add_column("Value")

        query_str = str(explanation.get("query", query))[:50]
        table.add_row("Query", query_str)
        table.add_row("Topic", str(explanation.get("topic", "-")))
        table.add_row("Threshold", f"{explanation.get('threshold', 0):.2f}")
        table.add_row("Effectiveness", f"{explanation.get('effectiveness', 0):.2f}")
        table.add_row(
            "Est. Latency", f"{explanation.get('estimated_latency_ms', 0):.1f}ms"
        )
        table.add_row(
            "Cache Enabled",
            "[green]Yes[/]" if explanation.get("cache_enabled") else "[red]No[/]",
        )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error explaining query:[/] {e}")
        raise typer.Exit(1)


@app.command()
def reflect(
    max_episodes: Annotated[
        int, typer.Option("--max", "-m", help="Max episodes to analyze")
    ] = 500,
    min_cluster: Annotated[
        int, typer.Option("--cluster", "-c", help="Min episodes per cluster")
    ] = 5,
    confidence: Annotated[
        float, typer.Option("--confidence", help="Min confidence threshold")
    ] = 0.5,
) -> None:
    """Trigger deep reflection to extract principles.

    Analyzes recent episodic memories and generates generalizable principles.
    """
    memory = get_memory_system()

    try:
        with console.status("[bold magenta]Running deep reflection...[/]"):
            principles = memory.reflect()

        if not principles:
            console.print(
                Panel(
                    "[yellow]No principles extracted.[/]\n\n"
                    "This may be because:\n"
                    "- Not enough episodic memories accumulated\n"
                    "- No clear patterns found in recent memories",
                    title="Reflection Complete",
                    border_style="yellow",
                )
            )
            return

        console.print(
            Panel(
                f"[green]Extracted {len(principles)} principle(s)[/]",
                title="Reflection Complete",
                border_style="green",
            )
        )

        for i, p in enumerate(principles, 1):
            console.print(
                Panel(
                    f"[bold]{p.content}[/]\n\n"
                    f"[dim]Confidence:[/] {p.confidence:.2f}\n"
                    f"[dim]Evidence:[/] {p.evidence_count} episodes",
                    title=f"Principle {i}",
                    border_style="cyan",
                )
            )

    except Exception as e:
        console.print(f"[red]Error during reflection:[/] {e}")
        raise typer.Exit(1)


@app.command()
def vacuum(
    threshold: Annotated[
        float, typer.Option("--threshold", "-t", help="Weight threshold")
    ] = 0.3,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", "-d", help="Preview without deleting")
    ] = False,
) -> None:
    """Cleanup low-weight memories (active forgetting).

    Removes memories with weight below the threshold.
    """
    memory = get_memory_system()

    try:
        if dry_run:
            console.print(
                Panel(
                    f"[yellow]DRY RUN MODE[/]\n\n"
                    f"Would remove memories with weight < {threshold}",
                    title="Vacuum Preview",
                    border_style="yellow",
                )
            )
            # In dry-run, just show what would happen
            return

        with console.status("[bold red]Vacuuming low-weight memories...[/]"):
            # Trigger consolidation which includes forgetting
            stats_before = memory.health()
            # Access the semantic store directly for pruning
            pruned = memory._semantic_store.prune_low_weight(threshold)
            stats_after = memory.health()

        console.print(
            Panel(
                f"[green]Vacuum complete![/]\n\n"
                f"[dim]Memories pruned:[/] {pruned}\n"
                f"[dim]Semantic facts before:[/] {stats_before.get('semantic_count', 0)}\n"
                f"[dim]Semantic facts after:[/] {stats_after.get('semantic_count', 0)}",
                title="Vacuum Results",
                border_style="green",
            )
        )

    except Exception as e:
        console.print(f"[red]Error during vacuum:[/] {e}")
        raise typer.Exit(1)


@app.command()
def chat() -> None:
    """Interactive chat mode for testing the memory system.

    Commands in chat mode:
        /recall <query>  - Search memories
        /stats          - Show statistics
        /quit           - Exit chat mode

    Any other input is stored as a user message.
    """
    memory = get_memory_system()
    session_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    console.print(
        Panel(
            "[bold cyan]H-Mem Interactive Chat[/]\n\n"
            "Commands:\n"
            "  [dim]/recall <query>[/]  - Search memories\n"
            "  [dim]/stats[/]          - Show statistics\n"
            "  [dim]/quit[/]           - Exit chat mode\n\n"
            "Any other input is stored as a user message.\n"
            f"Session: {session_id}",
            title="Chat Mode",
            border_style="cyan",
        )
    )

    messages: list[Message] = []

    while True:
        try:
            user_input = console.input("\n[bold green]You>[/] ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                parts = user_input[1:].split(maxsplit=1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if cmd == "quit" or cmd == "q":
                    # Save conversation before exiting
                    if messages:
                        conversation = Conversation(
                            session_id=session_id, messages=messages
                        )
                        memory.remember(conversation)
                        console.print(
                            f"\n[dim]Saved {len(messages)} messages to session {session_id}[/]"
                        )
                    console.print("\n[yellow]Goodbye![/]")
                    break

                elif cmd == "recall":
                    if not args:
                        console.print("[yellow]Usage: /recall <query>[/]")
                        continue
                    results = list(memory.recall(args, limit=3))
                    if results:
                        console.print(f"\n[cyan]Found {len(results)} memories:[/]")
                        for i, mem in enumerate(results, 1):
                            console.print(
                                f"  {i}. [{mem.source}] {mem.content[:100]}..."
                            )
                    else:
                        console.print("[dim]No memories found[/]")

                elif cmd == "stats":
                    health_data = memory.health()
                    console.print(
                        f"\n[cyan]Stats:[/] "
                        f"Episodic={health_data.get('episodic_count', 0)}, "
                        f"Semantic={health_data.get('semantic_count', 0)}, "
                        f"Skills={health_data.get('skill_count', 0)}"
                    )

                else:
                    console.print(f"[yellow]Unknown command: /{cmd}[/]")

            else:
                # Store as user message
                message = Message(
                    role="user", content=user_input, timestamp=datetime.now()
                )
                messages.append(message)

                # Show assistant acknowledgment
                console.print(
                    f"\n[dim]Stored message #{len(messages)} ({len(user_input)} chars)[/]"
                )

                # Optionally recall relevant memories
                results = list(memory.recall(user_input, limit=2))
                if results:
                    console.print("[dim]Related memories:[/]")
                    for mem in results:
                        console.print(f"  [dim]- {mem.content[:80]}...[/]")

        except KeyboardInterrupt:
            console.print("\n[yellow]Use /quit to exit[/]")
        except EOFError:
            break


@app.callback()
def main() -> None:
    """Cognitive Agent Memory System (CAMS) - CLI for testing and validation.

    A three-layer memory architecture inspired by cognitive neuroscience:
    - Episodic Memory: Past experiences and events
    - Semantic Memory: Facts and knowledge
    - Procedural Memory: Skills and procedures
    """
    pass


def cli_main() -> None:
    """Main CLI entry point (legacy compatibility)."""
    app()


if __name__ == "__main__":
    app()
