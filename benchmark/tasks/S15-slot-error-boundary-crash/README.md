# S15 · Slot Error-Boundary Crash (vanishing dock chips)

Static, read-only. A lib-only Web plugin's dock-chip component references another
component's state variable (`busy`) inside a props object; the expression only evaluates
when the phase guard is false, so the bug ships latent — until the first release where a
user actually renders a chip, the ReferenceError fires inside the slot and the framework's
error boundary unmounts the entire entry. The user-visible symptom is "the chips are gone",
pointing at the newest feature diff instead of the pre-existing line.

Derived from a real 2026-09-03 dsh-paste-input v0.1.17 session (dangling `busy` in
AttachmentChips; surfaced by the hover-preview rollout).

- Type: static / read-only report
- **Verifier**: LLM: busy scope/trigger, slot boundary, evidence-based attribution/isolation, fix/hardening and data-present regression: 20 each. Accept grounded reports of inconsistent diff evidence. Criterion credit is full/half/zero; evaluator failures produce no reward.
- **Oracle**: run `harbor run -p benchmark/tasks/S15-slot-error-boundary-crash -a oracle` with judge configuration. This grades the reference report through the same LLM; a perfect score is not hardcoded.
- See `instruction.md` for the brief, `solution/SOLUTION.md` for the reference answer

Default task version: **4.0.0**, protocol `report-judge-v2`. Set
`REPORT_JUDGE_BASE_URL`, `REPORT_JUDGE_MODEL` and `REPORT_JUDGE_API_KEY` for the
verifier. See [semantic-judge setup](../../docs/report-judge-pilot.md).
The agent receives neither judge credentials nor sealed reference excerpts.
Edit the shared rubric/implementation in `benchmark/report-judge/`, run
`npm run sync:report-judge`, then `npm run test:report-judge`; CI rejects stale
standalone copies or packets. Historical keyword scores remain historical.
