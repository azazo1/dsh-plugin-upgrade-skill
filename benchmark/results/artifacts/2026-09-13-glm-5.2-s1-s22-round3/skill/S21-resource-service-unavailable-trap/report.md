# S21 · The Resource Service That "Unavailable" — Analysis Report

Task: S21-resource-service-unavailable-trap (read-only diagnosis)
Evidence: fixture pack from a real 2026-09-09 dsh 0.1.5-alpha.1 → 0.1.5-alpha.2 npm-global in-place upgrade on Windows (profile created under 0.1.2/0.1.3, six external client plugins junction-linked).
Skill mode: A · inspect (read-only; no migration, installation, or fixture modification performed).

## 1. Attribution — which layer actually fails

Two distinct symptoms appear, and they fail at different layers:

**(a) Outside-workspace link → "no registered tab type claims dsh-resource://file/absolute/…"**
This is a client-side tab-registry claim miss, not a read failure. The evidence is in `boot-manifest-excerpt.txt`: in 0.1.5-alpha.2, `ui-sidebar-textpreview` (which registered the "text" tab claiming `dsh-resource://file/**`) was **replaced** by `ui-sidebar-documentpreview`, whose document tab `canOpen` accepts only `parseFileAddress(address)?.scope === 'session'`. An `…/file/absolute/…` address therefore has no claimant by design in alpha.2. The roster census confirms `ui-sidebar-textpreview` is ABSENT (0 mentions) while `ui-sidebar-documentpreview`'s row is in the bundle patch. This is expected behavior of the new package, not a broken artifact.

**(b) In-workspace link → tab opens, title correct, content shows 「文件资源服务不可用。」 with `meta.status` stuck at `'none'`**
This is the real failure, and it is **not** in static serving, not in tab registration, and not in the document renderer. The contrast probe isolates it:

| Reader | Transport | Result |
|---|---|---|
| file-trace plugin | its own host RPC (`/dsh-file-trace/*` HTTP face) | reads fine (原文 and 阅读 both render) |
| documentpreview tab | `@deepseek-ai/dsh-api-workspace-files` Remote | fails — `meta.status` never leaves `'none'` |

What the two readers of the same file rule in / rule out:

- file-trace working **rules out**: file permissions, the file's existence, session workspace-root resolution basics, the browser page, and general host-side FS access. The host can read the file over HTTP RPC.
- documentpreview failing while file-trace succeeds **rules in**: the failure is specific to the **api-workspace-files Remote/service chain** — the client-side Remote call to the workspace-files service never produces a result.

The metadata status is decisive about *where* it stalls: `meta.status === 'none'` (the initial/pending state), **not** an error state. A rejected read (permission denied, outside-root, decode failure) would produce an error status. `'none'` means the **RPC never resolves at all** — the request is sent and no provider answers. That matches the tab's message 文件资源服务不可用 ("file resource service unavailable"): the client detected the Remote as unavailable/pending, i.e. the host-side workspace-files service (or its wiring into the Remote gateway) did not take over after the in-place upgrade, even though its module serves fine and its row exists in the web-app `cordis.patch.yml`. This is the same family as discussion #5999 round 1, where "the resource-provider chain did not take over" after a restart — round 2 is narrower: roster/combo are now consistent, but the service still never answers.

Also note the host-side hint in `contrast-probe.txt`: the service resolves each session's workspace root via a typert `lookups.register` entry (`sessions.get(sessionId)?.header.cwd` falling back to `sandboxPolicy.workspaceRoot`). On this old profile, a lookup that never resolves would also leave the read pending rather than erroring — a plausible mechanism for the stall, to be confirmed upstream, but the layer is the same: host service/Remote resolution, not the client tab.

## 2. Probe discipline — which combo probe is valid

- **Valid: the per-module sweep (Probe 3, 62/62 HTTP 200, zero 404s)** — and equivalently Probe 1 on the single-module combo URL. Each manifest entry is fetched individually at its own advertised URL and `rev` suffix. This is a faithful measurement of static artifact serving: every module the boot manifest advertises is actually served by the combo route at its own rev.
- **Invalid: Probe 2, all 62 entries comma-joined into one ~4–5 KB URL → 404.** This is a hand-fabricated URL, not one the loader would ever issue:
  - the joined URL pins a **single `rev=…-0`** for all 62 modules, while the manifest gives each entry its own per-slot suffix (`rev=…-3`, `…-N`);
  - the loader does not concatenate the entire roster into one request — multi-module combos are built per-plugin `inject` groupings, not "everything at once";
  - a 404 on a URL the platform would never generate says nothing about artifact availability.

