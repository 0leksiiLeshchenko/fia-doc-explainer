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

Run 1: accurate but partial. Of the table's twelve columns the summary drew on
four — position, driver, laps and gap. Entrant, time, interval and speed were
never mentioned. The fastest lap time and the lap it was set on do appear, but
taken from the document's own FASTEST LAP block at the foot of the page rather
than from the columns, and the DNF list likewise comes from the NOT CLASSIFIED
block. The model reaches for labelled blocks and prose, and touches the table
only where word adjacency makes the mapping safe. Nothing in the output says
anything was left out.

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

### v5-*.json — at b0a4610, plain_explanation asks for plain paragraphs

Why: v4-05 came back with bold section headings in plain_explanation. The note
there called that "convenient for the Telegram stage" — wrong. Telegram's
MarkdownV2 is its own dialect (single-asterisk bold, mandatory escaping of
. - ( ) ! and more), so the model's CommonMark would be rejected or shown raw.
Markup from the model suits neither channel. Decision: the field carries plain
text, and each renderer adds its own formatting.

The field description now asks for prose in paragraphs separated by a blank
line, gives multi-topic documents a way to separate topics (each paragraph
opens with a full sentence introducing it), states why (the program formats),
and names the forbidden symbols last. A bare "do not use markdown" was
rejected: a prohibition removes the means but not the need for structure.

#### 05 — 2 runs

