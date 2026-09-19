# S5-negative-naming · Naming Four-State Judgment

The agent read-only-reviews the plugin naming manifest in `/app/fixture/` and writes a judgment report under `/app/agent-output/S5-negative-naming/`; modifying the fixture scores 0. Tests "negative capability + restrained four-state judgment": the official short name `greet` is valid (no compatibility error; prefixes are only collision recommendations), the unprefixed service `search` is a warning not an error, events are shared channels (informational), and an unqueried registry is unknown. Claiming "everything passes / can publish" is the trap.

- **Environment**: `node:24-bookworm` + git (fixture committed as a git baseline for the read-only gate); dsh is not installed (static task).
- **Verifier**: [LLM-as-judge by default](../../docs/report-judge-pilot.md), task version `4.0.0`.
  A sealed fixture hash enforces read-only work. The separate verifier reads the report,
  judges each criterion with a verdict and short reason, and deterministically aggregates the score.
  Configure `REPORT_JUDGE_BASE_URL`, `REPORT_JUDGE_MODEL` and `REPORT_JUDGE_API_KEY`
  only for the verifier. Missing reports score 0; evaluator failures leave no reward.
- **Oracle**: `harbor run -p benchmark/tasks/S5-negative-naming -a oracle`; inspect the semantic decisions (a reference answer has no assumed model score).

```
environment/fixture/   # test material only (private:true, do not publish)
tests/                 # judge.mjs + packet.json + test.sh + Dockerfile
solution/              # reference report + solve.sh
```
