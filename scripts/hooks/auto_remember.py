#!/usr/bin/env python3
"""
Auto-remember hook for h-mem.

This script is triggered by Claude Code hooks to automatically
memorize new conversation entries without explicit user action.

Usage:
    # Auto mode (called by hook on Stop event):
    python auto_remember.py

    # Manual mode (import specific session):
    python auto_remember.py import <session_file.jsonl> [--force] [--no-filter]

    # List available sessions:
    python auto_remember.py list [--limit N]

    # Show session info:
    python auto_remember.py info <session_file.jsonl>
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def load_config() -> dict:
    """Load hook configuration."""
    config_file = Path(__file__).parent / "config.json"
    default_config = {
        "enabled": True,
        "min_content_length": 100,
        "max_message_length": 2000,
        "batch_size": 10,
        "exclude_patterns": [],
        "importance_threshold": 3,
        "auto_filter": True,
    }
    if config_file.exists():
        with open(config_file) as f:
            user_config = json.load(f)
            default_config.update(user_config)
    return default_config


def get_latest_session_file() -> Path | None:
    """Find the most recently modified session JSONL file."""
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return None

    latest_file = None
    latest_mtime = 0

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            mtime = jsonl_file.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_file = jsonl_file

    return latest_file


def get_checkpoint_file() -> Path:
    """Get the checkpoint file path for tracking processed entries."""
    return Path.home() / ".claude" / "h-mem-checkpoint.json"


def load_checkpoint() -> dict:
    """Load the checkpoint data."""
    checkpoint_file = get_checkpoint_file()
    if checkpoint_file.exists():
        with open(checkpoint_file) as f:
            return json.load(f)
    return {"sessions": {}}


def save_checkpoint(checkpoint: dict) -> None:
    """Save the checkpoint data."""
    checkpoint_file = get_checkpoint_file()
    with open(checkpoint_file, "w") as f:
        json.dump(checkpoint, f, indent=2)


def extract_all_entries(session_file: Path) -> list[dict]:
    """Extract all conversation entries from a session file (ignoring checkpoint)."""
    entries = []

    with open(session_file) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if entry.get("type") in ["human", "assistant"]:
                    entries.append(entry)
            except json.JSONDecodeError:
                continue

    return entries


def extract_new_entries(session_file: Path, checkpoint: dict) -> list[dict]:
    """Extract entries that haven't been processed yet."""
    session_id = session_file.stem
    last_processed_line = checkpoint.get("sessions", {}).get(session_id, 0)

    new_entries = []
    current_line = 0

    with open(session_file) as f:
        for line in f:
            current_line += 1
            if current_line <= last_processed_line:
                continue

            try:
                entry = json.loads(line.strip())
                # Only process human and assistant messages
                if entry.get("type") in ["human", "assistant"]:
                    new_entries.append(entry)
            except json.JSONDecodeError:
                continue

    # Update checkpoint
    checkpoint.setdefault("sessions", {})[session_id] = current_line

    return new_entries


def should_exclude(text: str, patterns: list[str]) -> bool:
    """Check if text matches any exclusion pattern."""
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def extract_text_from_entry(entry: dict) -> str:
    """Extract text content from an entry."""
    content = entry.get("message", {})

    if isinstance(content, str):
        return content
    elif isinstance(content, dict):
        text = content.get("content", "")
        if isinstance(text, list):
            text_parts = []
            for block in text:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            return "\n".join(text_parts)
        return text if isinstance(text, str) else ""
    return str(content)


def format_conversation(entries: list[dict], config: dict) -> str:
    """Format entries into a conversation string."""
    lines = []
    max_len = config.get("max_message_length", 2000)
    exclude_patterns = config.get("exclude_patterns", [])

    for entry in entries:
        role = "User" if entry.get("type") == "human" else "Assistant"
        text = extract_text_from_entry(entry)

        if not text.strip():
            continue

        # Skip excluded patterns
        if should_exclude(text, exclude_patterns):
            continue

        # Truncate very long messages
        if len(text) > max_len:
            text = text[:max_len] + "..."

        lines.append(f"{role}: {text}")

    return "\n\n".join(lines)


def compute_content_hash(content: str) -> str:
    """Compute a hash of the content for deduplication."""
    return hashlib.md5(content.encode()).hexdigest()[:16]


def assess_importance(conversation: str, config: dict) -> bool:
    """Use LLM to assess if conversation is worth remembering."""
    if not config.get("auto_filter", True):
        return True

    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
        from hmem.agents.llm import LLMClient

        llm = LLMClient()
        result = llm.assess_memory_importance(
            content=conversation,
            context="Auto-captured conversation from Claude Code session",
        )

        threshold = config.get("importance_threshold", 3)
        return (
            result.get("should_remember", False)
            and result.get("importance", 0) >= threshold
        )

    except Exception as e:
        log_error(f"Error assessing importance: {e}")
        # If assessment fails, default to storing
        return True


