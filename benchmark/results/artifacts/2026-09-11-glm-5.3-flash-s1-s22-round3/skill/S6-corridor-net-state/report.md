# S6 · Corridor Net-State Report — "ignorable-deletion" defense code vs. alpha.2

Task: read-only analysis of the plugin in the S6 fixture pack (read from E:/deepseek-harness/dsh-plugin-upgrade-skill/benchmark/tasks/S6-corridor-net-state/environment/fixture; nothing under it was modified, created, or deleted). The host target is **0.1.2-alpha.2**; the defense was written for **0.1.2-alpha.1**. Method: skill Mode A (inspect) / corridor net-state computation per plugin-upgrade Mode C step 2 — read the full corridor first, then compute the final net state.

## The defense code (fixture evidence)

'src/events.ts' (verbatim, comment translated):

    export function produceExternalEvent(session: any, payload: any): void {
      const event = { type: 'third-party/informational', payload }
      // alpha.1 removed SessionEvent.ignorable (DSH-0.1.2-A1-02). Not deleting the marker
      // would get it rejected by the reader, so the marker is deleted here before writing.
      // Keep this when migrating to alpha.2.
      delete (event as any).ignorable
      session.append(event)
    }

'package.json' identifies the pack as dsh-events-bench 0.1.0, "private": true (test material). 'README.md' states the fixture was built around the "remove-then-restore" trap (DSH-0.1.2-A1-02 → DSH-0.1.2-A2-01) and that the correct action is to delete the defense.

## 1. Fate of the defense code: DELETE it

Corridor history of the ignorable semantics:

1. **Before alpha.1 (≤ 0.1.1-rc.2)**: SessionEvent.ignorable existed. Per the harness rule ("SessionEventMap members are required-on-read by default — builds that do not know a type refuse the log unless the event carries the envelope's ignorable: true"), unknown persisted events need the marker to be safely reloadable.
2. **alpha.1 (DSH-0.1.2-A1-02, "SessionEvent.ignorable temporarily removed")**: alpha.1 could not preserve the marker on third-party informational events; first-party readers rejected reloads of unknown persisted events regardless. The card explicitly says: "If the final target is alpha.2 or later, first read DSH-0.1.2-A2-01 to compute the corridor net state; **do not delete the producer marker and then restore it**." So even at alpha.1 the sanctioned workaround was to stop writing the unknown event or use known vocabulary — never to strip the marker and keep writing.
3. **alpha.2 (DSH-0.1.2-A2-01, "Restore SessionEvent.ignorable for third-party persisted events", type: fix)**: alpha.2 restores the retention semantics across envelope/persistence/reload/transport. The card's own symptom line names this exact bug pattern: "**old adapters that keep dropping the marker will make first-party readers reject Sessions containing unknown events**."

Net state across the corridor: the field was removed in an intermediate version and restored in the target, so the correct net state is "marker present" — per skill rule C.2, "When a field is removed in an intermediate version and restored in the target, do not delete and re-add it." The comment's instruction ("keep this when migrating to alpha.2") is the opposite of the alpha.2 card, and A2-01 proves the comment's premise false: with the marker deleted, an unknown third-party/informational event stays required-on-read and **the reader rejects the session on reload** — the exact failure the defense claims to prevent. Decision by evidence, not by the comment (brief item 3).

## 2. Correct producer semantics

- Producers may set ignorable: true only for informational events whose omission by an old reader does not affect reconstruction; the marker is not a consumer-side filtering directive, and the event remains in loaded events after reload (A2-01 migration recipe). Unknown events without the marker remain required-on-read (fail closed).
- The alpha.2 retention semantics cover the envelope/persistence/reload/transport seams: JSONL, SQLite, API transports, and the generated catalog must preserve the field as-is.
- **The public live Session.append(...) has no ignorable parameter** (A2-01: "the public live Session.append(...) still has no ignorable parameter"). So an ordinary plugin going only through Session.append(...) cannot and should not set the field at all. The card prescribes the right response: **mark the producer seam as a capability gap rather than faking a public entry via cast** — no 'as any' casting to inject the field through the public API. (The fixture's own 'as any' cast is used only for the delete; the same cast would be equally illegitimate in the restore direction.)
- In practice, the ignorable marker is set at the envelope/persistence seam, not by ordinary append-callers; plugins owning a persistence seam or manual envelope/seed setup must preserve the field as-is (A2-01 verification: "a plain Session.append should not be documented as supporting the field").

## 3. What to do (concrete change plan, Mode C shape — no write performed here)

Delete the two defense lines in 'src/events.ts':

- the 'delete (event as any).ignorable' statement, and
- the alpha.1 comment block (it encodes an obsolete alpha.1 premise and a false migration instruction; keeping it would seed the next regression).

What the function should become: for a genuinely informational third-party event, write it through the public API without touching ignorable at all; if the event must survive reload on old readers, it needs the marker at an owned persistence/envelope seam (a capability the public Session.append does not currently expose — record as a capability gap / pending public seam, not something to fake with casts). Do not substitute a consumer-side whitelist of third-party event types: A1-02 explicitly forbids that because it would wrongly let required events through.

## Verification plan (A2-01 verification items)

- Unknown events with ignorable: true survive reload and remain in loaded events; unknown required events are rejected (fail closed).
- A plain Session.append path is not documented as supporting the field.
- If the deployment uses the SQLite provider: it accepts only schema 20, rejects schema 19 and other schemas — back up/export or rebuild per provider documentation before upgrading.
- No build/typecheck/runtime run was performed: this is a read-only inspection (Mode A) of a "private": true fixture pack; per the brief, no reproduction environment was built and nothing was migrated.

## Unconfirmed / caveats

- The upstream decision note and release notes are cited by the cards ([alpha.2 "retain ignorable external session events" decision](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.1.2-alpha.2/.agents/notes/implemented/architecture/2026-08-30-retain-ignorable-external-session-events.md), [alpha.2 release notes](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.1.2-alpha.2)) but were not fetched (closed-book brief, no network): their content is taken via the reviewed corridor cards DSH-0.1.2-A1-02 / DSH-0.1.2-A2-01, which cite them as primary sources. The judgment does not depend on anything outside those cards.
- Whether the fixture plugin owns any persistence/envelope seam beyond session.append cannot be verified from the pack ('src/events.ts' is the only source file, and it uses "session: any"); treated as an ordinary append-only producer.

## Sources

- Fixture: README.md, package.json, src/events.ts (quoted above; fixture untouched — no writes under it).
- Skill references: references/v0.1.2-alpha.1.md card DSH-0.1.2-A1-02; references/v0.1.2-alpha.2.md card DSH-0.1.2-A2-01; corridor net-state rule in SKILL.md Mode C step 2.
- Harness AGENTS.md session-event rule: "SessionEventMap members are required-on-read by default … unless the event carries the envelope's ignorable: true".
