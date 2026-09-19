# S2-negative-scan · Negative Scan (Zero Hits ≠ Compatible)

The agent scans the minimal dsh 0.1.1 legacy plugin under `/app/fixture/` read-only: the only hit is #3 (apiProxy → DSH-0.1.2-A1-01); the other six categories have zero hits; the report must argue "zero hits ≠ compatible" and state that real verification is still required, written under `/app/agent-output/S2-negative-scan/`.
Tests "identifying the single hit + arguing the zero-hit semantics + verification awareness + read-only discipline".
Task brief: [instruction.md](instruction.md); grading logic: [tests/judge.mjs](tests/judge.mjs).

- **Environment**: `node:24-bookworm` + git (the agent image retains its baseline; the verifier independently checks sealed hashes), dsh 0.1.2-alpha.2 installed globally for optional cold-boot verification, but this task's grading does not run dsh (static).
- **Verifier**: LLM: located Host break 40; six negative categories 20; inference limits 20; proposed verification 20. Sealed fixture changes → 0. Full/partial/fail/missing earn 100%/50%/0%/0% of each weight. The verifier runs separately, validates frozen fixture hashes and structured decisions and reasons, and writes scalar `reward.txt` plus `details.json`. Judge service failures exit nonzero without a reward.
- **Oracle**: run `harbor run -p benchmark/tasks/S2-negative-scan -a oracle` with judge configuration. This grades the reference report through the same LLM; a perfect score is not hardcoded.

```
environment/fixture/   # minimal plugin source (only the #3 apiProxy hit, plus planted zero-hit decoys)
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
