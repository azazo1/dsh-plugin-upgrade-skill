# S7-unpublished-cohort · Unpublished Cohort Install Plan

The agent read-only-analyzes a plugin pinning `@deepseek-ai/dsh-llm ^0.1.2-alpha.1` (never published) and writes an install/type-baseline plan under `/app/agent-output/S7-unpublished-cohort/`; modifying the fixture scores 0. Tests "registry check first + one or more complete legitimate paths (verified source-build tarballs / exact pin to the published 0.1.2-alpha.2 + lockfile) + discipline (no package-manager switching)". The closed-book bonus point is recognizing that `^0.1.2-alpha.1` silently resolves to `0.1.2-alpha.2` (declaration/result divergence); prescribing a direct install of alpha.1 caps the score at 10.

- **Environment**: `node:24-bookworm` + git (fixture committed as a git baseline for the read-only gate); dsh is not installed (static task).
- **Verifier**: [LLM-as-judge by default](../../docs/report-judge-pilot.md), task version `4.0.0`.
  A sealed fixture hash enforces read-only work. The separate verifier reads the report,
  judges each criterion with a verdict and short reason, and deterministically aggregates the score.
  Configure `REPORT_JUDGE_BASE_URL`, `REPORT_JUDGE_MODEL` and `REPORT_JUDGE_API_KEY`
  only for the verifier. Missing reports score 0; evaluator failures leave no reward.
- **Oracle**: `harbor run -p benchmark/tasks/S7-unpublished-cohort -a oracle`; inspect the semantic decisions (a reference answer has no assumed model score).

```
environment/fixture/   # test material only (private:true, do not publish)
tests/                 # judge.mjs + packet.json + test.sh + Dockerfile
solution/              # reference report + solve.sh
```
