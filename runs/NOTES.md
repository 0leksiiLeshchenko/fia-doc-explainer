# Run journal

## Verified API behaviour

- 2026-09-22, live check: Gemini accepts parameters_json_schema= built from a
  pydantic model, including anyOf for `str | None`. Verified before source_url
  was dropped from the schema; no nullable field remains in v1.
- 2026-09-23, live check: Anthropic accepts input_schema from the same pydantic
  model. claude-sonnet-5 responds — the escalation model ID is valid.

## Runs

Primary model claude-haiku-4-5 throughout. Sections up to and including
v4-01*.json are all on tests/corpus/01-spanish-gp-car5-moving-under-braking.pdf;
later sections name their own document.

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

### v4-04*.json — 2 runs at d051a55, 04-mexico-gp-provisional-race-classification.pdf

What extraction does to the table: pdfplumber's extract_text() drops the column
separators, and the NAT column disappears entirely because nationality is drawn
as flag images with no text behind them. Rows carry different numbers of values
— the leader has no GAP and no INT — so nothing lines up positionally.

Predictions were written down before the runs. Scored:
 - would not flag — correct, no flag in either run;
 - would misattribute numbers — correct, but visible only in run 2;
 - would not invent nationality — correct, absent from both.

Run 1: accurate but partial. Five facts covering five of the twelve columns;
speed, points and the "on lap" column were simply left out. Nothing in the
output says that seven columns were dropped.

Run 2: wrong. "Max Verstappen finished first with 50 points, Lewis Hamilton
second with 50 points" — 50 is the ON column, the lap on which each set their
fastest lap. The real points are 25 and 18. Antonelli's 15 is right, taken from
PTS. The same sentence read one column for two drivers and a different one for
the third.

Mechanism: the model types columns by the format of their values, not by
position. Times, gaps and speeds have distinct shapes and were read correctly in
both runs. ON and PTS are both small integers — indistinguishable — and that is
the pair that broke. Flattening alone is not the failure; indistinguishable
column formats are.

Both guards failed at once. The heuristic cannot see this: the text is clean,
no replacement characters, no non-printables. The model did not flag, although
the flag criterion describes this case almost word for word. On this class of
document neither self-reported confidence nor the code heuristic works — which
is the answer to the question the README sets out to ask, and not the answer the
design expected.

The prompt was left unchanged on purpose. The criterion is correctly worded; the
model did not apply it to itself. Strengthening the wording would buy false
positives on tables that are fine. The real fix is page.extract_tables() with a
prompt of its own, which v1 excludes deliberately.

Methodological note: run 1 on its own looked like a clean pass, and a written
conclusion followed that the table hypothesis had been wrong. Run 2 reversed it.
A conclusion from a single run is unsafe in both directions, not only the
optimistic one.

### v4-05*.json — 2 runs at d051a55, 05-mexico-gp-race-director-competition-notes-v2.pdf

doc_type came back as "Competition Notes" — the first non-Stewards type in the
corpus, not forced into the Stewards shape.

No flag, and correctly so: the document is understood.

The worry that a document which decides nothing would break a schema built
around decisions did not materialise. key_facts reframed itself from "what was
decided" to "what is instructed", with no flag and no contortion. The field
descriptions turned out flexible enough; the concern was unfounded.

Nine pages, ~14.9k characters, roughly 4k tokens of input — the first real
length test. "State it briefly" did not over-compress: the explanation is long
where the document is long, so that instruction behaves conditionally rather
than absolutely.

The 3.0 s and 1.2 s marshalling thresholds are quoted from the text, not
invented.

Unasked-for behaviour: plain_explanation came back with markdown — bold section
headings that nothing in the prompt requests. Convenient for the Telegram stage,
noise in a terminal. Needs a decision in step 6: either forbid markup in the
field description or require it.

Not seen, as expected: the V1→V2 changes marked in magenta, and whatever the
circuit diagrams carry. Clean text, incomplete information, no guard — the same
family as the table case above.