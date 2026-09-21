# fia-doc-explainer

Learning project. Python 3.13, uv, pydantic v2, pytest (asyncio_mode=auto),
ruff + mypy via pre-commit.

## Rules
- No new dependencies unless explicitly asked.
- Do not refactor code you were not asked to touch. Keep the diff minimal.
- No docstrings or comments unless they explain a non-obvious "why".
- Type annotations are required on all public functions and methods, tests included.
- Pydantic models only for data crossing a trust boundary (LLM response,
  HTTP response). Containers assembled in code are dataclasses.
- schemas.py imports nothing from this project. Dependency direction:
  providers/chain.py -> providers/base.py -> schemas.py
- pipeline.py must not import a specific vendor's SDK.
- Tests: pytest. No unittest.mock where an explicit fake is enough.
- If you think something beyond the task should be added or changed, do it and
  explain why — do not silently drop it.
