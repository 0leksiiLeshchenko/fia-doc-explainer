# Run journal

## Verified API behaviour

- 2026-09-22, live check: Gemini accepts parameters_json_schema= built from a
  pydantic model, including anyOf for `str | None`. Verified before source_url
  was dropped from the schema; no nullable field remains in v1.
- 2026-09-23, live check: Anthropic accepts input_schema from the same pydantic
  model. claude-sonnet-5 responds — the escalation model ID is valid.

## Runs

(per-document observations go here)