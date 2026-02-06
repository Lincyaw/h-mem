from datetime import datetime
from pathlib import Path
from typing import Any, Literal
import atexit

import typer
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain.agents import create_agent
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.panel import Panel

from hmem.agents.tools import DEFAULT_TOOLS
from hmem.core.memory_system import MemorySystem
from hmem.models import Conversation, Message
from hmem.cli.inspector import MemoryInspector
import traceback


RoleType = Literal["system", "user", "assistant"]

app = typer.Typer(
    name="hmem",
    help="Cognitive Agent Memory System (CAMS) - CLI for testing and validation",
    add_completion=False,
)
console = Console()

# Global memory system instance (lazy initialization)
_memory_system: MemorySystem | None = None

# Default config file path
DEFAULT_CONFIG_PATH = "config/memory.yaml"


def _cleanup_memory_system() -> None:
    """Cleanup function to properly close Neo4j connection on exit."""
    global _memory_system
    if _memory_system is not None:
        try:
            _memory_system._store.close()
        except Exception:
            pass
        _memory_system = None


# Register cleanup handler
atexit.register(_cleanup_memory_system)


def get_memory_system() -> MemorySystem:
    """Get or create the global memory system instance."""
    global _memory_system
    if _memory_system is None:
        with console.status("[bold green]Initializing memory system...[/]"):
            # Load from config file if exists
            if Path(DEFAULT_CONFIG_PATH).exists():
                _memory_system = MemorySystem.from_config(DEFAULT_CONFIG_PATH)
            else:
                _memory_system = MemorySystem()
    return _memory_system


