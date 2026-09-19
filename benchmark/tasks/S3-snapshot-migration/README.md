# S3-snapshot-migration · Snapshot Read-Surface Migration Assessment (Read-Only)

The agent assesses read-only the browser pet plugin from the 0.1.1-rc.1 era under `/app/fixture/`, mapping the snapshot read surface (flat `ConversationSnapshot` → views/legacy projection, the `useSession` lifecycle seat, the `@deepseek-ai/cordis` type-import replacement, `slots.inject` registration) to DSH-0.1.2-A1-03, and writes the report under `/app/agent-output/S3-snapshot-migration/`.
Task brief: [instruction.md](instruction.md); grading logic: [tests/judge.mjs](tests/judge.mjs).

- **Environment**: `node:24-bookworm` + git (the agent image retains its baseline; the verifier independently checks sealed hashes), no dsh installed (this task is static).
- **Verifier**: LLM: chat projection, Session lifecycle, type/inject ownership, slot registration, and justified mapping/plan: 20 each. Sealed fixture changes → 0. Full/partial/fail/missing earn 100%/50%/0%/0% of each weight. The verifier runs separately, validates frozen fixture hashes and structured decisions and reasons, and writes scalar `reward.txt` plus `details.json`. Judge service failures exit nonzero without a reward.
- **Oracle**: run `harbor run -p benchmark/tasks/S3-snapshot-migration -a oracle` with judge configuration. This grades the reference report through the same LLM; a perfect score is not hardcoded.

```
environment/fixture/   # 0.1.1 snapshot-surface browser plugin (trimmed from real pre-migration code)
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
