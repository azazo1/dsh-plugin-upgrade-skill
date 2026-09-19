# S1-static-scan · Static Touchpoint Scan (Read-Only)

The agent scans the dsh 0.1.1 legacy plugin under `/app/fixture/` read-only, maps the hits across the seven touchpoint categories to the change cards of the 0.1.1-rc.2 → 0.1.2-alpha.2 corridor, and writes the report to `/app/agent-output/S1-static-scan/`.
Tests "complete scan + accurate card mapping (incl. corridor folding A1-02 ↔ A2-01) + read-only discipline".
Task brief: [instruction.md](instruction.md); grading logic: [tests/judge.mjs](tests/judge.mjs).

- **Environment**: `node:24-bookworm` + git (the agent image retains its baseline; the verifier independently checks sealed hashes), no dsh installed (this task is static).
- **Verifier**: LLM: seven located touchpoints × 10; justified card mapping 20; scope/verification limits 10. Bare card lists earn no credit; sealed fixture changes → 0. Full/partial/fail/missing earn 100%/50%/0%/0% of each weight. The verifier runs separately, validates frozen fixture hashes and structured decisions and reasons, and writes scalar `reward.txt` plus `details.json`. Judge service failures exit nonzero without a reward.
- **Oracle**: run `harbor run -p benchmark/tasks/S1-static-scan -a oracle` with judge configuration. This grades the reference report through the same LLM; a perfect score is not hardcoded.

```
environment/fixture/   # legacy plugin source (fixture with all seven touchpoint categories planted as traps)
tests/                 # judge.mjs + packet.json + test.sh + Dockerfile
solution/              # reference report + solve.sh
```

Default task version: **4.0.0**, protocol `report-judge-v2`. Set
`REPORT_JUDGE_BASE_URL`, `REPORT_JUDGE_MODEL` and `REPORT_JUDGE_API_KEY` for the
verifier. See [semantic-judge setup](../../docs/report-judge-pilot.md).
The agent receives neither judge credentials nor sealed reference excerpts.
Edit the shared rubric/implementation in `benchmark/report-judge/`, run
`npm run sync:report-judge`, then `npm run test:report-judge`; CI rejects stale
standalone copies or packets. Historical keyword scores remain historical.
