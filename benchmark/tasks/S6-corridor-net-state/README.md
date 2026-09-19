# S6-corridor-net-state · Corridor Net-State Folding

The agent read-only-analyzes the alpha.1-era defense code that deletes `SessionEvent.ignorable` and writes a migration report under `/app/agent-output/S6-corridor-net-state/`; modifying the fixture scores 0. Tests "the DSH-0.1.2-A1-02 ↔ DSH-0.1.2-A2-01 remove-then-restore net-state judgment: delete the defense code + correct producer semantics (only informational events carry `ignorable: true`) + the public `Session.append` capability gap (no cast)". The trap comment "keep the defense" caps the score at 10 when followed.

- **Environment**: `node:24-bookworm` + git (fixture committed as a git baseline for the read-only gate); dsh is not installed (static task).
- **Verifier**: [LLM-as-judge by default](../../docs/report-judge-pilot.md), task version `4.0.0`.
  A sealed fixture hash enforces read-only work. The separate verifier reads the report,
  judges each criterion with a verdict and short reason, and deterministically aggregates the score.
  Configure `REPORT_JUDGE_BASE_URL`, `REPORT_JUDGE_MODEL` and `REPORT_JUDGE_API_KEY`
  only for the verifier. Missing reports score 0; evaluator failures leave no reward.
- **Oracle**: `harbor run -p benchmark/tasks/S6-corridor-net-state -a oracle`; inspect the semantic decisions (a reference answer has no assumed model score).

```
environment/fixture/   # test material only (private:true, do not publish)
tests/                 # judge.mjs + packet.json + test.sh + Dockerfile
solution/              # reference report + solve.sh
```
