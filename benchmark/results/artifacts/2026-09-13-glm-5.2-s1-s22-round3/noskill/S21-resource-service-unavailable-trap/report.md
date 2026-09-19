# S21 · "The Resource Service That 'Unavailable'" — Analysis Report

Scope: read-only analysis of the evidence pack under the fixture directory. No fixture,
skill, verifier, or reference files were touched.

## 1. Attribution — which layer actually fails

The tab renders a correct title (so the tab-type module loaded and registered) but the
content area shows 「文件资源服务不可用。」 with `meta.status` stuck at `'none'`. The
**contrast probe** isolates the failing layer precisely:

| Reader | Transport | Result |
|---|---|---|
| file-trace plugin | its own host RPC (`/dsh-file-trace/*`) | reads fine (原文 and 阅读 both render) |
| documentpreview sidebar tab | `api-workspace-files` Remote | fails — metadata never arrives |

What the two readers of the same file rule in / rule out:

- **Ruled in (working):** the file exists on disk; the session's workspace root resolves
  (the address is session-scoped and `.dsh/tmp` sits under the workspace root, which the
  host `read()` doc explicitly allows); the host process can read the file; static client
  artifact serving works (62/62 module probes HTTP 200); the documentpreview tab module
  itself is loaded, registered, and rendering (title + placeholder UI).
- **Ruled out:** a filesystem/permission problem, a missing file, a 404 on the client
  bundle, a JavaScript crash in the tab (F12 shows no red errors from documentpreview or
  the sidebar), and a scope/claim rejection (that produced the *first* dialog for
  outside-workspace links, not this state — the tab opened).

So the failure is in the **runtime service-resolution chain between the sidebar tab and
the workspace-files Remote** — the resource-provider chain did not "take over": the
metadata request is issued (or queued behind a service that never activates) and never
resolves. The observed `meta.status === 'none'` is decisive about *where it stalls*: it
is **not** an error response (`error`/`denied`) and not a completed read — the request
**never completes at all**. The stall is upstream of any file I/O, at the point where the
client-side resource service (note `api-workspace-files` `inject`s
`@deepseek-ai/dsh-client-resources`) should have wired the Remote to the host row. This
is the same failure family as discussion #5999 round 1, narrower: in alpha.1 the
roster/combo mismatch made plugins fail to register; in alpha.2 everything registers but
the resource-service handshake still never completes.

## 2. Probe discipline — which combo probe is valid

- **Valid:** Probe 1 (a single manifest-listed combo URL) and Probe 3 (the per-module
  sweep of all 62 manifest entries, each fetched with its own row and rev suffix):
  62/62 HTTP 200, zero 404s. These measure exactly what they claim — static artifact
  serving of every roster entry — and they measure it with URLs the system actually
  produces.
- **Invalid:** Probe 2 (all 62 entries comma-joined into one ~4–5 KB URL → 404,
  zero-length body). A 404 on a **fabricated** URL that the loader would never issue says
  nothing about module availability. A joined URL of that length is beyond typical
  server/browser URL-length limits, and the combo route is not obliged to accept an
  arbitrary multi-module join across mixed `rev` suffixes. Citing Probe 2 as "modules
  missing" would directly contradict the valid Probe 3 sweep and send the investigation
  into static serving, which the evidence shows is healthy.
- **How the real loader fetches the roster:** it does not join modules. It fetches the
  same-origin `__DSH_BOOT__` boot manifest (HTML-injected), then loads **each roster row's
  own combo URL individually** (`/plugins/??<id>/client.js&rev=<rev>`), each with its
  per-row rev suffix. Any probe of static serving should replicate that shape — which
  Probe 1/3 do and Probe 2 does not.

## 3. Distractor separation

**The `dsh-paste-input` fold-skip warnings are unrelated.** They fire while rendering
*historical paste-attachment messages* in the chat transcript: the plugin tries to
collapse each ```==== DSH_PASTE_INPUT_V1 ====``` marker block into a 📎 chip and the
parse of some historical messages fails. That is a message-bubble rendering concern in a
different subsystem; it touches neither the sidebar tab registry, the resource service,
nor any RPC used by the content read. The fixture's own note confirms the attachment
chain itself was verified working. Simultaneous bugs ≠ causal.

**What actually changed in the roster between the two versions:** the
`ui-sidebar-textpreview` package was **replaced** by `ui-sidebar-documentpreview`
(`cordis.patch.yml` row swapped; the old id has 0 mentions in the alpha.2 boot HTML).

