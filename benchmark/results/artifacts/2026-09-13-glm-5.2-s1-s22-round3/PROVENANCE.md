# Provenance: 2026-09-13 glm-5.2 S1–S22 round 3 artifacts

**Status: resolved (PR #228, 2026-09-15).** The raw round-3 artifacts (44 solver reports under
`noskill/` and `skill/`, 38 LLM-judge verdicts plus 6 keyword-judge outputs under `judge/`) were
committed in PR #228 and the reconstructed `aggregate.json` was verified against them.

History:

- `aggregate.json` (22 records) was first rebuilt on 2026-09-15 from the per-task paired-median table in
  `benchmark/results/validation-report-2026-09-13-glm-5.2-s1-s22-round3.md` (R3 zero / R3 skill columns),
  because the original artifacts had never entered any git ref (checked local branches, `origin`, and the
  author's fork). Verification: three-round paired medians recomputed from the three round aggregates equal
  the report's published values (zero-skill 2053, with-skill 2120, +67).
- The report's "Round 3 results" totals line (1895/2005) contradicted the per-task R3 columns (1995/2105),
  one task differing by 100/100. **Resolved in PR #228**: the totals line was a stale snapshot computed while
  the two S22 judge verdicts were absent, silently excluding S22 (100/100 both arms). The report's totals
  line was corrected to 1995/2105 in the same PR; the per-task table and the reconstructed aggregate were
  correct all along. Three-round paired medians (2053/2120, +67) are unaffected.
- Round 1/2 `aggregate.json` files were also repaired on 2026-09-15: S13/S14/S20 keyword-judge rows were
  restored from each round's sibling `keyword-scores.json`; repaired totals match the reports (2086/2120,
  2084/2120).
