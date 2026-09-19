# Migration Report — S6: Corridor Net-State Judgment

**Scope:** Read-only analysis of the plugin fixture (`/app/fixture/`). Target host: **alpha.2**.
**Constraint:** Closed book. No upstream changelog, release notes, or framework-specific
references were available. Everything below is derived from the fixture itself plus a
generic migration methodology; anything that could not be verified from the given
material is explicitly marked **unconfirmed**.

---

## 1. Verdict

**Delete the defense code** — the `delete (event as any).ignorable` line and its
comment in `src/events.ts:6` (and rewrite the comment at lines 3–5, which currently
instructs future maintainers to keep it).

The defense was written for alpha.1 semantics. Across the full corridor, the
`SessionEvent.ignorable` retention semantics were **removed in alpha.1 and restored in
alpha.2** (per the fixture's own README, citing change cards `DSH-0.1.2-A1-02` →
`DSH-0.1.2-A2-01`). A remove-then-restore is a **net-zero change**: code at alpha.2
behaves, for this concern, like the pre-alpha.1 baseline, so a workaround that only
exists because of the intermediate alpha.1 regression is obsolete at the target.

---

## 2. Evidence

### 2.1 What the fixture actually contains

- `src/events.ts:1–8` — the only source file. A single function
  `produceExternalEvent(session, payload)` builds an object literal
  `{ type: 'third-party/informational', payload }`, runs
  `delete (event as any).ignorable`, and calls `session.append(event)`.
- `src/events.ts:3–5` — a comment (in Chinese) stating: alpha.1 removed
  `SessionEvent.ignorable` (card `DSH-0.1.2-A1-02`); "without deleting the marker
  readers will reject it"; "this must be kept when migrating to alpha.2". The comment
  is attributed to a community note, and the fixture README characterizes it as a
  trap.
- `README.md` (fixture) — states the corridor history explicitly: alpha.1 temporarily
  removed `ignorable`; **alpha.2 restored the retention semantics**
  (`DSH-0.1.2-A1-02` → `DSH-0.1.2-A2-01`, a remove-then-restore); the correct action
  is to delete the defense.
- `package.json` — `private: true`, no dependencies, no host-SDK import surface to
  inspect. There is nothing else to couple-analyze.

### 2.2 Net-state reasoning (methodology)

Per the generic methodology ("read the corridor, not just the endpoints"), the
correct unit of analysis is the **net change from start to target**, not any single
intermediate release:

| Corridor step | Change to `ignorable` semantics | Classification |
|---|---|---|
| pre-alpha.1 → alpha.1 | field/semantics removed (`DSH-0.1.2-A1-02`) | breaking (for alpha.1 targets) |
| alpha.1 → alpha.2 | semantics restored (`DSH-0.1.2-A2-01`) | breaking reversal / net-zero |
| **pre-alpha.1 → alpha.2 (net)** | **none** | informational |

Because the endpoint semantics match the pre-corridor semantics, any compensation
written for the intermediate state is dead weight at the target — and, worse, its
comment actively instructs maintainers to preserve the wrong behavior.

### 2.3 Mechanical observation (independent of corridor history)

Even setting history aside, the defense is a **no-op as written**: the object literal
at `src/events.ts:2` never assigns an `ignorable` property, so `delete` on it removes
nothing. This does not by itself prove the defense is wrong (a reader-side rejection
rule could conceivably concern events that *lack* a marker — unconfirmed), but it
means the line cannot be "protecting" the event by removing anything that exists. It
is dead code whose only real effect is the misleading comment around it.

### 2.4 Evidence hierarchy

The instruction says to decide by evidence, not by the comment. The ranking here:

1. The **corridor claim in the fixture README** (remove-then-restore, with card IDs)
   is the strongest available evidence and directly contradicts the code comment's
   "keep it for alpha.2" instruction.
