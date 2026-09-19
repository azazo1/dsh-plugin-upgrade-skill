# Provenance: 2026-09-01 Codex + gpt-5.6-luna paired scores (sensitivity only)

`paired-scores.json` was extracted on **2026-09-15** from the per-task tables in

- with-skill arm: `benchmark/results/validation-report-2026-09-01-codex-gpt-5.6-luna-other-18.md`
- no-skill arm: `benchmark/results/validation-report-2026-09-01-codex-gpt-5.6-luna-other-18-no-injected-skill.md`

No per-task JSON was committed from these runs; the report tables are the only source.

- Protocol: Codex 0.152.0 harness, Harbor 0.22.0, reasoning effort `xhigh`, 18 tasks (the 2026-09-01
  snapshot did not include H8), n=1 per arm, legacy graders.
- **Contamination (why this group is sensitivity-only):** the no-skill arm is not a literal
  zero-skill run. Harbor mounted no skill, but Codex's native system-skill catalog stayed visible,
  and the H2-baseline-trap and H3-client-plane trajectories explicitly read the native
  `plugin-creator` skill and its references. Both are flagged `noskillContaminated` in the JSON.
  The decontaminated 16-task no-skill subset is **10.42/16 = 0.6513, diagnostic only** — it is not a
  substitute for rerunning H2/H3 with native skills disabled.
- Validation: the 18 tasks sum to exactly 12.42 (no-skill) and 15.15 (with-skill), matching both
  reports.
- n=1 per arm: single-shot pairing, no per-task median.