- This change **does** explain the *first* symptom: the old "text" tab type claimed
  `dsh-resource://file/**` (any scope); the new document tab's `canOpen` accepts only
  `parseFileAddress(address)?.scope === 'session'`. Outside-workspace absolute addresses
  are therefore claimed by no tab type → `sidebarRight: no registered tab type claims
  "dsh-resource://file/absolute/…"`.
- It does **not** explain the *second* symptom: for the in-workspace file the new tab
  opens and titles correctly — the rename is behaving as designed there. The content read
  failing with `meta.status 'none'` is a separate defect in the resource-service chain
  (Section 1). Two bugs, two layers, one upgrade.

## 4. Mitigation decision

**The plugin should not work around the unavailable service.** No rewrite, no retry loop,
no fallback transport (e.g., shimming the read through file-trace's RPC). The file *is*
readable via another transport, so any client-side fallback would silently mask a host
regression, split the read path, and break the moment the real service is fixed. The
correct behavior is exactly what the tab already does — render an explicit
"service unavailable" state — ideally with a retry affordance.

Order of action for the maintainer:

1. **First cheap step: a full host restart** (`dsh web` stop/start, not just a page
   refresh). #5999 documents a roster/combo inconsistency after in-place upgrade that a
   restart self-healed once; the same class of stale state may be keeping the
   workspace-files host row from activating for this session even though the row is
   present in `cordis.patch.yml`. Re-test the in-workspace link after restart.
2. **Escape hatch: rollback** to the last known-good published version — per #5999,
   `npm i -g @deepseek-ai/dsh@0.1.3-alpha.2` was verified working on this profile.
   (0.1.5-alpha.1 is *not* a refuge: it had the same failure family, round 1.)
3. **Upstream:** file the forensics (Section 5) as a follow-up on discussion #5999
   (round 2 / comment 18371079), since this is a confirmed regression of the same family
   in the next alpha.

## 5. Prevention / upstream

**A complete upstream report needs:**

- Versions: before/after (`0.1.5-alpha.1 → 0.1.5-alpha.2`), install mode (npm global,
  in-place), profile age (created under 0.1.2/0.1.3), OS (Windows 11), and the list of
  six junction-linked external client plugins.
- The `__DSH_BOOT__` roster excerpt (with the `ui-sidebar-textpreview` →
  `ui-sidebar-documentpreview` census) and the relevant `cordis.patch.yml` rows
  (including the workspace-files host row).
- The probe evidence: per-module sweep (62/62 = 200) *and* an explicit statement that the
  joined-URL 404 is not evidence — plus how the loader actually fetches (manifest →
  per-row combo URLs).
- The contrast probe: file-trace RPC succeeds vs documentpreview Remote stalls with
  `meta.status 'none'` — this is the key attribution artifact.
- Console excerpt (no red errors; only unrelated `dsh-paste-input` warnings) and host
  terminal output ("[dsh-profiles] ready", no errors).
- The session facts the service resolves from: `sessions.get(sessionId)?.header.cwd` and
  the `sandboxPolicy.workspaceRoot` fallback value for the failing session, so upstream
  can check the typert `lookups.register` path.
- A network/HAR capture of the RPC that never completes (request issued, no response),
  and ideally host-side logs instrumenting the workspace-files Remote activation.

**What the host could check at boot so this fails loud:**

- **Roster/combo consistency assertion:** at boot, HEAD/GET every roster row's combo URL
  (or at least the injected-dependency spine like `api-workspace-files`) and refuse to
  print the web URL — or print a loud warning — on any non-200. This converts the silent
  #5999-style mismatch into a boot-time failure.
- **Client service-activation assertion:** when a client plugin declares `inject`
  (e.g., `api-workspace-files` → `@deepseek-ai/dsh-client-resources`), the loader
  should log loudly — and surface in the UI — if the injected service never activates
  within a deadline, instead of letting dependent reads stall forever.
- **Read-deadline + error state in tabs:** a resource read that stays at
  `status 'none'` past a timeout should escalate the placeholder to an actionable error
  (message + retry + "copy diagnostics"), not a bare 「文件资源服务不可用。」.
- **Claim-coverage warning:** on startup or link click, warn when a `dsh-resource://`
  address scheme (e.g. `file/absolute/…`) is claimable by no registered tab type, so
  scope-narrowing renames like textpreview → documentpreview are visible as an
  intentional behavior change rather than a mystery dialog.
