from datetime import datetime
from typing import Literal

import typer
from rich.console import Console
from rich.panel import Panel

from hmem.core.memory_system import MemorySystem
from hmem.models import Conversation, Message

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
def chat() -> None:
    """Interactive chat mode with real LLM responses.

    Commands in chat mode:
        /remember        - Store current conversation to memory
        /consolidate     - Trigger memory consolidation
        /recall <query>  - Search and display memories
        /stats          - Show statistics
        /quit           - Exit chat mode

    Regular input will be sent to LLM and you get a response.
    Use /remember to manually save the conversation.
    """
    from hmem.agents.llm import LLMClient

    memory = get_memory_system()
    llm_client = LLMClient()
    session_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    console.print(
        Panel(
            "[bold cyan]H-Mem Interactive Chat with LLM[/]\n\n"
            "Commands:\n"
            "  [dim]/remember[/]        - Save conversation to memory\n"
            "  [dim]/consolidate[/]     - Trigger memory consolidation\n"
            "  [dim]/recall <query>[/]  - Search memories\n"
            "  [dim]/stats[/]          - Show statistics\n"
            "  [dim]/quit[/]           - Exit chat mode\n\n"
            "Chat naturally with the LLM. Use [bold]/remember[/] to save.\n"
            f"Session: {session_id}",
            title="Chat Mode",
            border_style="cyan",
        )
    )

    messages: list[Message] = []
    # Track conversation context for LLM
    llm_context: list[dict[str, str]] = []

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
                        console.print(f"[red]✗[/] Consolidation failed")
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

                else:
                    console.print(f"[yellow]Unknown command: /{cmd}[/]")

            else:
                # Regular chat - send to LLM
                user_message = Message(
                    role="user", content=user_input, timestamp=datetime.now()
                )
                messages.append(user_message)

                # Optionally retrieve relevant memories for context (skip if input is too short)
                recalled_memories = []
                if (
                    len(user_input.strip()) >= 2
                ):  # Avoid querying with very short inputs
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

                # Add context-enhanced prompt to conversation history
                llm_context.append({"role": "user", "content": context_prompt})

                # Get LLM response
                with console.status("[dim]Thinking...[/]"):
                    try:
                        from langchain_core.messages import (
                            HumanMessage,
                            SystemMessage,
                            BaseMessage,
                        )

                        lc_messages: list[BaseMessage] = [
                            SystemMessage(
                                content="You are a helpful AI assistant with access to memory. When relevant memories are provided, use them to give more personalized responses."
                            )
                        ]
                        # Add conversation history (last 5 exchanges to avoid context overflow)
                        for msg in llm_context:
                            lc_messages.append(HumanMessage(content=msg["content"]))

                        response = llm_client.llm.invoke(lc_messages)
                        assistant_content = str(response.content)

                    except Exception as e:
                        console.print(f"[red]Error getting LLM response:[/] {e}")
                        continue

                # Display assistant response
                console.print(f"\n[bold blue]Assistant>[/] {assistant_content}")

                # Store assistant message
                assistant_message = Message(
                    role="assistant",
                    content=assistant_content,
                    timestamp=datetime.now(),
                )
                messages.append(assistant_message)
                llm_context.append({"role": "assistant", "content": assistant_content})

                # Show hint about memories if any were found
                if recalled_memories:
                    console.print(
                        f"[dim](Used {len(recalled_memories)} memory/memories)[/]"
                    )

        except KeyboardInterrupt:
            console.print("\n[yellow]Use /quit to exit[/]")
        except EOFError:
            break


@app.callback()
def main() -> None:
    pass


def cli_main() -> None:
    """Main CLI entry point (legacy compatibility)."""
    app()


if __name__ == "__main__":
    app()
