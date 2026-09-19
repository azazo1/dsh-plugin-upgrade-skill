# S21 · The Resource Service That Went "Unavailable" — Analysis Report

Scope: read-only analysis of the evidence pack for the dsh 0.1.5-alpha.1 → 0.1.5-alpha.2
in-place npm-global upgrade on Windows (profile created under 0.1.2/0.1.3, six external
client plugins junction-linked). No fixture files were modified.

## Evidence basis

- `symptom-log.txt` — timeline: two distinct failures (absolute-scope tab-claim error, then session-scoped tab that opens but renders 「文件资源服务不可用。」)
- `boot-manifest-excerpt.txt` — `__DSH_BOOT__` roster: `ui-sidebar-right` present, `ui-sidebar-textpreview` ABSENT (replaced by `ui-sidebar-documentpreview`)
- `combo-probe.txt` — per-module sweep 62/62 HTTP 200; all-entries-joined URL 404
- `contrast-probe.txt` — two readers of the same file: file-trace's own RPC works; the documentpreview tab's read never arrives (`meta.status` stays `'none'`)
- `console-excerpt.txt` — no sidebar/resource console errors; only `dsh-paste-input` fold-skip warnings
- `discussion-excerpt.txt` — prior round (#5999): roster/combo mismatch self-healed by restart, but the same content-read failure persisted; rollback verified

---

## 1. Attribution: which layer actually fails

**The failing layer is the api-workspace-files Remote resource-provider chain (the file
resource service the documentpreview tab depends on), not the filesystem, not the tab
registry, and not static artifact serving.**

What each observation pins down:

- **The tab shell works.** The tab opens with a correct title, so `ui-sidebar-documentpreview`
  loaded, its tab type is registered in `sidebarRight`, and its `canOpen` accepted the
  session-scoped address. The earlier "no registered tab type claims dsh-resource://file/absolute/…"
  dialog was the *previous*, different defect (see §3); for the in-workspace file, claiming succeeds.
- **The host filesystem works.** The file-trace plugin reads the very same file at the same
  moment through its own host RPC (`/dsh-file-trace/*`), in both 原文 and 阅读 modes. So the
  file exists, host-side file access is functional, and session workspace resolution cannot be
  broadly broken.
- **The read never starts.** In the failing tab, `meta.status` stays `'none'` — not an error
  status, not a partial read. That means the client's request for file resource metadata never
  produced *any* answer: the call into the workspace-files Remote either never reaches a live
  provider or its response never arrives. The read stalls at the **service-availability /
  dispatch step, before a read is attempted** — which is exactly what the rendered string
  「文件资源服务不可用。」("file resource service unavailable") states. The UI is honestly
  reporting a service-level failure, not a file-level one.

**The two readers of the same file rule in/out as follows:**

| Reader | Transport | Result | Rules out / rules in |
|---|---|---|---|
| file-trace plugin | its own HTTP RPC face, independent of the workspace-files service | reads fine | Rules out: file missing, host FS permissions, session cwd/workspace-root resolution in general, auth to the host |
| documentpreview tab | `api-workspace-files` Remote (service injected per the boot manifest row) | fails, `meta.status = 'none'` | Rules in: the failure is specific to the workspace-files Remote chain — the client plugin is served and loaded (200s, tab renders), but the host-side service it injects/depends on does not answer |

So: **transport + artifact serving + tab registration = healthy; the workspace-files
resource-provider service on the host = not answering.** The host row for workspace-files
*is* in the web-app bundle patch and its module *is* served, so this is a
registration/handoff failure (the resource-provider chain "did not take over", as the prior
round in #5999 already observed), not a missing artifact.

## 2. Probe discipline: which combo probe is valid

- **Valid: the per-module sweep (Probe 3), and Probe 1's single-module combo.** Each fetches
  exactly a URL that appears in the boot manifest. 62/62 HTTP 200 is a legitimate measurement
  of **static artifact serving**: every module the 0.1.5-alpha.2 host lists is actually
  served at its declared rev. It conclusively rules out "modules missing / combo route
  broken" for this round.
- **Invalid: the all-in-one join (Probe 2).** Joining all 62 entries into one ~4–5 KB URL
  constructs a request **the real loader never makes**. Its 404 with zero-length body is an
  artifact of the probe itself (the route does not serve arbitrary ad-hoc groupings / a URL
  that long), not a property of the deployment. Citing it as "modules missing" would be a
  measurement error: it measures an unsupported URL shape, not artifact availability — and
  it directly contradicts the valid per-module sweep of the very same entries.
- **How the loader actually works:** the client receives the roster in the boot manifest
  (`__DSH_BOOT__`, fetched same-origin), and fetches **each entry's own declared URL**
  (per-module or the specific combos the host emitted), honoring each entry's `rev` stamp
  and `inject` list. It does not concatenate the roster into one request. Any probe must
  therefore replay the manifest's own URLs (as Probe 1/3 do) to be a valid measurement.

## 3. Distractor separation

**The `dsh-paste-input` fold warnings are unrelated.** They come from a different external
plugin, operate on message-bubble text (collapsing the ```==== DSH_PASTE_INPUT_V1 ====`
marker blocks), and repeat once per historical paste-attachment message. They share no code
path, service, or transport with the sidebar's file-resource read; the console shows **no**
errors from documentpreview, the sidebar, or the resource system. Two simultaneous,
independent defects — keep them separate.

**The roster change that DID happen:** 0.1.5-alpha.2 replaced
`packages/client/ui-sidebar-textpreview` with `packages/client/ui-sidebar-documentpreview`
(the boot manifest census confirms: textpreview 0 mentions; the web-app `cordis.patch.yml`
now carries the documentpreview row). Consequences:

- The old "text" tab type, which claimed `dsh-resource://file/**` (any scope), is gone.
- The new document tab's `canOpen` accepts only `parseFileAddress(address)?.scope === 'session'`.

**This fully explains timeline step 2** — the outside-workspace absolute-scope link
(`dsh-resource://file/absolute/E:/…`) now has *no claiming tab type*, hence "no registered
tab type claims …". That is intended-behavior-under-the-rename territory (a scope-policy
narrowing), not a bug in serving.

**It does NOT explain the content-read failure.** For the in-workspace file, the new tab
type *does* claim the address and the tab opens; what fails is the metadata read through
the workspace-files Remote (`meta.status = 'none'`). The rename changed which tab claims
what; it did not touch the host-side resource-provider chain. The content failure is the
same one that survived the restart in the alpha.1 round (#5999): the resource-provider
chain does not take over even when everything serves. Two changes, two symptoms, one
coincidence in time.

## 4. Mitigation decision

**Should the plugin work around it? No.** No rewrite, no retry loop, no client-side
fallback reader:

- The contrast probe proves host file access is fine; the failing seam is a
  **host-provided service** the client injects. A client fallback (e.g., shelling out to
  file-trace's RPC or another reader) would duplicate the resource stack, mask the upstream
  regression, and break again the moment the real service is fixed.
- Retrying is pointless: `meta.status = 'none'` is not a transient read error; the service
  never answered on a clean boot with zero console errors — there is nothing to retry into.
- The correct client behavior is what it already does: report "service unavailable"
  distinctly (ideally with a retry affordance and diagnostics, see §5).

**Order of action for the maintainer:**

1. **First cheap step: full restart of the host + a hard browser refresh.** The prior round
   (#5999) shows a restart once self-healed a roster/combo mismatch; a stale browser-side
   roster/rev from the pre-upgrade page is also free to eliminate. Verify the workspace-files
   host plugin actually activated on the new boot (its services present in the host's
   service list).
2. **Escape hatch: rollback** to the last known-good published version
   (`npm i -g @deepseek-ai/dsh@0.1.3-alpha.2` — verified working in #5999 for this
   deployment). Given the prior round's restart only fixed serving and *not* the resource
   chain, do not burn unlimited time on alpha.2 if step 1 doesn't clear it.
3. **Upstream:** file the forensic package (§5) as round 2 on discussion #5999 / an issue, so
   the registration/handoff defect in the workspace-files resource-provider chain is fixed at
   the source. Only an upstream fix makes the upgrade viable.

## 5. Prevention / upstream

**A complete upstream report needs:**

- Exact versions: from (`0.1.5-alpha.1`) / to (`0.1.5-alpha.2`), plus the profile's origin
  version (0.1.2/0.1.3) and OS/install mode (Windows 11, npm global, in-place, junction-linked
  external plugins — list all six).
- Full `__DSH_BOOT__` roster dump and the web-app `cordis.patch.yml` rows (host + client),
  with `rev` stamps, showing workspace-files present-and-served yet not answering.
- Network trace (HAR or DevTools export) of the actual resource-metadata RPC from the
  documentpreview tab — showing the request pending/never answered — contrasted with the
  file-trace RPC succeeding for the same path at the same timestamp.
- Host-side boot/terminal logs around plugin activation, specifically whether the
  workspace-files host plugin reports activation and whether its resource service is
  registered; the session's resolved workspace root (`sessions.get(sessionId)?.header.cwd`
  vs `sandboxPolicy.workspaceRoot` fallback) for the affected session.
- The probe results: per-module sweep (62/62 × 200) to rule out serving, and an explicit
  note that the joined-URL 404 is a probe artifact, not evidence.
- Console excerpt demonstrating zero client-side errors (rules out client throw paths).

**What the host could check at boot so this fails loud instead of an empty tab:**

- **Self-probe the roster:** after assembling the boot roster, fetch each emitted combo/module
  URL from the host itself and fail loud (log + boot warning surfaced in the Web UI) on any
  404/rev mismatch, instead of shipping a roster the route can't serve.
- **Service-presence invariant for client injections:** for every roster entry's `inject`
  list (e.g. `@deepseek-ai/dsh-api-workspace-files` injecting
  `@deepseek-ai/dsh-client-resources`), verify at boot that a live provider for the required
  service exists; if a client plugin injects a service with no provider, refuse or warn
  prominently rather than letting the client render "unavailable" with no diagnostics.
- **Degrade visibly:** when a resource service is unreachable, the tab should show an error
  state with the failing service name, a retry action, and a link to boot diagnostics —
  never a bare 「文件资源服务不可用。」 with no error object, matching the current
  zero-console-error silence that made attribution require a contrast probe.
- **Rename guardrails:** when a client package is renamed/replaced (textpreview →
  documentpreview), a boot-time check that every address scheme previously claimable still
  has a claiming tab type (or that the narrowing is intentional and logged) would have
  turned the absolute-scope dialog into a documented behavior change instead of a surprise.

---

## Summary of answers

1. **Attribution** — the workspace-files Remote resource-provider service fails to answer;
   the tab shell and host FS are proven healthy by the two readers (file-trace RPC reads
   fine; the tab's read stalls pre-read with `meta.status = 'none'`, i.e. a service-level
   stall, not a file error).
2. **Probe discipline** — the per-module sweep is the valid measurement (62/62 × 200 ⇒
   serving is fine); the all-in-one joined URL is an unsupported request shape the loader
   never makes and must never be cited as "modules missing". The loader fetches the boot
   manifest roster and each entry's own URL per its `rev`.
3. **Distractors** — paste-input fold warnings are an unrelated plugin's message-parsing
   noise; the roster change (textpreview → documentpreview, `canOpen` narrowed to
   session scope) explains the absolute-scope dialog only, not the content-read failure.
4. **Mitigation** — no client workaround; restart + hard refresh first, rollback to
   0.1.3-alpha.2 as the escape hatch, upstream fix as the real resolution.
5. **Prevention** — full forensics (versions, roster, patch rows, HAR of the unanswered RPC,
   host activation logs, session workspace resolution, probe data) plus boot-time roster
   self-probes, inject-list service-presence checks, and visible degradation with
   diagnostics in the tab.
