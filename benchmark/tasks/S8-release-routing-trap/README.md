# S8-release-routing-trap · Release routing trap (read-only)

A consumer on an older dsh runtime hits a two-stage install failure on a community plugin:
first the README-pinned tag cannot resolve on the public mirror, then the "fixed" newest tag
installs but the plugin crashes with `useConversation is not a function`. The agent must
diagnose **two distinct root causes** (tag distribution defect vs forward-incompatible version
routing) from the static evidence pack, give the consumer a working install command under the
production-freeze constraint, and the maintainer-side fix. 题面见
[instruction.md](instruction.md)，判分逻辑见 [tests/judge.mjs](tests/judge.mjs)。

- **Environment**: `node:24-bookworm` + git (fixture baseline-committed for the read-only gate); no dsh (static task).
- **Verifier**: [LLM-as-judge by default](../../docs/report-judge-pilot.md), task version `4.0.0`.
  A sealed fixture hash enforces read-only work. The separate verifier reads the report,
  judges each criterion with a verdict and short reason, and deterministically aggregates the score.
  Configure `REPORT_JUDGE_BASE_URL`, `REPORT_JUDGE_MODEL` and `REPORT_JUDGE_API_KEY`
  only for the verifier. Missing reports score 0; evaluator failures leave no reward.
- **Oracle**: `harbor run -p benchmark/tasks/S8-release-routing-trap -a oracle`; inspect the semantic decisions (a reference answer has no assumed model score).

```
environment/fixture/   # evidence pack: mirror tags, dsh version, compat table, sync script (crash symptom is quoted in instruction.md)
tests/                 # judge.mjs + packet.json + test.sh + Dockerfile
solution/              # reference report + solve.sh
```

Fixture provenance: trimmed from a real 2026-08-31 incident (six-plugin mirror set; same
findings as profile-dependency-management.md §8/§9, first-hand).
