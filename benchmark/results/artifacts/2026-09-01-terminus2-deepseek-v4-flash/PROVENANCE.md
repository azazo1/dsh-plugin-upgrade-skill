# Provenance: 2026-09-01 terminus-2 + deepseek-v4-flash paired scores

`paired-scores.json` was extracted on **2026-09-15** from the per-task table in
`benchmark/results/validation-report-2026-09-01-terminus2-deepseek-v4-flash.md` (the only place the
per-run scores exist; no JSON was committed from this run).

- Protocol: terminus-2 harness (Harbor built-in minimal terminal agent), Harbor 0.22.0, `-k 3 -n 3`
  (3 attempts per task per condition), base commit `2de49059ec3178e23ea644cd78e7d20575b74745`,
  conditions `--skill skills/plugin-upgrade` vs no skill flag, original Harbor keyword verifiers,
  primary metric per-task median of 3 runs.
- 23 tasks × 2 arms, raw per-run scores transcribed verbatim from the report's `runs (with)` /
  `runs (no)` columns.
- **H8-fire-drill with-skill arm has only 2 runs** (`0.79, 0.60`): one trial ended in
  `VerifierTimeoutError`. The array length is recorded as-is.
- Known inconsistency: recomputed per-task median totals are no-skill **16.09** (exact match with the
  report) and with-skill **18.545** (report: 18.55). The 0.005 difference is entirely H8: the report
  displays the two-run median of `[0.79, 0.60]` as `0.70`, while the even-count median convention
  (mean of the two middle values) yields `0.695`. All other 22 tasks match the report exactly.
  `measure-paired-effect.mjs` validates this group with a 0.005 tolerance and computes with `0.695`.
