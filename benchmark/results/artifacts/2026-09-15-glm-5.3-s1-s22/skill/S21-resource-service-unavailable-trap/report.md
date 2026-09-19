# S21 · The Resource Service That "Unavailable" — Analysis Report

Task: S21-resource-service-unavailable-trap (read-only diagnosis)
Evidence: fixture pack from a real 2026-09-09 dsh 0.1.5-alpha.1 → 0.1.5-alpha.2 npm-global
in-place upgrade on Windows 11 (profile created under 0.1.2/0.1.3, six external client
plugins junction-linked). Mode A (inspect) per the plugin-upgrade skill; no migrations,
installs, or writes outside this report.

---

## 1. Attribution — which layer actually fails

**The failing layer is the `api-workspace-files` Remote/service chain, not the host
filesystem, not the sidebar tab-type registry, and not static artifact serving.**

Two independent facts localize it:

- **The tab itself works.** In alpha.2 the replacement package
  `ui-sidebar-documentpreview` registers a document tab whose `canOpen` accepts
  `parseFileAddress(address)?.scope === 'session'`. The in-workspace test file
  (`.dsh/tmp/sidebar-open-test-2.md`, session-scoped address) *is* claimed, the tab
  opens, and the title renders. Tab-type claim and title need no file read; they only
  need the parsed address. So the failure is downstream of tab opening — in content
  acquisition.
- **The two readers of the same file split cleanly** (contrast-probe.txt):
  - `file-trace` reads the same file **fine** over its *own* HTTP RPC
    (`/dsh-file-trace/*` routes). This rules out: file missing, permissions, host FS
    access, and the session's workspace-root resolution in general host terms.
  - the documentpreview tab reads via the **`api-workspace-files` Remote** and fails.
    The only channel that fails is the one that depends on the workspace-files service
    being live end-to-end (client Remote → gateway → host service → typert
    `lookups.register` workspace-root resolution → FS).