Markup in 0 of 2: no **, no #, no list markers, no "Label:" lines. Every topic
is its own paragraph and opens with a sentence ("There are track limits at
three locations."). Output 3062 and 3475 bytes against 2647 and 2593 in v4.

#### 01 — 3 runs, against the 5 v4 runs

              chars (mean)   paragraphs
    v4 (5)    438–537 (498)  1,1,2,1,1
    v5 (3)    678–806 (734)  3,2,2

The ranges do not overlap, so the growth is the change, not sampling. What
fills it: the term "moved under braking" glossed in 3 of 3 (absent in v4-run11),
and the prohibition explained concretely instead of "the rule against
unsportsmanlike driving". Paragraphs split by meaning: incident, then decision.
Accepted as it is. The link between "paragraphs" and "fuller glosses" is a
correlation on three runs, not a finding.

"The Stewards reviewed video evidence" reappeared in 1 of 3. key_facts forbids
procedural detail, plain_explanation never did. Noise for now.

#### Filled-in facts — a count to keep

Plausible details the document does not state, no flag raised:
 - v5-05-run2: "may be penalised" — the text says "may be deemed to be going
   unnecessarily slowly" and "will normally be investigated" (§1);
 - v5-05-run2: "The Stewards will set a maximum time" — the text says teams
   "will be informed" after FP2 and names no one; v4-05-run1 made the same
   attribution;
 - v5-01-run3: Car 43 left the track "to avoid further damage" — the text says
   only that it "had to leave the track".
3 in 7 v5 runs, plus 1 in v4. The first breaks a rule the system prompt states
almost verbatim ("saying that a penalty followed"). Not attributable to the
format change. Input for step 8 and §8 of the README.

#### Measurement note

The first markup check ran before the runs existed and printed "clean":
`grep ... || echo clean` treats grep's exit 2 (error) like exit 1 (no match). A
check that reports success on a missing file is worse than none. Fixed by
testing the file first and reading grep's exit code via PIPESTATUS.

### 6446017 — minLength on FlagLowConfidence.reason

An empty reason now fails validation and becomes a malformed response, which
escalates. Visible to the model as minLength: 1 in the tool schema, so formally
a prompt change. No run: it affects only the flag path, which the corpus has
not triggered yet.

## Step 8 — corpus run, predictions (written before the run)

Eight documents, 3 runs each, 24 calls. Counted per run unless stated.
A filled-in fact is any detail absent from the document text, world
knowledge included; checked by hand against the PDF.

Across the corpus: primary answers 24 of 24; heuristic fires 0 of 24;
model flag 0 of 24 — including both tables, as in v4-04.

- 01 (Warning, moving under braking): no run states a later consequence of
  the Warning. At least 1 of 3 contains a filled-in fact (v5: 1 of 3).
- 02 (left track, 5 s): 3 of 3 give 5 s as the penalty imposed; no run
  presents the 10 s guideline as the decision.
- 03 (technical, MGU-K): MGU-K glossed in at least 2 of 3. No run places the
  disqualification in the Race instead of Qualifying.
- 04 (race classification): at least 1 of 3 attributes a points figure not
  taken from PTS. No run mentions nationality.
- 05 (Competition Notes, Mexico): at least 1 of 3 contains a filled-in fact
  in §1 — a penalty, or the Stewards setting the maximum time. Markup 0 of 3.
  No run mentions the V1→V2 changes.
- 06 (qualifying classification): at least 1 of 3 gives Leclerc a Q3 lap
  time (he set none: DNF). No run names a cause for his DNF (the document gives none) (the
  document gives none). Pole time correct 3 of 3 — it sits in a labelled
  block. No run mentions nationality.
- 07 (track limits, British): 3 of 3 give the 5 s penalty. No run presents
  the mechanical issue as mitigation. At least 1 of 3 mentions earlier
  warnings or a black-and-white flag — standard procedure, not in the text.
- 08 (Competition Notes, Chinese): same §1 wording as 05, so at least 1 of 3
  contains the same kind of filled-in fact. Markup 0 of 3.

## Step 8 — corpus run at 426637e (runs/corpus-426637e-20261103T155707Z)

Eight documents, 3 runs each, 24 calls. Models as in manifest.json: primary
claude-haiku-4-5, escalation claude-sonnet-5, quota fallback
gemini-3.5-flash-lite. The predictions above were committed before the run.

### Outcome

21 of 24 calls succeeded, every one answered by the primary model. Escalation
produced no successful answer. Three calls failed with exit 1: 01 run1,
01 run3, 08 run2. Heuristic fired 0 of 21, model flag 0 of 21.

### Predictions scored

18 of 23 held. The five misses:
 - "primary answers 24 of 24" — three calls failed outright;
 - 04: no run misattributed points; run3 gives 25/18/15, all from PTS;
 - 06: no run gave Leclerc a Q3 time; run1 states that 1:15.281 is his Q2 time;
 - 07: no run mentioned earlier warnings or a black-and-white flag;
 - 08: no filled-in fact in §1 in either successful run.

The pattern in the misses: errors were expected at the obvious traps, the model
held there and went wrong elsewhere (below). Predicting where a model will fill
in turned out much harder than predicting that it will.

### Malformed tool calls

All three failures are the same: key_facts arrived as a string, and the string
contains `<parameter name="key_f...` — the model wrote its own tool-call
syntax inside a JSON value. The same failure as v3-01-run7.

A fourth case passed validation: 07 run2 ends plain_explanation with
`</explanation>\n</invoke>`. A string is a valid string, so neither pydantic nor
the heuristic objects, and the text would have reached the reader. That makes
4 of 24 calls with a broken tool-call format, one of them silent.

"Escalation provider failed" means the primary failed first and the escalation
model then failed on the same input in the same way. The failures are
correlated, while escalation to a model of the same vendor assumes they are
independent — retrying on a replica that chokes on the same payload. The
primary's own error is lost: .err keeps only the last error in the chain.

01 now has 3 malformed responses in 14 runs across all versions (v3 one, this
run two). An observation, not yet a finding.

### Errors in clean text

11 of 21 successful answers contain at least one error, the 07 leak included.
No guard fired on any of them — the v4-04 conclusion, now on more data: the
errors live in clean text, the guards watch for broken text.

Filled in from general knowledge — not in the document:
 - 06, all 3 runs: the qualifying classification presented as the starting
   grid ("which means he will start the race first", "sets the starting
   grid"). The FIA publishes the grid as a separate document; penalties can
   make it differ. Invented qualifying rules on top: run1 "classified based on
   their fastest laps from Q2 or Q1, whichever was quicker", run2 "In Q1 and
   Q2, all drivers were on track and set times";
 - 05 run1: "may be investigated and penalized" — the same addition as
   v5-05-run2;
 - 05 run3: "the stewards may investigate them" — the text says "Incidents
   will normally be investigated" and names no one;
 - 01 run2: the Warning described as "a penalty for unsportsmanlike or
   reckless driving".

Misread — the text is there, the meaning is distorted:
 - 03 run3: disqualified "from the results of Q2 qualifying"; the decision
   covers the whole Provisional Qualifying Classification;
 - 04 run2: "Ten drivers were classified ... Four drivers finished the race
   but were not classified in the points" — 17 are classified, 7 outside the
   points;
 - 06 run3: Leclerc "did not earn a grid position in the top ten" — he is 10th;
 - 08 run3: practice starts — "stay to the left-hand side ... and not cross
   the white line"; the text forbids crossing the line on the left and puts
   the queue on the right. TSP 17 "moved 100 metres further back"; the text
   says "moved to 100m before the turn";
 - 05 run2: "blue flag signals"; the text says blue light panels.

### Tables

Column confusion by value format: 0 of 6 table runs, including 06, which has
three groups of same-format columns. On 04 it is now 1 case in 5 runs overall.
On tables the errors moved to counting rows (04 run2) and to domain rules
filled in from outside (06). The mechanism is not refuted, but it is rarer than
v4-04 suggested.

### Definition note

"Filled-in fact" was refined after the run. As written above it includes
world knowledge, which formally covers term glosses such as "MGU-K, a
motor-generator unit" — and those are what the prompt asks for. Working
definition from here on: a claim about the event, the decision or a procedure
that the text does not support; explaining a term does not count. Recorded
because the change was made after seeing the results.

### Decision

Next: strict tool use (`strict: true`) on the Anthropic tools, then the same
corpus again, 3 runs each, for a before/after comparison. Known obstacle:
strict schemas do not support minLength, and FlagLowConfidence.reason carries
one since 6446017; deciding what replaces it is part of the change. Open
question for the rerun: whether strict also stops a leak inside a string
value, as in 07 run2, or only the structural failures.
