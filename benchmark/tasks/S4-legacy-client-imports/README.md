# S4-legacy-client-imports · Legacy Client Runtime Touchpoints

The agent read-only-scans the legacy dsh 0.1.1-rc.2 Web Client plugin in `/app/fixture/` and writes a migration report under `/app/agent-output/S4-legacy-client-imports/`; modifying the fixture scores 0. Tests "find all four cards (DSH-0.1.2-A1-25 / A1-26 / A1-27 / A1-30) + read-only discipline + no fabricated cards".

- **2026-08-31 calibration note**: in closed-book runs, agents fabricate "upgrade cards" (e.g. an apply-lifecycle replacement or inject-moved-to-manifest that never happened) — the semantic judge caps positive unsupported assertions at 70; a rejected bad example does not trigger the cap.
- **Environment**: `node:24-bookworm` + git (fixture baseline retained; read-only verification uses sealed hashes); dsh is not installed (static task).
- **Verifier**: LLM: runtime removal, registration identity, session content and connection face: 25 each. Positive unsupported lifecycle/inject claims cap at 70; rejecting bad advice does not. Full/partial/fail/missing earn 100%/50%/0%/0% of each weight. The verifier runs separately, validates frozen fixture hashes and structured decisions and reasons, and writes scalar `reward.txt` plus `details.json`. Judge service failures exit nonzero without a reward.
- **Oracle**: run `harbor run -p benchmark/tasks/S4-legacy-client-imports -a oracle` with judge configuration. This grades the reference report through the same LLM; a perfect score is not hardcoded.

```
environment/fixture/   # test material only (private:true, do not publish)
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
