# H4-tsbuildinfo-trap · Build Cache False-Positive Trap (Read-Only)

The agent diagnoses a "fully migrated" plugin that reports `MISSING_EXPORT resolveSessionPreset`
at build time while the source has zero references: it must recognize this as a false
positive from stale build artifacts/incremental cache (`lib/index.js` still imports the
deleted export, and `lib/tsconfig.tsbuildinfo` pins the old dependency graph); the
remediation is clean then rebuild with zero source changes. The trap: following the
DSH-0.1.2-A1-21 migration recipe to "fix" a non-existent reference (changing src scores 0
directly). Task statement in [instruction.md](instruction.md), grading logic in
[tests/judge.mjs](tests/judge.mjs).

- **Verifier**: version-4 LLM-as-judge in a separate container, with complete reports and sealed fixture/reference inputs; the model returns decisions and short reasons, and code aggregates points. See the task rubric in [rubrics.mjs](../../report-judge/rubrics.mjs) and [scoring rules](../../docs/scoring.md). There is no keyword fallback.
- **Configuration**: explicitly provide `REPORT_JUDGE_BASE_URL`, `REPORT_JUDGE_MODEL` and `REPORT_JUDGE_API_KEY` to the verifier. Missing configuration or transport errors fail the judge without issuing a zero reward.
- **Validation**: `npm run test:report-judge` checks protocol and boundaries with mock transport. Reference answers and adversarial reports are calibration inputs, not guaranteed scores; model accuracy needs a live calibration run. Historical regex scores are not comparable.

H4 permits deletion of original `lib/` artifacts, while edits/additions and changes outside `lib/` score zero. The judge retains the original artifact evidence after cleanup. A proposed clean/rebuild procedure is sufficient; the static fixture does not establish an executed successful build.
