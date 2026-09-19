# S6 · Corridor Net-State Judgment — Migration Report (read-only)

**Task:** judge the fate of the alpha.1-era "defense code" in `fixture/src/events.ts` when migrating to host **alpha.2**.
**Mode:** read-only analysis; fixture untouched. Target host: alpha.2.

## 0. What the code under judgment does

```ts
export function produceExternalEvent(session: any, payload: any): void {
  const event = { type: 'third-party/informational', payload }
  // alpha.1 removed SessionEvent.ignorable (DSH-0.1.2-A1-02). Without deleting the
  // marker, readers reject it, so delete it first. Keep this when migrating to alpha.2.
  delete (event as any).ignorable
  session.append(event)
}
```

The claimed invariant: "readers will reject the event unless the `ignorable` marker is deleted, and this defense must survive the alpha.2 migration."

## 1. Verdict: **delete the defense code** (both the `delete` line and the comment)

Reasoning across the full version corridor:

1. **Original semantics (pre-alpha.1).** `SessionEvent` carries an `ignorable` marker on the event envelope. `SessionEventMap` members are required-on-read by default: a reader build that does not know an event type refuses the log entry **unless the envelope carries `ignorable: true`**. The marker is therefore a *reader-directed tolerance/retention* flag — it tells unknown readers they may accept (and retain) an event type they don't statically know.

2. **alpha.1 (DSH-0.1.2-A1-02).** `SessionEvent.ignorable` was temporarily **removed**. In that window, a producer stuffing `ignorable` into a third-party event could produce a field the alpha.1 schema no longer defined, and readers built against alpha.1 might reject such an event. The `delete` line is an alpha.1-scoped workaround for exactly this window.

3. **alpha.2 (DSH-0.1.2-A2-01, the migration target).** The remove-then-restore corridor **restores the retention semantics**: `ignorable` exists again on the event envelope, and unknown-type events are again tolerated precisely when the envelope carries `ignorable: true`. Under alpha.2, deleting the marker is not merely unnecessary — it is **harmful**: a third-party event type stripped of `ignorable` reverts to required-on-read, so reader builds that don't know `third-party/informational` will refuse it. The defense inverts into an anti-defense.

4. **The comment is not evidence.** It asserts the defense "must be kept when migrating to alpha.2", but the only support is the comment itself. The fixture's own README states the opposite and explicitly labels the comment a trap: alpha.2 restored the retention semantics (DSH-0.1.2-A1-02 → DSH-0.1.2-A2-01 remove-then-restore) and "the correct action is to delete this defense." Comments narrate intent; they cannot override the host's actual schema.

5. **The defense is dead code anyway.** The event literal is `{ type, payload }`; it never defines an `ignorable` property, so `delete (event as any).ignorable` is a no-op on this object in every version. Even inside the alpha.1 window the line defended against nothing for a producer that never sets the marker. Combined with point 3, there is no corridor state in which this specific line does useful work for this specific literal — and in alpha.2 its presence (and the comment urging its retention) actively misleads future maintainers.

**Net-state judgment:** across the corridor the semantics form a remove-then-restore arc; the migration lands on the *restore* side, so the alpha.1 compensation must be dropped, not carried forward. Compensations for a temporary regression are themselves temporary; migrating them across the corridor's far side re-imports the bug the restore fixed.

## 2. Correct producer semantics on alpha.2

- `ignorable` is **envelope-level and reader-directed**, not a payload field a producer mutates. It declares "reader builds that don't statically know this event type may accept and retain this entry" (the retention semantics restored in alpha.2).
- Default `SessionEventMap` members are **required-on-read**: unknown types are refused unless the envelope says `ignorable: true`. A third-party informational event that arbitrary reader builds should tolerate is exactly the case where the marker should be **present with value `true`**, never deleted.
- The proper mechanism for a plugin is **declaration merging** into the host's extensible `SessionEventMap`: declare `third-party/informational` as a proper event type with its envelope marked `ignorable: true` (plus the documented `@mode`/payload JSDoc the event system requires). The marker then belongs to the *type declaration*, applied by the host when writing the envelope.
- **What an ordinary plugin calling `session.append(...)` should do: nothing marker-related.** The public `Session.append(...)` surface takes the typed event; the `ignorable` flag is not an `append` parameter a caller toggles (per the task hint, the public API may not expose such a parameter at all — **unconfirmed** against real alpha.2 typings, see §3). The plugin's only obligations are: emit a well-formed typed event, declare the type via declaration merging if it is plugin-defined, and mark that declaration `ignorable: true` if reader builds may not know it. Hand-deleting envelope fields through `any` casts is outside the contract in every version.

Concretely, the corrected migration of `produceExternalEvent` is:

```ts
export function produceExternalEvent(session: any, payload: any): void {
  session.append({ type: 'third-party/informational', payload })
}
```

— with `third-party/informational` declared (merged) as an `ignorable: true` event type in the plugin's type declarations, and the alpha.1 comment removed.

## 3. Evidence inventory & confidence

| Claim | Evidence | Status |
|---|---|---|
| alpha.1 removed `SessionEvent.ignorable` (DSH-0.1.2-A1-02) | fixture README + code comment | confirmed within fixture (closed book) |
| alpha.2 restored the retention semantics (DSH-0.1.2-A2-01 remove-then-restore) | fixture README ("the correct action is to delete this defense") | confirmed within fixture |
| Required-on-read default; `ignorable: true` on the envelope lets unknown-reader builds accept the entry | harness architecture documentation quoted in this workspace's AGENTS.md ("SessionEventMap members are required-on-read by default — builds that do not know a type refuse the log unless the event carries the envelope's `ignorable: true`") | verified against workspace docs |
| The comment's "must keep in alpha.2" claim | the comment itself only | **rejected** — contradicted by fixture README and by the restored semantics |
| Exact alpha.2 `Session.append(...)` parameter list (that no `ignorable` parameter exists) | task hint only; alpha.2 host source not inspectable in-container | **unconfirmed** (closed book) |
| Full text of DSH-0.1.2-A1-02 / A2-01 records | not present in fixture | **unconfirmed** — relied on fixture README's citation |

## 4. Conclusion

- **Fate of the defense code: delete** — remove the `delete (event as any).ignorable` line and its comment. It was a compensation for alpha.1's temporary removal of `ignorable`; alpha.2 restores the marker, so keeping the deletion would strip a third-party event of the very flag unknown readers need, and the line is a no-op on this literal regardless.
- **Producer semantics on alpha.2:** `ignorable` is an envelope-level, reader-directed retention marker expressed through the event's type declaration (declaration merging, `ignorable: true`), not a field producers add/remove by hand. An ordinary plugin using `session.append(...)` does nothing marker-related at the call site.
- Decisions above rest on fixture evidence and workspace architecture docs, not on the code comment; residual uncertainties are marked **unconfirmed** in §3.
