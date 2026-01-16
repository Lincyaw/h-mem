"""Tools for ReAct agent.

Provides various tools that can be used by the agent during conversations.
"""

import subprocess
from typing import Annotated

from langchain_core.tools import tool


@tool
def bash(
    command: Annotated[str, "The bash command to execute"],
) -> str:
    """Execute a bash command and return the output.

    Use this tool to run shell commands for tasks like:
    - File operations (ls, cat, find, etc.)
    - System information (date, whoami, pwd, etc.)
    - Running scripts or programs

    Args:
        command: The bash command to execute

    Returns:
        The command output (stdout and stderr combined)
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]: {result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code]: {result.returncode}"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "[error]: Command timed out after 30 seconds"
    except Exception as e:
        return f"[error]: {e}"


@tool
def python_eval(
    code: Annotated[str, "Python code to evaluate"],
) -> str:
    """Evaluate Python code and return the result.

    Use this for quick calculations, data processing, or testing code snippets.
    Note: This runs in the current Python environment.

    Args:
        code: Python code to evaluate

    Returns:
        The result of the evaluation or error message
    """
    try:
        # Create a restricted globals dict
        allowed_globals = {
            "__builtins__": {
                "print": print,
                "len": len,
                "range": range,
                "list": list,
                "dict": dict,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "sum": sum,
                "min": min,
                "max": max,
                "sorted": sorted,
                "enumerate": enumerate,
                "zip": zip,
                "map": map,
                "filter": filter,
                "abs": abs,
                "round": round,
                "type": type,
                "isinstance": isinstance,
            }
        }
        result = eval(code, allowed_globals, {})
        return str(result)
    except SyntaxError:
        # Try exec for statements
        try:
            local_vars: dict = {}
            exec(code, allowed_globals, local_vars)
            if local_vars:
                return str(local_vars)
            return "(executed successfully, no return value)"
        except Exception as e:
            return f"[error]: {e}"
    except Exception as e:
        return f"[error]: {e}"


# Default tools to use in the agent
DEFAULT_TOOLS = [bash, python_eval]
