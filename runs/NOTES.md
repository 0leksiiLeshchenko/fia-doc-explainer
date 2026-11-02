# Run journal

## Verified API behaviour

- 2026-09-22, live check: Gemini accepts parameters_json_schema= built from a
  pydantic model, including anyOf for `str | None`. Verified before source_url
  was dropped from the schema; no nullable field remains in v1.
- 2026-09-23, live check: Anthropic accepts input_schema from the same pydantic
  model. claude-sonnet-5 responds — the escalation model ID is valid.

## Runs

All runs below are on tests/corpus/01-spanish-gp-car5-moving-under-braking.pdf,
primary model claude-haiku-4-5.

### baseline/01.json — before prompts.py existed

No system prompt, no field descriptions, the raw PDF text as the user message.
The explanation paraphrased the document in its own language: "moving under
braking" used three times without ever saying why it is forbidden, "black/white
flag" explained by another piece of jargon, nothing about what the decision
means for the driver. key_facts held 7 items, two of them procedural — appeal
rights and which evidence was reviewed.

The schema and tool use worked on the first try. The limit was the prompt that
did not exist, and only a real document showed it.

### v2-01*.json — 4 runs, after the prompts commit

The prohibition is explained, not only the manoeuvre. Jargon carries a gloss,
and in one run the model glossed "moving under braking" by itself — a term that
appears nowhere in the prompt. It picked up the pattern rather than a list,
which is why the examples were cut down to one.

Procedural boilerplate gone from all four. No ungrounded numbers — but this
document gave no occasion to invent any, so that guard is barely tested.

doc_type identical across all four runs ("Stewards Decision"). The baseline,
with no field description on that field, said "Stewards Decision Document".

Regression: 0 of 4 runs named the Grand Prix or the date. Repeated to tell a
prompt effect from sampling noise; it was the prompt.

### v3-01*.json — 3 runs, with the event requirement added

Runs 5 and 6: the event context is back. Run 7 failed — the model returned
key_facts as a string instead of a list, on the primary and the escalation
model both, and its content was procedural boilerplate. The file is 0 bytes
because the message went to stderr:

    No provider can generate proper doc summary: "Schema validation failed for
    tool 'provide_summary': 1 validation error for ProvideSummary / key_facts /
    Input should be a valid list"

What it exposed: both providers were turning a ValidationError into a
low-confidence flag, merging "the model did not understand the document" with
"the model returned malformed JSON". Those are different signals and the README
is meant to compare one of them against the code heuristic, so the merge would
have corrupted that measurement. Fixed in its own commit.

Version note: these three runs were made with the event requirement applied in
the working tree but not committed, and before plain_explanation was reworded.
They correspond to no single commit — a run is only attributable if the prompt
it used was committed first.

### v4-01*.json — 5 runs at d051a55, after the rewording and the ProviderResponseError fix

Event context present in all 5. Together with v3 that is 7 of 7 since the
key_facts change, against 0 of 4 before it. Output size 1179–1411 bytes: the
event requirement does not fight the "state it briefly" instruction.

No malformed responses in these 5 runs, and this proves nothing about the
failure rate. Zero events in five trials puts the upper bound somewhere around
60%; a true rate of 10% would have shown zero here more than half the time. The
rate gets measured on the corpus, not by repeating one document.

First set of runs made from a committed state, so they have a prompt version.