@app.command()
def chat() -> None:
    """Interactive chat mode with ReAct agent.

    Commands in chat mode:
        /remember        - Store current conversation to memory
        /consolidate     - Trigger memory consolidation
        /recall <query>  - Search and display memories
        /stats          - Show statistics
        /quit           - Exit chat mode

    The agent can use tools (bash, python_eval) to help answer questions.
    Use /remember to manually save the conversation.
    """
    from langchain.chat_models import init_chat_model

    memory = get_memory_system()

    # Initialize LLM with tool support
    llm = init_chat_model(
        memory.config.llm.model,
        temperature=memory.config.llm.temperature,
    )

    # Create ReAct agent with tools
    system_prompt = """You are a helpful AI assistant with access to tools and memory.
When relevant memories are provided, use them to give more personalized responses.
You have access to the following tools:
- bash: Execute shell commands
- python_eval: Evaluate Python expressions

Use tools when needed to help answer questions or complete tasks."""

    agent: Any = create_agent(llm, DEFAULT_TOOLS, system_prompt=system_prompt)

    session_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    console.print(
        Panel(
            "[bold cyan]H-Mem Interactive Chat with ReAct Agent[/]\n\n"
            "Commands:\n"
            "  [dim]/remember[/]        - Save conversation to memory\n"
            "  [dim]/consolidate[/]     - Trigger memory consolidation\n"
            "  [dim]/recall <query>[/]  - Search memories\n"
            "  [dim]/stats[/]          - Show statistics\n"
            "  [dim]/debug[/]          - Show data at each stage\n"
            "  [dim]/reset[/]          - Clear all data (for testing)\n"
            "  [dim]/quit[/]           - Exit chat mode\n\n"
            "Tools available: [green]bash[/], [green]python_eval[/]\n"
            f"Session: {session_id}\n\n"
            "[dim]Tip: Use ↑/↓ arrows to navigate history[/]",
            title="Chat Mode (ReAct Agent)",
            border_style="cyan",
        )
    )

    messages: list[Message] = []
    # Track conversation context for agent (LangChain message format)
    agent_messages: list[HumanMessage | AIMessage | ToolMessage | SystemMessage] = []

    # Setup prompt_toolkit with history and auto-completion
    history_file = Path.home() / ".hmem_history"
    command_completer = WordCompleter(
        ["/remember", "/consolidate", "/recall", "/stats", "/reset", "/quit", "/q"],
        ignore_case=True,
    )
    prompt_session: PromptSession[str] = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=command_completer,
    )

    while True:
        try:
            user_input = prompt_session.prompt("You> ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                parts = user_input[1:].split(maxsplit=1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if cmd == "quit" or cmd == "q":
                    console.print("\n[yellow]Goodbye![/]")
                    break

                elif cmd == "remember":
                    if not messages:
                        console.print("[yellow]No conversation to save yet[/]")
                        continue
                    conversation = Conversation(
                        session_id=session_id, messages=messages
                    )
                    result_session_id = memory.remember(conversation)
                    console.print(
                        f"[green]✓[/] Saved {len(messages)} messages to memory (session: {result_session_id})"
                    )

                elif cmd == "consolidate":
                    with console.status("[dim]Consolidating memories...[/]"):
                        result = memory.consolidate(session_id)

                    if result.success:
                        console.print(
                            f"[green]✓[/] Consolidation complete: "
                            f"{result.stored_events} events, "
                            f"{result.updated_facts} facts updated, "
                            f"{result.conflicts_resolved} conflicts resolved"
                        )
                    else:
                        console.print("[red]✗[/] Consolidation failed")
                        if result.errors:
                            for error in result.errors[:3]:  # Show first 3 errors
                                console.print(f"  [dim]• {error}[/]")

                elif cmd == "recall":
                    if not args:
                        console.print("[yellow]Usage: /recall <query>[/]")
                        continue

                    with console.status("[dim]Searching...[/]"):
                        results = list(memory.recall(args, limit=5))

                    if results:
                        console.print(f"\n[cyan]Found {len(results)} memories:[/]")
                        for i, mem in enumerate(results, 1):
                            score_color = (
                                "green"
                                if mem.score > 0.7
                                else "yellow"
                                if mem.score > 0.4
                                else "red"
                            )
                            console.print(
                                f"  {i}. [{score_color}]{mem.score:.2f}[/] [{mem.source}] {mem.content[:100]}..."
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

                elif cmd == "debug":
                    # Show data at each stage for debugging
                    console.print("\n[bold cyan]== Debug: Memory System Status ==[/]\n")

                    # Neo4j (Unified Store)
                    console.print("[yellow]Neo4j (Unified Store)[/]")
                    try:
                        stats_data = memory._store.get_stats()
                        console.print(
                            f"   Conversations: {stats_data.get('conversations', 0)}"
                        )
                        console.print(f"   Events: {stats_data.get('events', 0)}")
                        console.print(
                            f"   Facts: {stats_data.get('facts', 0)} (active: {stats_data.get('active_facts', 0)})"
                        )
                        console.print(
                            f"   Principles: {stats_data.get('principles', 0)}"
                        )
                        console.print(f"   Skills: {stats_data.get('skills', 0)}")
                    except Exception as e:
                        traceback.print_exc()
                        console.print(f"   [red]Error: {e}[/]")

                elif cmd == "reset":
                    # Confirm before clearing
                    confirm = (
                        prompt_session.prompt("[yellow]Clear ALL data? (yes/no): [/]")
                        .strip()
                        .lower()
                    )
                    if confirm != "yes":
                        console.print("[dim]Cancelled[/]")
                        continue

                    console.print("\n[bold red]Clearing all data...[/]")

                    # Clear Neo4j (unified store)
                    try:
                        deleted = memory._store.clear()
                        console.print(f"   [green]✓[/] Neo4j: {deleted} nodes")
                    except Exception as e:
                        console.print(f"   [red]✗[/] Neo4j: {e}")

                    console.print("\n[green]✓ All data cleared![/]")

                else:
                    console.print(f"[yellow]Unknown command: /{cmd}[/]")

            else:
                # Regular chat - send to ReAct agent
                user_message = Message(
                    role="user", content=user_input, timestamp=datetime.now()
                )
                messages.append(user_message)

                # Optionally retrieve relevant memories for context
                recalled_memories = []
                if len(user_input.strip()) >= 2:
                    recalled_memories = list(memory.recall(user_input, limit=3))

                # Build context with memories
                context_prompt = user_input
                if recalled_memories:
                    memory_context = "\n".join(
                        [
                            f"[Memory {i + 1}]: {mem.content}"
                            for i, mem in enumerate(recalled_memories)
                        ]
                    )
                    context_prompt = (
                        f"Relevant memories:\n{memory_context}\n\nUser: {user_input}"
                    )

                # Add to agent messages
                agent_messages.append(
                    HumanMessage(content=[{"type": "text", "text": context_prompt}])
                )

                # Invoke ReAct agent
                with console.status("[dim]Thinking...[/]"):
                    try:
                        agent_result = agent.invoke({"messages": agent_messages})
                        response_messages = agent_result["messages"]

                        # Process response messages and display tool calls
                        assistant_content = ""
                        for msg in response_messages[len(agent_messages) :]:
                            if isinstance(msg, AIMessage):
                                # Check for tool calls
                                if msg.tool_calls:
                                    for tool_call in msg.tool_calls:
                                        console.print(
                                            f"\n[dim magenta]⚙ Tool:[/] [magenta]{tool_call['name']}[/]"
                                        )
                                        args_str = str(tool_call["args"])
                                        if len(args_str) > 100:
                                            args_str = args_str[:100] + "..."
                                        console.print(f"[dim]  Args: {args_str}[/]")
                                if msg.content:
                                    assistant_content = str(msg.content)
                            elif isinstance(msg, ToolMessage):
                                tool_output = str(msg.content)
                                if len(tool_output) > 200:
                                    tool_output = tool_output[:200] + "..."
                                console.print(f"[dim green]  Result: {tool_output}[/]")

                        # Update agent messages with all new messages
                        agent_messages = agent_result["messages"]

                    except Exception as e:
                        console.print(f"[red]Error:[/] {e}")
                        traceback.print_exc()
                        continue

                # Display final assistant response
                if assistant_content:
                    console.print(f"\n[bold blue]Assistant>[/] {assistant_content}")

                    # Store assistant message
                    assistant_message = Message(
                        role="assistant",
                        content=assistant_content,
                        timestamp=datetime.now(),
                    )
                    messages.append(assistant_message)

                # Show memories used
                if recalled_memories:
                    mem_lines = []
                    for i, mem in enumerate(recalled_memories, 1):
                        score_color = (
                            "green"
                            if mem.score > 0.7
                            else "yellow"
                            if mem.score > 0.4
                            else "red"
                        )
                        mem_lines.append(
                            f"[{score_color}]{i}. [{mem.source}] {mem.score:.2f}[/]\n   {mem.content}"
                        )
                    console.print(
                        Panel(
                            "\n".join(mem_lines),
                            title=f"[dim]Memories ({len(recalled_memories)})[/]",
                            border_style="dim",
                        )
                    )

        except KeyboardInterrupt:
            console.print("\n[yellow]Use /quit to exit[/]")
        except EOFError:
            break


@app.command()
def graph(
    entity: str = typer.Argument(..., help="Entity name to visualize"),
    depth: int = typer.Option(2, "--depth", "-d", help="Traversal depth (1-5)"),
) -> None:
    """Show entity's relationship graph as ASCII tree.

    Example:
        hmem graph Alice --depth 2

    Output:
        Alice
        ├── PREFERS → DarkMode (weight: 0.90, v1)
        ├── LIVES_IN → Beijing (weight: 1.00, v1)
        └── WORKS_AT → TechCorp (weight: 0.80, v2)
    """
    memory = get_memory_system()
    inspector = MemoryInspector(memory)

    with console.status(f"[dim]Loading graph for '{entity}'...[/]"):
        result = inspector.show_graph(entity, depth=min(max(depth, 1), 5))

    console.print(f"\n[cyan]Entity Graph:[/]\n{result}")


@app.command()
def trace(
    session_id: str = typer.Argument(..., help="Session ID to trace"),
) -> None:
    """Show consolidation trace for a session.

    Displays the complete processing history including:
    - Event log entries
    - Episodic memories
    - Semantic triples
    - Induced principles

    Example:
        hmem trace session_20240115_123456
    """
    memory = get_memory_system()
    inspector = MemoryInspector(memory)

    with console.status(f"[dim]Tracing session '{session_id}'...[/]"):
        result = inspector.trace_consolidation(session_id)

    console.print(f"\n{result}")


@app.command()
def stats() -> None:
    """Show comprehensive memory system statistics.

    Displays counts and health status for the unified Neo4j store:
    - Conversations
    - Events
    - Facts (semantic triples)
    - Principles
    - Skills
    - Event log
    """
    memory = get_memory_system()
    inspector = MemoryInspector(memory)

    with console.status("[dim]Gathering statistics...[/]"):
        stats_data = inspector.get_memory_stats()

    console.print("\n[bold cyan]Memory System Statistics[/]\n")

    # Episodic
    episodic = stats_data.get("episodic", {})
    if "error" in episodic:
        console.print(f"[red]Episodic:[/] Error - {episodic['error']}")
    else:
        console.print(f"[green]Episodic:[/] {episodic.get('total_count', 0)} memories")

    # Semantic
    semantic = stats_data.get("semantic", {})
    if "error" in semantic:
        console.print(f"[red]Semantic:[/] Error - {semantic['error']}")
    else:
        console.print(
            f"[green]Semantic:[/] {semantic.get('total_triples', 0)} triples "
            f"({semantic.get('superseded_triples', 0)} superseded)"
        )

    # Skills
    skill = stats_data.get("skill", {})
    if "error" in skill:
        console.print(f"[red]Skills:[/] Error - {skill['error']}")
    else:
        console.print(f"[green]Skills:[/] {skill.get('total_skills', 0)} templates")

    # Event log
    event_log = stats_data.get("event_log", {})
    if isinstance(event_log, dict) and "error" in event_log:
        console.print(f"[red]Event Log:[/] Error - {event_log['error']}")
    elif isinstance(event_log, dict):
        console.print(
            f"[green]Event Log:[/] {event_log.get('total_entries', 0)} entries "
            f"across {event_log.get('sessions', 0)} sessions"
        )
    else:
        console.print(f"[green]Event Log:[/] {event_log}")

    console.print(f"\n[dim]Timestamp: {stats_data.get('timestamp', 'N/A')}[/]")


@app.command()
def explain(
    memory_id: str = typer.Argument(..., help="Memory ID to explain"),
) -> None:
    """Explain a memory's provenance and usage history.

    Shows the derivation chain and any memories derived from this one.

    Example:
        hmem explain evt_abc123
    """
    memory = get_memory_system()
    inspector = MemoryInspector(memory)

    result = inspector.explain_memory(memory_id)
    console.print(f"\n{result}")


@app.command()
def health() -> None:
    """Check system health status.

    Returns overall health status and key metrics.
    """
    memory = get_memory_system()

    with console.status("[dim]Checking health...[/]"):
        health_data = memory.health()

    status = health_data.get("status", "unknown")
    status_color = (
        "green" if status == "healthy" else "yellow" if status == "degraded" else "red"
    )

    console.print("\n[bold cyan]System Health[/]\n")
    console.print(f"Status: [{status_color}]{status}[/{status_color}]")
    console.print(f"Version: {health_data.get('version', 'unknown')}")
    console.print(f"Episodic Count: {health_data.get('episodic_count', 0)}")
    console.print(f"Semantic Count: {health_data.get('semantic_count', 0)}")
    console.print(f"Skill Count: {health_data.get('skill_count', 0)}")
    console.print(f"Retrieval P95: {health_data.get('retrieval_p95_ms', 0):.1f}ms")


@app.command()
def serve(
    port: int = typer.Option(8080, "--port", "-p", help="Port to listen on"),
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
    dev: bool = typer.Option(False, "--dev", help="Enable CORS + GraphiQL"),
) -> None:
    """Start the web UI server.

    In dev mode, enables CORS for localhost:5173 (Vite dev server) and GraphiQL IDE.

    Examples:
        hmem serve --port 8080
        hmem serve --dev --port 8080
    """
    import uvicorn

    from hmem.api.app import create_app

    console.print(
        f"\n[bold cyan]h-mem Web UI[/] starting on [green]http://{host}:{port}[/]"
    )
    if dev:
        console.print("[yellow]Development mode:[/] CORS enabled, GraphiQL at /graphql")
    console.print()

    app_instance = create_app(dev=dev)
    uvicorn.run(app_instance, host=host, port=port)


@app.command(name="import")
def import_conversations(
    path: str = typer.Argument(
        ...,
        help="Path to JSONL file or project directory containing JSONL files",
    ),
    all_projects: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Import all projects from ~/.claude/projects",
    ),
) -> None:
    """Import Claude Code conversations into h-mem memory system.

    This uses LLM to extract events, facts, tags, and outcomes from conversations.

    Examples:
        # Import single JSONL file
        hmem import ~/.claude/projects/-home-nn-workspace-h-mem/abc123.jsonl

        # Import all files from a project directory
        hmem import ~/.claude/projects/-home-nn-workspace-h-mem/

        # Import all projects
        hmem import ~/.claude/projects --all
    """
    from pathlib import Path

    from hmem.cli.importer import ClaudeCodeImporter
    from hmem.core.conversation_processor import ConversationProcessor

    memory = get_memory_system()

    # Use the processor from memory system (it has the properly configured encoder)
    processor = ConversationProcessor(
        store=memory._store,
        encoder=memory._encoder,
    )

    importer = ClaudeCodeImporter(processor)
    target_path = Path(path).expanduser()

    if not target_path.exists():
        console.print(f"[red]Error:[/] Path not found: {target_path}")
        raise typer.Exit(1)

    def progress_callback(current: int, total: int) -> None:
        console.print(f"  Processing {current}/{total}...")

    console.print(f"\n[bold cyan]Importing conversations from:[/] {target_path}\n")

    if all_projects:
        # Import all projects
        result = importer.import_all(
            target_path,
            on_progress=lambda name, curr, total: console.print(
                f"  Project {curr}/{total}: {name}"
            ),
        )
    elif target_path.is_file():
        # Import single file only
        conversations = importer.parse_jsonl(target_path)
        if conversations:
            # Process just this file's conversations, not the whole directory
            batch_result = processor.process_batch(conversations)
            # Build result manually for single file
            from hmem.cli.importer import ImportResult

            result = ImportResult()
            result.total_files = 1
            result.total_conversations = len(conversations)
            result.total_messages = sum(len(c.messages) for c in conversations)
            result.batch_result = batch_result
        else:
            console.print("[yellow]No conversations found in file[/]")
            return
    else:
        # Import project directory
        result = importer.import_project(target_path, progress_callback)

    # Show results
    console.print("\n[bold green]Import complete![/]\n")
    console.print(f"  Files processed: {result.total_files}")
    console.print(f"  Conversations: {result.total_conversations}")
    console.print(f"  Messages: {result.total_messages}")

    if result.batch_result:
        console.print(f"  Entities extracted: {result.batch_result.total_entities}")
        console.print(f"  Attributes extracted: {result.batch_result.total_attributes}")
        console.print(f"  Processes extracted: {result.batch_result.total_processes}")
        if result.batch_result.principles_induced:
            console.print(
                f"  Principles induced: {result.batch_result.principles_induced}"
            )

    if result.errors:
        console.print(f"\n[yellow]Warnings ({len(result.errors)}):[/]")
        for err in result.errors[:5]:
            console.print(f"  - {err}")
        if len(result.errors) > 5:
            console.print(f"  ... and {len(result.errors) - 5} more")

    # Explicitly close Neo4j connection and cleanup to prevent SIGSEGV during exit
    import gc

    # Clear global reference before closing
    global _memory_system

    try:
        memory._store.close()
    except Exception:
        pass

    # Clear the global reference
    _memory_system = None

    # Force garbage collection to clean up any lingering references
    gc.collect()


@app.callback()
def main() -> None:
    pass


def cli_main() -> None:
    """Main CLI entry point (legacy compatibility)."""
    app()


if __name__ == "__main__":
    app()
