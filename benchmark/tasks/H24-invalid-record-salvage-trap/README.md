# H24-invalid-record-salvage-trap · Invalid-Record Salvage

The agent repairs a disposable derived-index storage domain after the
alpha.4 → alpha.5 upgrade: one current-version schema-invalid record rejects
the entire domain open, taking the healthy records down with it. Tests the
alpha.5 salvage contract (DSH-0.1.2-A5-02 `invalidRecords:
'backup-and-skip'` + `KvUnit.backupRecord`): the corrupted bytes must be
preserved on disk, only that record skipped, healthy records kept working,
and the damaged key rebuildable — with the policy scoped to this disposable
domain, never generalized to authoritative data.

- **Environment**: `node:24-bookworm` + git; `/app/fixture` ships the alpha.4
  domain declaration, a real-runtime reader app, the authoritative source
  documents, the preloaded records (healthy A/B + corrupt `broken`, all
  stamped 5), and the exact pinned alpha.5 storage closure
  (`@deepseek-ai/dsh-storage*@0.1.2-alpha.5`, `@deepseek-ai/cordis@4.0.2`,
  `zod@4.4.3`; committed lockfile, `npm ci` at build time; the agent phase
  needs no network). The fixture, data, source, and `node_modules` are
  committed as a git baseline — the judge seals everything except
  `fixture/src/**` and `fixture/package.json`, plus the runtime's own
  authorized rename of the one corrupt document (tracked deletion +
  `<key>.json.bak.<stamp>` untracked file). The trusted commit anchor is
  `/opt/h24-verifier/baseline.sha`; a missing or replaced anchor fails closed.
- **Verifier**: deterministic. 70 behavioral against the real published
  alpha.5 packages (open resolves, healthy records intact, backup moved +
  bytes equal the sealed baseline, damaged key absent, rebuild persists) +
  20 migration (scoped policy, honest schema, contract preserved) + 10
  hygiene (all required runtime dependencies retain their exact pins).
  Schema probes preserve valid records and reject missing or wrongly typed
  `id`, `sourceHash`, and `tokens`, including aliased any/unknown bypasses.
  Hard caps: spec load failure → 30; downgrade, alpha.4 pin, or missing/changed
  runtime dependencies → 20; catch-and-empty → 30; schema contract failure
  → 40 (explicit z.any) / 60; manual backup without salvage policy → 50;
  policy globalized → 70. Flat 0: fixture untouched, unavailable/changed
  trusted baseline, or sealed-file edits. Integrity is checked before and
  after candidate execution, schema probes, runtime opens, and rebuilds;
  index flags cannot hide changes to actual file bytes. A byte-identical
  backup from running the prescribed reader is accepted. Other record edits,
  backup deletion/corruption, and runtime or manifest mutation are rejected.
- **Oracle**: `harbor run -p benchmark/tasks/H24-invalid-record-salvage-trap -a oracle`, expected reward 1.0.

```
environment/fixture/   # alpha.4 domain spec + reader app + source docs + preloaded records + pinned closure
tests/                 # judge + integrity helper + unit/real-runtime regressions + test.sh
solution/              # alpha.5 salvage + solve.sh
```

Distinct from H23 (valid payload, stale version stamp, silent absence →
`compatibleVersions`): this task is current-stamp + schema-invalid payload +
loud open rejection → `backup-and-skip`. A cross-axis negative control
verifies that H23's `compatibleVersions` cannot fix this failure.

Run `npm run test:h24-judge` for the unit tests and real-runtime adversarial
regressions. This command installs the committed fixture lockfile first and
is included in `npm test`.
