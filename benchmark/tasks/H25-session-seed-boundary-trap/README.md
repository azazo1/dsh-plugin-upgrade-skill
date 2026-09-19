# H25-session-seed-boundary-trap · Session Seed Boundary

The agent migrates a fork-aware session state helper from alpha.3 to
alpha.4: the durable fork boundary (`header.seedLength`) becomes
`isSeeded` + top-level `inheritedEventCount`, positions and offsets become
branded `SessionSeq` / `SessionLogOffset`, and the projection `init`
receives the inherited boundary. The core trap: a FRESH fork looks correct
with the current log length as the cut, but a RESUMED fork (stored log
grown past the original prefix) exposes the difference — the ORIGINAL cut
must survive, or own events silently reclassify as inherited.

- **Environment**: `node:24-bookworm` + git; `/app/fixture` ships the
  alpha.3 helper module, a local verification app, and the exact pinned
  first-party closure `@deepseek-ai/dsh-session@0.1.2-alpha.4` (committed
  lockfile, `npm ci` at build time; the agent phase needs no network). The
  fixture and `node_modules` are committed as a git baseline — the judge
  seals everything except `fixture/src/**` and `fixture/package.json`
  (all required runtime dependency pins are checked). The trusted commit
  anchor is `/opt/h25-verifier/baseline.sha`; missing or replaced anchors
  fail closed. Integrity checks compare actual file bytes with the trusted
  commit before and after candidate execution, independent of index flags.
- **Verifier**: deterministic. 65 behavioral against the real published
  alpha.4 package (fresh fork cut, resumed fork original cut, unforked
  session, projection init+apply, valid + invalid brand construction) + 25
  migration (no stale `seedLength`, `isSeeded` correct, `inheritedEventCount`
  declared, `SessionSeq` for positions, `SessionLogOffset` for offsets) +
  10 hygiene. Hard caps: module load failure → 30; as-cast bypass → 30;
  constructors no longer throw → 40; swapped brand usage → 60; resumed
  boundary fails real-session probes → 65; `isSeeded` without count /
  count without `isSeeded` → 40; stale `seedLength` kept → 70; alpha.3 pin
  or missing/changed required runtime dependencies → 20. Flat 0: fixture
  untouched, sealed-file edits, runtime prototype mutation, candidate source
  or manifest mutation during verification, or an unavailable/changed baseline.
  Resume checks use grown logs with original cuts 3/1/5; a legitimate length
  validation or other incidental `.length` read does not trigger a cap.
- **Oracle**: `harbor run -p benchmark/tasks/H25-session-seed-boundary-trap -a oracle`, expected reward 1.0.

```
environment/fixture/   # alpha.3 fork-state helpers + verification app + pinned closure
tests/                 # judge + integrity helper + unit/real-runtime regressions + test.sh
solution/              # alpha.4 migration + solve.sh
```

Distinct from H20 (`Session.events` removal — how to READ the log): this
task is about what session numbers MEAN and how the fork cut is stored —
the sequence/offset distinction plus the seed/fork metadata migration.

Run `npm run test:h25-judge` for the unit tests and real-runtime adversarial
regressions. This command installs the committed fixture lockfile first and
is included in `npm test`.