**What `meta.status === 'none'` says:** the read stalls *before any terminal state*.
It is not `'error'`, not "not found", not "denied" — the metadata RPC simply never
arrives/never resolves. That is the signature of a **service-availability stall**: the
client-side Remote has no working provider to answer (the service is in the roster and
its module serves 200, but the host-side service/provider chain never took over — same
family as the alpha.1 round in discussion #5999, where "the resource-provider chain did
not take over" persisted even after the roster/combo mismatch self-healed). The string
「文件资源服务不可用。」 is the tab's graceful degradation for exactly this condition.

Corroborating exclusions:

- The host row **is** in the web-app bundle patch (`cordis.patch.yml` carries
  `workspace-files`), so this is not a missing composition row.
- Files outside the workspace are documented as allowed, and the failing file is inside
  the workspace anyway — scope policy is not the blocker for the content read.
- F12 shows **no** errors from documentpreview or the resource system — consistent with
  a call that never completes, not one that throws.

(Note the two dialogs are two different bugs: dialog 1 — "no registered tab type
claims `dsh-resource://file/absolute/…`" for an out-of-workspace link — is the
alpha.2 tab-type narrowing, see §3. Dialog 2 — the empty tab — is the service
unavailability analyzed here.)

## 2. Probe discipline — which combo probe is valid

- **Valid measurement of static artifact serving: Probe 3, the per-module sweep
  (62/62 HTTP 200).** Each request uses exactly the addressing the manifest itself
  advertises (one module id + its `rev`), the same shape as the boot manifest's own
  per-entry URLs (Probe 1 confirms the single-module form serves). 62/62 with zero 404s
  is sound evidence that **every roster artifact is served at its rev** — the
  alpha.1-era roster/combo mismatch is *not* present this round.
- **Invalid: Probe 2, the all-62-joined single URL (404).** It must never be cited as
  "modules missing" because its 404 is an artifact of the probe's own construction, not
  of the server's inventory: joining 62 module ids into one ~4–5 KB combo URL does not
  correspond to any request the platform ever issues, and a 404 with a zero-length body
  on an over-long, semantically unsupported join says nothing about whether the
  individual modules exist — Probe 3 already proves they all do. A negative result from
  a request shape the loader never uses is not a measurement of serving health.
- **How the real loader fetches the roster:** the page reads the `__DSH_BOOT__` boot
  manifest (same-origin), which lists each entry with its *own* `url`
  (`/plugins/??<id>/client.js&rev=<rev-N>`) plus `inject` dependencies; the loader
  requests those per-entry URLs (individually or as the small combos the manifest
  itself encodes). It never synthesizes one giant all-modules join. So the correct
  probe discipline is: enumerate manifest entries → fetch each entry's advertised URL
  at its advertised rev → compare; that is Probe 1/Probe 3, and they pass.

## 3. Distractor separation

- **`dsh-paste-input` "fold skipped (parse failed)" warnings: unrelated.** They come
  from a different subsystem — collapsing verbose paste-attachment marker blocks
  (`==== DSH_PASTE_INPUT_V1 ====`) in *historical message bubbles*. They share no
  transport, service, or code path with the sidebar's `api-workspace-files` Remote,
  they are warnings (not errors), and the console shows zero output from
  documentpreview or the resource system. Simultaneous bugs, not one bug.
- **What actually changed in the roster between alpha.1 and alpha.2:**
  `ui-sidebar-textpreview` is **absent** (0 mentions) — the alpha.2 tree replaced it
  with `ui-sidebar-documentpreview`, and the web-app `cordis.patch.yml` now carries
  the documentpreview row with the textpreview row removed.
- **Does that change explain the symptom? Partly — it explains dialog 1 only.** In
  alpha.1 the "text" tab type registered by `ui-sidebar-textpreview` claimed
  `dsh-resource://file/**` (any scope); the alpha.2 document tab claims only
  `scope === 'session'`. Hence out-of-workspace `file/absolute/…` links now find no
  claiming tab type → "no registered tab type claims …". That is an intended-scope
  narrowing, not a fault. It does **not** explain the empty tab: for the session-scoped
  file the new tab type claims, opens, and titles correctly, and the content failure is
  the never-arriving metadata (§1). The roster change and the service stall are two
  separate findings that happen to co-occur on the same boot.

## 4. Mitigation decision — order of action

**No, the plugin should not work around it.** No rewrite, retry loop, or fallback
reader in plugin code: the host FS demonstrably works (file-trace reads the same file),
the artifact serving works (62/62), and the tab type works. The defect is in the
host-side service takeover for `api-workspace-files` after the in-place upgrade;
papering over it client-side would mask an upstream regression and bake
version-specific hacks into the plugin. The skill's boundary applies: record both
observations, reproduce, report upstream — do not silently pick a side.

Order for the maintainer:

1. **First cheap step: full host restart** (completely stop `dsh web`, start again,
   hard-refresh the browser). #5999 documents that a restart once self-healed the
   roster/combo mismatch on this profile family; an in-place npm upgrade can leave the
   running host serving a stale combo/roster state. Cost: seconds; must be tried and
   its outcome recorded before anything else.
2. **Escape hatch: pinned rollback to the last known-good published version** —
   from an *external* terminal with the host fully stopped (skill's host-upgrade
   discipline; a bare package name can silently resolve `latest` to an older line):
   `npm install -g @deepseek-ai/dsh@0.1.3-alpha.2` (verified working in #5999), then
   restart and hard-refresh.
3. **Upstream: report it.** Append the round-2 forensics to discussion #5999 (the
   fixture notes round 2 was appended as comment 18371079) with the full evidence pack
   (§5). Only after an upstream fix ships should the plugin consider anything — and
   even then, nothing is needed plugin-side, because the plugin consumed the public
   seam correctly.

## 5. Prevention / upstream — forensics and boot checks

**A complete upstream report needs:**

- exact corridor: `0.1.5-alpha.1 → 0.1.5-alpha.2`, npm-global in-place upgrade,
  install command as run, and the client combo served *before* vs *after* restart;
- host/platform facts: Windows 11, profile created under 0.1.2/0.1.3, six external
  junction-linked client plugins, `dsh web` restart timestamps;
- boot manifest excerpt (`__DSH_BOOT__` roster with revs; the ui-sidebar-textpreview →
  ui-sidebar-documentpreview replacement);
- probe results *with methodology*: per-module sweep 62/62 × HTTP 200 (valid), and the
  explicit note that the all-joined 404 is a construction artifact, not evidence;
- the contrast probe: file-trace's own RPC succeeding vs the documentpreview tab's
  `api-workspace-files` Remote stalling at `meta.status: 'none'`;
- console excerpt showing no documentpreview/resource errors (the absence is evidence
  of a stall, not a throw);
- host-side activation state: whether the workspace-files host service actually
  activated on that boot (its row is in `cordis.patch.yml`; the typert
  `lookups.register` workspace-root resolution entry — `sessions.get(sessionId
 )?.header.cwd` fallback `sandboxPolicy.workspaceRoot` — is a prime suspect to
  instrument);
- reproduction: does a *fresh* profile on alpha.2 reproduce, or only this aged
  0.1.2/0.1.3-created profile? That isolates profile-age/stale-state vs pure code
  regression.

**What the host could check at boot so this fails loud:**

- **Artifact/roster self-check:** after building the boot manifest, the host fetches
  each advertised entry URL at its advertised rev (server-side or via a startup probe)
  and refuses to serve the page — or loudly banners — on any miss, instead of letting
  the client discover 404s or silently-degraded modules one by one. This converts the
  alpha.1 roster/combo mismatch class into a boot-time failure.
- **Remote-provider liveness assertion:** for every client roster entry that
  `inject`s a Remote-backed service (`api-workspace-files`, `client-resources`,
  …), verify at boot that the host-side provider actually registered and answers a
  cheap handshake (e.g. a metadata HEAD for a known session root) before advertising
  the entry. "Row present in patch yml" ≠ "service live".
- **Client-side terminal states:** the documentpreview tab should never render a bare
  「文件资源服务不可用。」 for an indefinite `meta.status: 'none'`. The Remote call
  needs a timeout, an error surfaced to the console/telemetry, and a retry affordance
  in the tab — so a stalled provider is visible in F12 and distinguishable from
  "file missing".
- **Named attribution:** the degradation string should name the missing dependency
  (which service, which entry, which rev), matching how the alpha.1 round named the
  first unregistered entry — that made triage possible; "service unavailable" with no
  console trace made this round ambiguous between serving, claiming, and reading.

---

## Summary table

| Question | Answer |
|---|---|
| Failing layer | `api-workspace-files` Remote/service chain stalls (`meta.status: 'none'`); host FS, tab registry, artifact serving all fine |
| Valid probe | Per-module sweep (62/62 200) at each entry's advertised URL/rev |
| Invalid probe | All-62-joined URL 404 — construction artifact; the loader never issues such a URL |
| Roster change | `ui-sidebar-textpreview` → `ui-sidebar-documentpreview`; explains the absolute-link claim error only, not the empty tab |
| paste-input warnings | Unrelated (message-bubble folding of paste markers) |
| Plugin workaround | No — host-side regression; restart → pinned rollback (0.1.3-alpha.2) → upstream report to #5999 |
| Prevention | Boot-time roster/rev self-check, Remote-provider liveness handshake, client timeout + named error |

*No files outside the designated output directory were modified; the fixture was read
only.*
