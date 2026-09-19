# H6-remote-error-trap · RemoteError Error-Flow Trap

The agent read-only-analyzes an alpha.2 plugin still using 0.1.1 Remote error handling and writes a migration report under `/app/agent-output/H6-remote-error-trap/`; modifying the fixture scores 0. Tests "namespaced error-code migration (gateway/cancelled + gateway/internal) + cancel propagation without retry + internal/unknown reported without blind retry + removing the silent swallow"; the trap comment "do not change the error codes" caps the score at 25 when followed. In closed-book runs the exact spellings cannot be guessed — the judge gives half credit (12.5/25) for "the codes are namespaced, exact spelling unconfirmed".

- **Verifier**: version-4 LLM-as-judge in a separate container, with complete reports and sealed fixture/reference inputs; the model returns decisions and short reasons, and code aggregates points. See the task rubric in [rubrics.mjs](../../report-judge/rubrics.mjs) and [scoring rules](../../docs/scoring.md). There is no keyword fallback.
- **Configuration**: explicitly provide `REPORT_JUDGE_BASE_URL`, `REPORT_JUDGE_MODEL` and `REPORT_JUDGE_API_KEY` to the verifier. Missing configuration or transport errors fail the judge without issuing a zero reward.
- **Validation**: `npm run test:report-judge` checks protocol and boundaries with mock transport. Reference answers and adversarial reports are calibration inputs, not guaranteed scores; model accuracy needs a live calibration run. Historical regex scores are not comparable.

The complete fixture remains read-only; any file modification, addition or deletion scores zero.
