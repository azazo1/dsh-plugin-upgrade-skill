# S12-global-upgrade-ebusy-trap · Global upgrade EBUSY + downgrade trap (read-only)

A user tries to upgrade dsh from alpha.4 to alpha.5 and fails twice: first EBUSY on
koffi.node (the running dsh host process holds an OS file lock on the native addon that a
page refresh cannot release), then after stopping dsh, a combined install command from a
plugin README silently downgrades dsh to rc.2 (unpinned npm install -g resolves to the
`latest` dist-tag, not the current or newest version). 题面见 [instruction.md](instruction.md)，
判分逻辑见 [tests/judge.mjs](tests/judge.mjs)。

- **Environment**: `node:24-bookworm` + git (fixture baseline retained; read-only verification uses sealed hashes).
- **Verifier**: LLM: native-module owner, browser/host stop-install-restart sequence, unpinned dist-tag resolution, exact alpha.5/TUI commands and README prevention: 20 each. Full/partial/fail/missing earn 100%/50%/0%/0% of each weight. The verifier runs separately, validates frozen fixture hashes and structured decisions and reasons, and writes scalar `reward.txt` plus `details.json`. Judge service failures exit nonzero without a reward.
- **Oracle**: run `harbor run -p benchmark/tasks/S12-global-upgrade-ebusy-trap -a oracle` with judge configuration. This grades the reference report through the same LLM; a perfect score is not hardcoded.

Fixture provenance: trimmed from a real 2026-09-02 upgrade incident (dsh alpha.4→alpha.5,
author's own session).

Default task version: **4.0.0**, protocol `report-judge-v2`. Set
`REPORT_JUDGE_BASE_URL`, `REPORT_JUDGE_MODEL` and `REPORT_JUDGE_API_KEY` for the
verifier. See [semantic-judge setup](../../docs/report-judge-pilot.md).
The agent receives neither judge credentials nor sealed reference excerpts.
Edit the shared rubric/implementation in `benchmark/report-judge/`, run
`npm run sync:report-judge`, then `npm run test:report-judge`; CI rejects stale
standalone copies or packets. Historical keyword scores remain historical.