2. The **code comment** is a self-described community note written against alpha.1;
   its "must be kept" clause is a prediction about alpha.2 made before alpha.2's
   restore, and the fixture flags it as a trap. Comments are not semantics.
3. The **mechanical no-op** (§2.3) corroborates that deleting the line changes no
   runtime behavior in this file.

All three point the same way: **delete**.

---

## 3. Correct producer semantics at alpha.2

- A producer going through `Session.append(...)` should construct the event with its
  documented shape and **not touch `ignorable` at all** — neither set it nor delete
  it. Marker retention/interpretation is the host's (reader's) business under the
  restored alpha.2 semantics.
- Concretely, the migrated body is:

  ```ts
  export function produceExternalEvent(session: any, payload: any): void {
    const event = { type: 'third-party/informational', payload }
    session.append(event)
  }
  ```

- **Unconfirmed:** whether the public API surface of `Session.append` (or the event
  type it accepts) even exposes an `ignorable` parameter/field at alpha.2. The
  fixture uses `session: any` and `delete (event as any).ignorable`, and the `any`
  casts suggest the property may not be part of the typed public surface at all — if
  so, the defense was reaching into non-public shape from the start. This cannot be
  verified without the host's SDK types or changelog, which are not in the fixture.
- **Unconfirmed:** the precise alpha.2 reader-side retention rule (what "restored
  retention semantics" means field-by-field). The fixture README asserts the restore;
  an exact mapping to change cards `DSH-0.1.2-A1-02` / `DSH-0.1.2-A2-01` requires the
  upstream changelog/migration cards, which I do not have. The correct procedure is:
  pull the upstream release notes for every version in the corridor
  (pre-alpha.1 → alpha.1 → alpha.2), locate those two cards, confirm the alpha.2
  entry explicitly reverses the alpha.1 removal, and only then finalize the edit.

---

## 4. How this would be verified (had edits been in scope)

Layered verification, cheap first (per methodology §4):

1. **Static:** typecheck the plugin against the alpha.2 SDK — if `ignorable` is not
   on the public event type, the `as any` cast disappears with the delete.
2. **Install/cold start:** load the plugin under a real alpha.2 host; watch logs for
   deprecation or reader-rejection warnings, not just crashes.
3. **Functional probe:** write one real third-party persistent event through
   `Session.append` *without* any marker manipulation and confirm the alpha.2 reader
   accepts and retains it as the restored semantics promise. Also probe an event
   that legitimately carries the marker, to confirm retention behavior both ways.
4. **Regression check on the un-migrated path:** confirm no other code in the plugin
   reads or depends on `ignorable` (in this fixture: none — single 8-line file).
5. **Rollback rehearsal:** keep the alpha.1-targeted install side-by-side until the
   alpha.2 probe passes.

---

## 5. Unconfirmed items (explicit)

- The exact text/scope of change cards `DSH-0.1.2-A1-02` and `DSH-0.1.2-A2-01` — the
  fixture README references them but the cards themselves are not in the given
  materials. The corridor history is taken from the README's assertion.
- Whether `ignorable` exists on the public API surface at alpha.2 (or ever did).
- Whether any reader at alpha.2 has edge-case behavior around events that *lack* the
  marker (the scenario the original comment feared); assumed settled by the restore,
  but not independently verifiable here.
- Whether the plugin has any other coupling to this semantics outside
  `src/events.ts` — ruled out by inspection: the fixture contains exactly three
  files, and `events.ts` is the only source file.

## 6. Migration log entry (recommended)

> Removed alpha.1-era defense (`delete event.ignorable`) and its comment from
> `produceExternalEvent`. Rationale: `ignorable` semantics removed in alpha.1,
> restored in alpha.2 — net-zero corridor change, workaround obsolete. The delete was
> additionally a runtime no-op (property never assigned). Producers should pass the
> documented event shape to `Session.append` and leave marker handling to the host.
> Card-level confirmation against the upstream changelog is pending (cards not in
> fixture).
