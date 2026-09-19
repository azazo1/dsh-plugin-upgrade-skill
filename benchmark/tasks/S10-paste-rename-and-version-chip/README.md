# S10-paste-rename-and-version-chip · Paste renaming & version chip (read-only)

Two post-release follow-ups on a community attachment plugin: (A) pasted files need unified
renaming — images `paste_image.<ext>`, other files `paste_file.<ext>`, sequence numbering
`(2)`, `(3)`… derived from the authoritative live-chip set, while drops and the picker keep
real names; (B) the self-update version chip displayed a CDN-stale fetched tag as "latest"
minutes after a push. The agent must design the rename (scheme, scope, conflict source,
extension fallback), name the chip's display rule (compare fetched tag vs running version,
show the newer), and give the regression + lib-only release hygiene. 题面见
[instruction.md](instruction.md)，判分逻辑见 [tests/judge.mjs](tests/judge.mjs)。

- **Environment**: `node:24-bookworm` + git (fixture baseline retained; read-only verification uses sealed hashes); no dsh (static task).
- **Verifier**: LLM: paste naming/scope, live conflict state, stale-tag display, regressions and release hygiene: 20 each. Prompt item 2 (extension/MIME/display detail) remains unscored. Full/partial/fail/missing earn 100%/50%/0%/0% of each weight. The verifier runs separately, validates frozen fixture hashes and structured decisions and reasons, and writes scalar `reward.txt` plus `details.json`. Judge service failures exit nonzero without a reward.
- **Oracle**: run `harbor run -p benchmark/tasks/S10-paste-rename-and-version-chip -a oracle` with judge configuration. This grades the reference report through the same LLM; a perfect score is not hardcoded.

```
environment/fixture/   # evidence pack: attachment-flow excerpt, chip code, user threads, captured HTTP response
tests/                 # judge.mjs + packet.json + test.sh + Dockerfile
solution/              # reference report + solve.sh
```

Fixture provenance: trimmed from the same real 2026-09-01 dsh-paste-input session as S9
(the v0.1.10 unified-renaming feature and the v0.1.11 chip fix).

Default task version: **4.0.0**, protocol `report-judge-v2`. Set
`REPORT_JUDGE_BASE_URL`, `REPORT_JUDGE_MODEL` and `REPORT_JUDGE_API_KEY` for the
verifier. See [semantic-judge setup](../../docs/report-judge-pilot.md).
The agent receives neither judge credentials nor sealed reference excerpts.
Edit the shared rubric/implementation in `benchmark/report-judge/`, run
`npm run sync:report-judge`, then `npm run test:report-judge`; CI rejects stale
standalone copies or packets. Historical keyword scores remain historical.
