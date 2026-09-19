# S3 · Snapshot Read-Surface Migration Assessment — bench-pet (dsh 0.1.1-rc.1 → 0.1.2-alpha.2)

**Status: read-only assessment. No fixture file was modified.**

## 0. Important scope and honesty note

This report was produced with **only** the fixture source, the task brief, and a
framework-agnostic migration methodology. I do **not** have access to:

- the dsh 0.1.2-alpha.2 changelog or release notes,
- the upgrade-card catalog (`DSH-0.1.2-A1-xx` series),
- the target-version type definitions of `@deepseek-ai/dsh-client-runtime/client`.

Consequences, stated up front so nothing below is mistaken for fabricated
certainty:

1. **Where every snapshot read occurs and how the plugin is coupled — fully
   answerable from the fixture alone** (§2, §3). This part is exact.
2. **The exact post-migration API shapes and the exact card numbers — cannot be
   determined from the given information.** Per the methodology ("never migrate
   blind"; "read the upstream source at the target tag; do not guess shapes from
   a one-line changelog entry"), I will not invent field names, API
   identifiers, or card IDs. Where the brief asks for them, I give (a) what is
   provable from the fixture, (b) the *category* of change each site needs, and
   (c) the exact procedure to resolve the unknowns against upstream materials
   (§5).
3. **Compatibility-projection vs. new-read-path classification** (brief item 4)
   depends on which fields the target version keeps vs. restructures. I can
   give the decision rule and a provisional classification keyed to the fields'
   shapes, but the final call per field requires the corridor notes (§4).

## 1. What was scanned

All six files of the fixture, in full:

- `package.json` — manifest / injection metadata.
- `cordis.patch.yml` — plugin registration patch.
- `README.md` — task-material notice.
- `src/client/index.ts` — plugin entry (`inject` array, `apply`, slot
  registration, dictionary registration).
- `src/client/Pet.tsx` — the component that reads the conversation snapshot
  (the core of this task).
- `src/client/locales.ts` — dictionary key types and strings.

## 2. Coupling inventory (methodology §1)

### 2.1 Manifest / metadata

- `package.json:6-9` — `client.platform: "web"`, `client.inject:
  ["dsh-client-runtime", "dsh-client-ui-conversation", "dsh-client-locale"]`.
  No declared version/compatibility range for the host exists in this file, so
  nothing here blocks loading per se; but if the 0.1.2 host renamed any of the
  injected packages, this list must be updated first (manifests before code,
  per methodology §3.1). Cannot be confirmed without target metadata.

### 2.2 Host API imports

- `src/client/index.ts:6` — `import type { ClientContext } from
  '@deepseek-ai/dsh-client-runtime/client'`.
- `src/client/index.ts:8,10` — type-only imports for Context/SlotMap merges
  from `dsh-client-locale/client` and `dsh-client-ui-conversation/client`.
- `src/client/index.ts:14-19` — module augmentation of
  `@deepseek-ai/dsh-client-ui-slots` (`LocaleNamespaceMap`).
- `src/client/Pet.tsx:7` — `PropsRuntime`, `PropsLocale` from
  `@deepseek-ai/dsh-client-ui-slots`.
- `src/client/Pet.tsx:8` — `import type { ConversationSnapshot } from
  '@deepseek-ai/dsh-client-runtime/client'`. **This type is the anchor of the
  whole migration:** every snapshot read below is typed by it.

### 2.3 Lifecycle & events

- `src/client/index.ts:35-44` — `apply(ctx)`, `ctx.effect(...)`, and a nested
  `ctx.inject(['slots','conversation'], ...)`. Standard plugin lifecycle; no
  snapshot coupling here.

### 2.4 UI contributions

- `src/client/index.ts:38-43` — registers `Pet` into slot
  `conversation.session.header.actions` (id `pet`, order 10). Depends on the
  slot still existing with the same name in 0.1.2-alpha.2 — unverifiable from
  the given materials; not part of the snapshot read surface per se.

### 2.5 Persistence / configuration / process seams / dependencies

- No persistence, no settings keys, no subprocess or output parsing, no shared
  runtime dependencies beyond the injected host packages. Scanned: all files;
  nothing found, and nothing in the fixture suggests hidden state.

## 3. The snapshot read surface — every read site (brief item 1)

All live snapshot reads are in `src/client/Pet.tsx`, via the `useSession`
selector prop supplied by the slot runtime. There are **four distinct field
reads**, plus one type dependency:

| # | Location | Code | What it reads | Change category needed |
|---|----------|------|---------------|------------------------|
| R1 | `Pet.tsx:19` | `useSession(s => s.running)` | top-level boolean `running` — session actively generating | depends on whether `running` survives 0.1.2 (rename / move / removal — see §4) |
| R2 | `Pet.tsx:13-15` | `snapshot.partial?.blocks.some(b => b.kind === 'reasoning') ?? false` | nested path `partial.blocks[].kind === 'reasoning'` — model emitting reasoning with no tool in flight | most fragile read in the file: a two-level nested path plus an enum literal; any restructuring of partial-output blocks breaks it |
| R3 | `Pet.tsx:21` | `useSession(s => s.runningCalls.length > 0)` | top-level array `runningCalls` — tool calls in flight | depends on whether in-flight tool calls stay a top-level collection (name/shape change possible) |
| R4 | `Pet.tsx:23` | `useSession(s => s.turnEnds[s.turnEnds.length - 1]?.reason)` | top-level array `turnEnds`, reading `…[last]?.reason` — settled-turn end reason | array-of-records shape; depends on whether turn-end history survives with the same `reason` field |
| T1 | `Pet.tsx:8,10,13` | `ConversationSnapshot` type import + usage | the snapshot contract itself | if the snapshot type was split/renamed in 0.1.2, the import path and type name must change even where field reads are unchanged |

Supporting context: `src/client/index.ts:35-44` wires the component in but
performs no snapshot reads; `locales.ts` is snapshot-independent.

**What would break on 0.1.2-alpha.2 (honest version):** the task brief asserts
this release restructures the snapshot read surface and ships upgrade cards for
it, but the fixture alone cannot tell me *which* of R1–R4 changed shape. The
methodology-grade statement I can make: **these four reads (plus the
`ConversationSnapshot` type) are the complete list of sites that any
snapshot-surface breaking change in 0.1.2-alpha.2 can hit in this plugin** —
the blast radius is exactly `Pet.tsx` lines 8, 13–15, 19, 21, 23, and nothing
else. A quick grep-based confirmation (`running`, `partial`, `blocks`,
`runningCalls`, `turnEnds`, `ConversationSnapshot`, `useSession`) found no
occurrences anywhere else in the fixture.

## 4. Compatibility projection vs. new read path (brief item 4)

The brief asks which fields can be served temporarily through a compatibility
projection (a shim mapping the old flat shape onto the new snapshot) and which
must switch immediately. The decision rule from the methodology (§2, §5 —
"prefer the host's documented replacement"; "deprecated-but-working is a
scheduled failure"):

**Decision rule.** A field can run first through a compatibility projection
iff (a) the target host still exposes equivalent data with the same semantics
and the host (or the plugin) provides an adapter for the old shape, and (b) no
behavioral change (ordering, timing, default) alters its meaning. A field must
switch to the new read path immediately iff the old field is removed outright,
was restructured into a different aggregation (e.g. flat flags folded into a
nested status object), or its semantics changed.

**Provisional classification by read shape** (final per-field mapping requires
the corridor notes — see §5):

- **R1 `s.running`** — a scalar flag. Scalar lifecycle flags are the most
  likely candidates to be preserved or trivially projected; *if* the target
  keeps an equivalent "turn in progress" signal, R1 can run first through a
  compatibility projection while the rest is migrated. Verify against the
  changelog whether it was renamed or folded into a status enum.
- **R2 `partial.blocks[].kind === 'reasoning'`** — the deepest, most
  structural read. If 0.1.2 restructured streaming/partial output (the most
  common reason for a snapshot-surface release), this is the read least likely
  to be projectable without re-implementing host logic — which the methodology
  forbids ("prefer the documented replacement over re-implementing"). Treat as
  **switch-to-new-read-path immediately**, pending confirmation.
- **R3 `s.runningCalls`** — a top-level collection of in-flight calls.
  Projectable only if the target still materializes the same collection
  somewhere; if tool-call state moved (e.g. into per-turn or per-block
  structures), it needs the new read path. Genuinely undecidable from the
  fixture.
- **R4 `s.turnEnds[…].reason`** — history-of-records read. If the target keeps
  turn-end history, a projection is feasible; if turn lifecycle was remodeled,
  the "last settled turn's reason" must be re-derived from the new event/state
  model. Undecidable from the fixture.

**Post-migration code forms (brief item 2):** I can spell out the *pattern*
each migrated read must take, but not the literal new field/API names — those
are exactly what the missing changelog defines:

- Each `useSession(selector)` stays as the subscription mechanism unless the
  slot runtime's prop contract changed (check `PropsRuntime` in the target
  version); only the **selector bodies** change.
- R1: `s => <target equivalent of "turn in progress">` — likely a renamed
  field or a comparison against a status enum.
- R2: a helper over the target's partial-output model, selecting "reasoning
  content present and no tool call in flight" — this logic should come from a
  host-provided selector/helper if one exists, not hand-rolled.
- R3: `s => <target in-flight tool-call collection>.length > 0` or a host
  boolean if the target exposes one.
- R4: `s => <target "last completed turn end reason">`, re-derived from
  whatever replaces the `turnEnds` history.

Any report that hands you concrete new field names for these without quoting
the upstream source at the 0.1.2-alpha.2 tag is guessing; mine declines to.

## 5. Card mapping (brief item 3) — and how to obtain it

**I cannot cite `DSH-0.1.2-A1-xx` numbers: the card catalog is not among the
materials I was given, and inventing IDs would corrupt the assessment.** The
exact procedure I would run to produce the mapping (methodology §0, §2, §5):

1. Obtain the upstream changelog/release notes for **every version in the
   corridor** 0.1.1-rc.1 → 0.1.2-alpha.2 inclusive (all rcs and alphas, not
   just the endpoints), plus the card catalog.
2. Build the net-state table for the snapshot type: for each of `running`,
   `partial.blocks`, `runningCalls`, `turnEnds`, and `ConversationSnapshot`
   itself, list every card/changelog entry that touches it across the
   corridor; collapse intermediate remove-then-restore and A→B→C renames to
   their net change.
3. Classify each net change as breaking / behavioral / additive /
   informational; record behavioral changes (defaults, ordering, timing) even
   when the field name survives — R2 and R4 in particular are sensitive to
   ordering and presence semantics.
4. Cross-check ambiguous entries against the upstream source at the
   0.1.2-alpha.2 tag (type definition of the snapshot), never from the
   changelog line alone.
5. Emit the final table: read site (file:line) → net upstream change → card
   number → post-migration selector → projection-vs-switch classification.

With those materials, this table is a mechanical fill-in of §3–§4 above;
without them, the card column and the literal API names stay blank by design.

## 6. Verification plan (for when the migration is executed)

Layered, cheapest first (methodology §4):

1. **Static**: typecheck the plugin against the target version's type
   definitions — every unresolved selector field surfaces at compile time
   because reads are typed through `ConversationSnapshot`.
2. **Install-time**: target host accepts `package.json` injection metadata and
   loads the plugin.
3. **Cold start**: boot with the plugin enabled; watch logs for slot-runtime
   deprecation/fallback warnings around `useSession` and
   `conversation.session.header.actions`.
4. **Functional probe**: drive a real conversation through the four states the
   pet distinguishes — idle; generating (R1); reasoning without tool call (R2);
   tool call in flight (R3); turn settled (R4) — and confirm the `data-frame`
   attribute transitions correctly. Probe the states you did *not* migrate
   too; silent drift hides there.
5. **Rollback rehearsal**: confirm the pre-migration plugin build still runs
   against the old host so the upgrade is reversible.

## 7. Read-only discipline statement

No file under the fixture was created, modified, or deleted. Analysis was
performed by reading the six fixture files and grepping them; the only write
performed is this report in the designated output directory.
