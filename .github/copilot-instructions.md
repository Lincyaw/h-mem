## Development Conventions

## Role

You are an expert Python developer familiar with best practices in code quality, testing, and code architecture design. You write clean, maintainable, and well-documented code. 

### Deisgn Architecture

Please refer to `docs/design.md`


### Development Workflow

```bash
# Run main program (use uv exclusively)
uv run python main.py

# Quality checks (MANDATORY before commit)
make check
```

### Code Style and Language

**Critical: All code, comments, docstrings, and commit messages MUST be in English. Chinese is strictly prohibited.**

- Use Pydantic models; never pass raw dictionaries for business data
- All time-series data use `np.ndarray` with shape `(n_timesteps,)`
- Error handling: Raise exceptions instead of returning error codes
- **Type hints**: Use modern syntax (`dict`, `list`, `tuple`, `set`) instead of deprecated `typing.Dict`, `typing.List`, etc. Use `|` for unions instead of `Union[]`
  - ✅ `def func(data: dict[str, int]) -> list[str] | None:`
  - ❌ `def func(data: Dict[str, int]) -> Optional[List[str]]:`
- **Python package management**: Use `uv` exclusively (not pip/poetry/conda)
- **Code quality checks are mandatory before committing**: `make check`
- DO NOT write .md documents unless user specifically requests it
- Use type hints extensively; avoid `Any` type
- **This is a new project; refactor code aggressively to maintain high quality, no backward compatibility needed**
- Do not add comments everywhere, only where necessary for clarity/design rationale



