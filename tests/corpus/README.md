# Test corpus

Real FIA documents, saved by hand. Synthetic PDFs stay in the tests only where
an artificially precise edge case is needed (heuristic thresholds).

Source is the FIA's own reference for the document — event, document number and
date — which identifies it unambiguously; the published URL pattern differs by
document category. Tests says why the document is in the corpus; what it
actually showed is in runs/NOTES.md.

| File | Type | Source | Tests | Saved |
|---|---|---|---|---|
| 01-spanish-gp-car5-moving-under-braking.pdf | Stewards Decision | Spanish GP 2026 — https://www.fia.com/system/files/decision-document/2026_spanish_grand_prix_-_infringement_-_car_5_-_moving_under_braking.pdf | The baseline document. A Warning, i.e. a signal whose later consequences the text does not state | 2026-09-23 |
| 02-mexico-gp-car16-left-track-lasting-advantage.pdf | Stewards Decision | Mexico City GP 2026, Doc 69, 01 Nov 2026 | States both a 10 s penalty guideline and a 5 s actual decision; the two must not be conflated. Two cars in the reasoning | 2026-11-02 |
| 03-mexico-gp-car30-technical-nonconformity.pdf | Stewards Decision | Mexico City GP 2026, Doc 57, 31 Oct 2026 | Technical rather than sporting jargon (MGU-K, "step down"), Qualifying session rather than Race, disqualification rather than a time penalty | 2026-11-02 |
| 04-mexico-gp-provisional-race-classification.pdf | Provisional Classification | Mexico City GP 2026, Doc 75, 01 Nov 2026 | A results table. Column separators are lost on extraction and the NAT column vanishes with the flag images; ON and PTS are both small integers and cannot be told apart. Confirmed failure mode, caught by neither guard | 2026-11-02 |
| 05-mexico-gp-race-director-competition-notes-v2.pdf | Competition Notes | Mexico City GP 2026, Doc 63, 01 Nov 2026 | Nine pages, no driver and no decision — the first non-Stewards type, and the first real length test. The V1→V2 diff is carried by colour and is invisible after extraction | 2026-11-02 |