def store_to_hmem(conversation: str, session_id: str) -> bool:
    """Store the conversation to h-mem."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
        from hmem.core.memory_system import MemorySystem
        from hmem.models import Conversation, Message

        ms = MemorySystem()

        # Create a conversation object
        messages = []
        for line in conversation.split("\n\n"):
            log_info(line)
            if line.startswith("User: "):
                messages.append(Message(role="user", content=line[6:]))
            elif line.startswith("Assistant: "):
                messages.append(Message(role="assistant", content=line[11:]))

        if not messages:
            return False

        conv = Conversation(
            session_id=f"auto-{session_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            messages=messages,
        )

        # Store to memory using remember() - synchronous API
        ms.remember(conv)
        return True

    except Exception as e:
        log_error(f"Error storing to h-mem: {e}")
        return False


def log_error(message: str) -> None:
    """Log error to file."""
    log_file = Path(__file__).parent / "auto_remember.log"
    timestamp = datetime.now().isoformat()
    with open(log_file, "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def log_info(message: str) -> None:
    """Log info to file."""
    log_file = Path(__file__).parent / "auto_remember.log"
    timestamp = datetime.now().isoformat()
    with open(log_file, "a") as f:
        f.write(f"[{timestamp}] INFO: {message}\n")


def list_sessions(limit: int = 20) -> list[tuple[Path, float, int]]:
    """List available session files sorted by modification time.

    Returns:
        List of (path, mtime, entry_count) tuples
    """
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return []

    sessions = []
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            mtime = jsonl_file.stat().st_mtime
            # Count entries
            entry_count = 0
            with open(jsonl_file) as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("type") in ["human", "assistant"]:
                            entry_count += 1
                    except json.JSONDecodeError:
                        continue
            sessions.append((jsonl_file, mtime, entry_count))

    # Sort by mtime descending
    sessions.sort(key=lambda x: x[1], reverse=True)
    return sessions[:limit]


def get_session_info(session_file: Path) -> dict:
    """Get detailed info about a session file."""
    if not session_file.exists():
        return {"error": f"File not found: {session_file}"}

    entries = extract_all_entries(session_file)
    checkpoint = load_checkpoint()
    session_id = session_file.stem
    last_processed = checkpoint.get("sessions", {}).get(session_id, 0)

    # Count lines
    total_lines = sum(1 for _ in open(session_file))

    # Get first and last message timestamps
    first_ts = None
    last_ts = None
    user_count = 0
    assistant_count = 0

    for entry in entries:
        ts = entry.get("timestamp")
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts
        if entry.get("type") == "human":
            user_count += 1
        else:
            assistant_count += 1

    return {
        "file": str(session_file),
        "session_id": session_id,
        "total_lines": total_lines,
        "total_entries": len(entries),
        "user_messages": user_count,
        "assistant_messages": assistant_count,
        "last_processed_line": last_processed,
        "unprocessed_lines": total_lines - last_processed,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
    }


def cmd_list(args: argparse.Namespace) -> None:
    """Handle 'list' command."""
    sessions = list_sessions(args.limit)

    if not sessions:
        print("No session files found.")
        return

    print(f"{'Session ID':<40} {'Modified':<20} {'Entries':>8}")
    print("-" * 70)

    for path, mtime, count in sessions:
        modified = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        print(f"{path.stem:<40} {modified:<20} {count:>8}")

    print(f"\nTotal: {len(sessions)} sessions")


def cmd_info(args: argparse.Namespace) -> None:
    """Handle 'info' command."""
    session_file = resolve_session_path(args.session)
    if session_file is None:
        print(f"Session not found: {args.session}")
        return

    info = get_session_info(session_file)

    if "error" in info:
        print(info["error"])
        return

    print(f"Session: {info['session_id']}")
    print(f"File: {info['file']}")
    print(f"Total lines: {info['total_lines']}")
    print(f"Conversation entries: {info['total_entries']}")
    print(f"  - User messages: {info['user_messages']}")
    print(f"  - Assistant messages: {info['assistant_messages']}")
    print(f"Last processed line: {info['last_processed_line']}")
    print(f"Unprocessed lines: {info['unprocessed_lines']}")
    if info['first_timestamp']:
        print(f"First message: {info['first_timestamp']}")
    if info['last_timestamp']:
        print(f"Last message: {info['last_timestamp']}")


def resolve_session_path(session: str) -> Path | None:
    """Resolve session identifier to full path.

    Args:
        session: Can be full path, session ID, or partial match

    Returns:
        Resolved Path or None if not found
    """
    # Try as direct path
    path = Path(session)
    if path.exists():
        return path

    # Try to find in projects directory
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return None

    # Search for matching session
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue

        # Exact match
        exact = project_dir / f"{session}.jsonl"
        if exact.exists():
            return exact

        # Partial match
        for jsonl_file in project_dir.glob("*.jsonl"):
            if session in jsonl_file.stem:
                return jsonl_file

    return None


def cmd_import(args: argparse.Namespace) -> None:
    """Handle 'import' command - import a specific session file."""
    session_file = resolve_session_path(args.session)
    if session_file is None:
        print(f"Session not found: {args.session}")
        return

    config = load_config()

    # Override config based on args
    if args.no_filter:
        config["auto_filter"] = False

    print(f"Importing session: {session_file.stem}")

    # Get entries based on --force flag
    if args.force:
        entries = extract_all_entries(session_file)
        print(f"  Force mode: processing all {len(entries)} entries")
    else:
        checkpoint = load_checkpoint()
        entries = extract_new_entries(session_file, checkpoint)
        print(f"  Processing {len(entries)} new entries")

    if not entries:
        print("  No entries to process.")
        return

    # Format conversation
    conversation = format_conversation(entries, config)

    if not conversation.strip():
        print("  No valid conversation content after filtering.")
        return

    print(f"  Conversation length: {len(conversation)} chars")

    # Assess importance (unless --no-filter)
    if config.get("auto_filter", True):
        print("  Assessing importance...")
        should_store = assess_importance(conversation, config)
        if not should_store:
            print("  Skipped: conversation deemed low importance.")
            if not args.force:
                # Still update checkpoint
                checkpoint = load_checkpoint()
                checkpoint.setdefault("sessions", {})[session_file.stem] = sum(
                    1 for _ in open(session_file)
                )
                save_checkpoint(checkpoint)
            return
        print("  Importance check passed.")
    else:
        print("  Skipping importance filter (--no-filter)")

    # Store to h-mem
    print("  Storing to h-mem...")
    session_id = session_file.stem
    success = store_to_hmem(conversation, session_id)

    if success:
        print(f"  Success! Stored {len(entries)} entries.")
        log_info(f"Manual import: {len(entries)} entries from {session_id}")

        # Update checkpoint
        if not args.force:
            checkpoint = load_checkpoint()
            checkpoint.setdefault("sessions", {})[session_id] = sum(
                1 for _ in open(session_file)
            )
            save_checkpoint(checkpoint)
    else:
        print("  Failed to store. Check auto_remember.log for details.")


def main_auto():
    """Main entry point for auto mode (hook trigger)."""
    config = load_config()

    # Check if enabled
    if not config.get("enabled", True):
        return

    # Find the latest session file
    session_file = get_latest_session_file()
    if not session_file:
        return

    # Load checkpoint
    checkpoint = load_checkpoint()

    # Extract new entries
    new_entries = extract_new_entries(session_file, checkpoint)

    if not new_entries:
        save_checkpoint(checkpoint)
        return

    # Format conversation
    conversation = format_conversation(new_entries, config)

    if not conversation.strip():
        save_checkpoint(checkpoint)
        return

    # Check minimum content threshold
    min_length = config.get("min_content_length", 100)
    if len(conversation) < min_length:
        save_checkpoint(checkpoint)
        return

    # Assess importance using LLM
    should_store = assess_importance(conversation, config)

    if not should_store:
        log_info(f"Skipped low-importance conversation ({len(new_entries)} entries)")
        save_checkpoint(checkpoint)
        return

    # Store to h-mem
    session_id = session_file.stem
    success = store_to_hmem(conversation, session_id)

    if success:
        log_info(
            f"Auto-remembered {len(new_entries)} entries from session {session_id}"
        )

    # Save checkpoint regardless of success
    save_checkpoint(checkpoint)


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="h-mem auto-remember: Store Claude Code conversations to memory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto mode (used by hook):
  python auto_remember.py

  # List recent sessions:
  python auto_remember.py list
  python auto_remember.py list --limit 50

  # Show session info:
  python auto_remember.py info <session_id>

  # Import a session:
  python auto_remember.py import <session_id>
  python auto_remember.py import /path/to/session.jsonl --force --no-filter
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list command
    list_parser = subparsers.add_parser("list", help="List available session files")
    list_parser.add_argument(
        "--limit", "-n", type=int, default=20, help="Number of sessions to show"
    )

    # info command
    info_parser = subparsers.add_parser("info", help="Show session info")
    info_parser.add_argument("session", help="Session ID or file path")

    # import command
    import_parser = subparsers.add_parser("import", help="Import a session to h-mem")
    import_parser.add_argument("session", help="Session ID or file path")
    import_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Import all entries, ignoring checkpoint",
    )
    import_parser.add_argument(
        "--no-filter",
        action="store_true",
        help="Skip importance filtering, store everything",
    )

    args = parser.parse_args()

    if args.command is None:
        # No command = auto mode (hook trigger)
        main_auto()
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "info":
        cmd_info(args)
    elif args.command == "import":
        cmd_import(args)


if __name__ == "__main__":
    main()