Therefore the failing probe must **never** be cited as "modules missing": its 404 reflects malformed request syntax, not absence of modules — directly contradicted by the 62/62 sweep on the same host. In round 1 (#5999) modules really were missing (combo 404 **at the module's own rev**); in round 2 they are not, and citing Probe 2 would misdiagnose the regression as a repeat of round 1.

**How the real loader fetches the roster:** the browser reads the boot manifest injected as `window.__DSH_BOOT__` (same-origin), then requests each listed entry's own `url` (`/plugins/??<id>/client.js&rev=<rev>-<slot>`) — or a combo of a plugin with its declared `inject` dependencies — exactly what Probe 3 replayed. There is no all-entries-joined fetch.

## 3. Distractor separation

- **`dsh-paste-input: fold skipped (parse failed)` warnings: unrelated.** They fire while re-rendering *historical paste-attachment message bubbles* (the ```==== DSH_PASTE_INPUT_V1 ====``` marker protocol) and repeat once per old attachment message. They concern message-bubble collapsing in the chat timeline, share no transport, service, or code path with the workspace-files Remote read, and produce no errors in the sidebar/resource system. Simultaneous unrelated bug — do not bundle them into the upstream report's cause.
- **What actually changed in the roster between the two versions:** `ui-sidebar-textpreview` → `ui-sidebar-documentpreview` (package replaced; old row removed from `packages/bundle/web-app/cordis.patch.yml`, new row added).
- **Does that change explain the symptom?** It explains **symptom (a)** completely: the removed "text" tab was the only claimant of `file/**` including `absolute` scope; the new document tab claims `scope === 'session'` only, so outside-workspace links now correctly report "no registered tab type claims". It does **not** explain **symptom (b)**: the in-workspace (session-scoped) address *is* claimed, the tab *does* open and render its title — the failure is downstream in the resource service read. Treating the rename as the cause of the content failure would be the trap this task tests.

## 4. Mitigation decision — should the plugin work around it?

**No.** The plugin (documentpreview) should not rewrite, retry, or add a fallback read path:

- the failing dependency is a **host-provided Remote**; the client cannot repair an unanswered host service, only mask it;
- a fallback (e.g. reading via some other route like file-trace's face) would produce divergent behavior across deployments and hide the host regression from upstream;
- retries are pointless for a stalled/pending Remote (`status: 'none'` is not a retryable transport error);
- the correct client behavior already exists: surface "service unavailable" distinctly. The improvement worth making client-side (upstream, not as a local hack) is turning the dead-end 「文件资源服务不可用。」 into an actionable error state with a retry affordance — matching how symptom (a)'s dialog already offers 重试.

**Order of action for the maintainer:**

1. **First cheap step — full clean host restart.** Completely stop every dsh process (a browser refresh is not a host stop), then start `dsh web` again. #5999 round 1 shows a host restart self-heals roster/combo inconsistencies after an in-place npm upgrade; re-check whether the workspace-files Remote also comes up on a clean boot (in round 1 it did not — but this is the zero-cost first probe and the standard post-in-place-upgrade step).
2. **If still failing — use the escape hatch: rollback** to the previous published version with a pinned install (`npm install -g @deepseek-ai/dsh@0.1.3-alpha.2`, verified working in #5999; or the last-known-good 0.1.5-alpha.1 for this profile if it read files correctly — it did not in #5999 round 1, so 0.1.3-alpha.2 is the verified choice). Run it from an external terminal with all dsh processes stopped, then hard-refresh the browser.
3. **Then go upstream:** append forensics to discussion #5999 (round 2, as the fixture notes comment 18371079 already did) or open a dedicated issue, so the host fixes the workspace-files service resolution on upgraded old profiles. Do not maintain a local fork/patch of the host.

## 5. Prevention / upstream — forensics and boot-time checks

**A complete upstream report needs:**

- exact versions: from (`0.1.5-alpha.1`) / to (`0.1.5-alpha.2`), install channel (npm global, in-place), Node/Windows versions, profile provenance (created under 0.1.2/0.1.3) and the six junction-linked external client plugins;
- the full `__DSH_BOOT__` manifest capture (not an excerpt), including the workspace-files row with its `inject` list and rev;
- probe results: per-module sweep (62/62 200) — explicitly labeled as the valid measurement — plus the contrast probe table (file-trace RPC works vs workspace-files Remote stalls at `meta.status: 'none'`);
- the session-scoped and absolute resource addresses involved, the session's workspace root, and how the service is expected to resolve it (`sessions.get(sessionId)?.header.cwd` → `sandboxPolicy.workspaceRoot` fallback);
- browser console excerpt (showing no renderer errors — rules out client exceptions) and host terminal log;
- reproduction steps: in-place upgrade on the same profile lineage, click in-workspace file link, observe `meta.status`;
- relation to #5999 round 1 and what differs (roster/combo now consistent; only the service read stalls).

**What the host could check at boot so this fails loud:**

- **Self-probe advertised Remotes:** after boot, for each client-advertised Remote/service in the boot manifest (at minimum `api-workspace-files`), execute one real end-to-end call (e.g. a metadata read of a known file) through the same gateway path clients use; a non-answering service should fail boot loudly (or emit a terminal/host-log error naming the service), not surface later as an empty tab.
- **Pending-service detection:** the client already distinguishes "unavailable" — promote that into an actionable state: after a timeout, the tab should show an explicit error with a 重试 action and the missing service name, and emit a console error, instead of a bare 「文件资源服务不可用。」 with no console trace.
- **Invariant between manifest and services:** the manifest lists a module whose service never registers/answers ⇒ log a mismatch at boot (analogous to the round-1 "loaded without registering" signal, but on the Host service side).
- **Old-profile migration coverage:** the seam that upgrades profiles created under 0.1.2/0.1.3 should verify the typert `lookups.register` workspace-root entry resolves for existing sessions at startup, and report the unresolved session instead of leaving reads pending forever.

## Summary of tested competencies

- Layer attribution from evidence: tab-claim miss (by-design scope restriction) vs host Remote/service stall (`status: 'none'` = never answered, not rejected).
- Probe validity: per-entry fetches at their own rev measure artifact serving; a fabricated all-joined URL with one rev measures nothing and must not be cited as "modules missing".
- Distractor separation: paste-input fold warnings are an unrelated message-rendering bug; the textpreview→documentpreview rename explains the claim miss only.
- Mitigation order: no client workaround → clean host restart → pinned rollback to a verified version → upstream report; local host patches are out of bounds.
- Prevention: boot-time end-to-end self-probe of advertised services, loud pending-service errors, and old-profile lookup-resolution checks.

*No files outside the designated output directory were written; the fixture was read only.*
