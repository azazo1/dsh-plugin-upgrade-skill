# Provenance: 2026-09-01 Codex + gpt-5.6-terra paired scores

`paired-scores.json` was extracted on **2026-09-15** from the per-task tables in

- with-skill arm: `benchmark/results/validation-report-2026-09-01-codex-gpt-5.6-terra-all-22.md`
- no-skill arm: `benchmark/results/validation-report-2026-09-01-codex-gpt-5.6-terra-all-22-literal-no-skill.md`

No per-task JSON was committed from these runs; the report tables are the only source.

- Protocol: Codex 0.152.0 harness, Harbor 0.22.0, reasoning effort `xhigh`, same-day paired arms,
  n=1 per arm, legacy graders. The no-skill arm is a literal zero-skill run: no Harbor `--skill`,
  plus Codex-native skills disabled via `skills.include_instructions=false` and
  `skills.bundled.enabled=false` (all 22 trajectories audited, zero skill reads).
- H9 on both arms uses the compliant closed-book rerun rewards (with-skill 0.80 replacing 0.53;
  no-skill 0.50 replacing 0.70), as selected by the reports.
- **H8-fire-drill is excluded on both arms**: the sealed verifier timed out at 1200s and again at
  2400s on both sides; no reward is inferred from the candidate artifacts (never counted as zero).
  The paired analysis therefore covers 21 tasks.
- Validation: the 21 scored tasks sum to exactly 14.93 (no-skill) and 16.75 (with-skill), matching
  both reports.
- n=1 per arm: there is no per-task median; the task-level pairing is single-shot and the run
  pre-dates the benchmark's current graders.
