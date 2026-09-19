# H12-remote-result-boundary-trap · RemoteResult control-flow boundary (Read-Only Markdown Diagnosis)

The agent diagnoses a client-plane helper whose alpha.2 error vocabulary is
**already migrated** (namespaced codes), but whose control-flow boundary is
wrong: it assumes ordinary unary failures reject into catch, reads
`result.value` without checking `result.ok`, discriminates with `instanceof
RemoteError`, and converts genuine assembly/programming rejects into a retry
loop. The trap: the colleague note at the top of the fixture — "the codes are
already migrated to alpha.2 and RemoteError is typed, so the safest pattern is
to handle all failures in catch".

**Relation to H6**: `H6-remote-error-trap` owns the error vocabulary / failure
policy axis (legacy → namespaced codes, cancellation propagation, internal /
unknown handling, silent-swallow avoidance). H12 deliberately starts after that
migration and grades a different axis: the resolved `RemoteResult` vs rejected
Promise boundary — `ok:false` vs catch, `.error` vs `.value`, and genuine
assembly/programming rejects as a separate exception boundary. Error-code
migration is **not** graded here.

Checkpoint references: card
[DSH-0.1.2-A2-02](../../../skills/plugin-upgrade/references/v0.1.2-alpha.2.md),
ledger [API-02](../../../skills/plugin-upgrade/references/api-migration-0.1.2-alpha.2.md),
and the [rollup "Remote call error flow"](../../../skills/plugin-upgrade/references/rollup-0.1.2.md)
section. Task statement in [instruction.md](instruction.md), grading logic in
[tests/judge.mjs](tests/judge.mjs).

- **Verifier**: version-4 LLM-as-judge in a separate container, with complete reports and sealed fixture/reference inputs; the model returns decisions and short reasons, and code aggregates points. See the task rubric in [rubrics.mjs](../../report-judge/rubrics.mjs) and [scoring rules](../../docs/scoring.md). There is no keyword fallback.
- **Configuration**: explicitly provide `REPORT_JUDGE_BASE_URL`, `REPORT_JUDGE_MODEL` and `REPORT_JUDGE_API_KEY` to the verifier. Missing configuration or transport errors fail the judge without issuing a zero reward.
- **Validation**: `npm run test:report-judge` checks protocol and boundaries with mock transport. Reference answers and adversarial reports are calibration inputs, not guaranteed scores; model accuracy needs a live calibration run. Historical regex scores are not comparable.

The complete fixture remains read-only; any file modification, addition or deletion scores zero.
