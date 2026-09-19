# S9-composer-coordinate-trap · Composer coordinate trap (read-only)

A community attachment plugin pastes files into the DSH composer: the first paste succeeds
and every later one errors with `The DSH composer changed before the attachment could be
inserted`, while the dock chip's × leaves the chip behind showing `unavailable`. The agent
must tie both symptoms to ONE underlying contract misread — the plugin feeds
clipboard-projection offsets into host verbs whose span guards compare against the
detect projection (a chip is one U+FFFC there, its full clipboard text in the published
draft) — derive the conversion rule from the host source excerpts, and design the
repeat-interaction + removal regression plan. 题面见 [instruction.md](instruction.md)，
判分逻辑见 [tests/judge.mjs](tests/judge.mjs)。

- **Environment**: `node:24-bookworm` + git (fixture baseline-committed for the read-only gate); no dsh (static task).
- **Verifier**: [LLM-as-judge by default](../../docs/report-judge-pilot.md), task version `4.0.0`.
  A sealed fixture hash enforces read-only work. The separate verifier reads the report,
  judges each criterion with a verdict and short reason, and deterministically aggregates the score.
  Configure `REPORT_JUDGE_BASE_URL`, `REPORT_JUDGE_MODEL` and `REPORT_JUDGE_API_KEY`
  only for the verifier. Missing reports score 0; evaluator failures leave no reward.
- **Oracle**: `harbor run -p benchmark/tasks/S9-composer-coordinate-trap -a oracle`; inspect the semantic decisions (a reference answer has no assumed model score).

```
environment/fixture/   # evidence pack: plugin client excerpt, session log, host facade + contract excerpts
tests/                 # judge.mjs + packet.json + test.sh + Dockerfile
solution/              # reference report + solve.sh
```

Fixture provenance: trimmed from a real 2026-09-01 debugging session on the
dsh-paste-input plugin (fixed in its v0.1.10); host excerpts quoted from the DSH
ui-conversation input facade/contract sources.
