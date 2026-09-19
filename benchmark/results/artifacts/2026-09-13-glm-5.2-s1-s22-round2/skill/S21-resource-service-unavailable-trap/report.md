# S21 · The Resource Service That "Unavailable" — Read-Only Diagnosis (Mode A)

Task: attribute a runtime file-read failure on dsh 0.1.5-alpha.1 → 0.1.5-alpha.2 (npm-global
in-place upgrade, Windows, profile created under 0.1.2/0.1.3, six junction-linked external
client plugins). Evidence pack read in full; no writes anywhere except this report.

## 1. Attribution — which layer actually fails

**The failing layer is the workspace-files resource-service chain (client Remote → host
service), not the tab registry, not the file, and not static artifact serving.**

What the two readers of the same file rule in and rule out (contrast-probe.txt):

| Reader | Transport | Result | Rules out / rules in |
|---|---|---|---|
| file-trace plugin | its own host RPC (`/dsh-file-trace/*`) | reads fine (原文 and 阅读 both render) | Rules out: file missing/locked, filesystem permissions, session workspace-root resolution, the host process being broken generally. The bytes are reachable over *some* HTTP face. |
| documentpreview sidebar tab | `api-workspace-files` Remote (injected `@deepseek-ai/dsh-client-resources`) | fails; `meta.status` stays `'none'` | Rules in: the failure is specific to the **resource-service Remote chain** the tab depends on. |

The tab renders a **correct title** — so the *tab-type layer* works: the alpha.2
`ui-sidebar-documentpreview` package loaded, registered its document tab, and its
`canOpen` accepted the session-scoped address (`parseFileAddress(address)?.scope ===
'session'`). Registration and routing succeeded; the content fetch never produced a result.

**What `meta.status` staying `'none'` says:** the read stalls *before any terminal
outcome* — no success, no file error, no permission denial. That is the signature of a
service-resolution/Remote-handshake stall: the client tab resolved its UI dependencies and
issued (or tried to issue) the read through a service that never answers — i.e. the
`dsh-client-resources` / `api-workspace-files` provider chain "did not take over" on this
boot, exactly as in the 0.1.5-alpha.1 round of the same family (discussion #5999). It is a
*durability/activation* problem on the service path, not a data problem.

Consistency with the corridor cards: alpha.2 reworked exactly this seam —
DSH-0.1.5-A2-01 (`workspaceFiles` moves to a Typert `workspaceFileScope` lookup,
`absolute` scope authorization changes) and DSH-0.1.5-A2-14 (`client-resources` drops
`reload` from `ResourceSnapshot`/`ResourceProvider`). A profile whose client side was
junction-linked under 0.1.2/0.1.3 and upgraded in place is a prime candidate for the
service chain failing to re-wire, while per-module artifact serving (probe 3) is healthy.

The **first symptom** in the timeline (outside-workspace link → `no registered tab type
claims "dsh-resource://file/absolute/…"`) is *not* the same failure: it is the documented
alpha.2 behavior change — the old `text` tab type registered by `ui-sidebar-textpreview`
claimed `dsh-resource://file/**`; the replacement `ui-sidebar-documentpreview` document
tab accepts only `scope === 'session'` (boot-manifest-excerpt.txt note; card
DSH-0.1.5-A2-09). Absolute-scope links are simply no longer claimed by any tab type. Two
different layers, two different causes.

## 2. Probe discipline — which combo probe is a valid measurement

- **Valid: Probe 3 (per-module sweep, 62/62 HTTP 200, zero 404s).** It requests each entry
  exactly as the boot manifest advertises it. It measures static artifact serving, and it
  says the artifacts are all served correctly at the running rev. Probe 1 (the manifest's
  own first combo URL → 200) is likewise valid for the combo route itself.
- **Invalid: Probe 2 (all 62 entries joined into one URL → 404).** It must **never** be
  cited as "modules missing", because:
  1. It is a *synthesized* URL the loader never constructs — the combo route serves the
     combos the host actually composes, not an arbitrary concatenation of every roster
     entry;
  2. the joined URL is ~4–5 KB long, well past practical URL-length limits, and combining
     62 modules in one request is not a shape the route supports;
  3. the 404 with a zero-length body is therefore an *expected rejection of a malformed
     request*, carrying zero information about module availability. The per-module sweep
     directly contradicts any "missing modules" reading.
- **How the real loader fetches the roster:** it reads the `__DSH_BOOT__` boot manifest
  embedded in the served page and requests the entries/combos exactly as advertised
  (per-module or the host-composed combo URLs with their `rev`), at same-origin. Probing
  must mimic that; measuring artifact serving means per-entry fetches, not invented joins.

(Minor evidence discrepancy worth recording in the upstream report: the manifest excerpt
header says "Total entries: 60" while the probe sweeps 62 entries — reconcile when
collecting forensics.)

Note also what the valid probes rule out: the alpha.1 failure family (DSH-0.1.5-A1-20 /
#5999 round 1 — roster lists modules the combo route 404s at the same rev) is **not**
present here: every entry serves. The alpha.2 symptom is narrower and downstream of
artifact serving.

## 3. Distractor separation

**The `dsh-paste-input` fold warnings are unrelated.** They come from a different plugin
parsing *historical paste-attachment messages* for bubble collapsing; the console excerpt
itself states the marker protocol and attachment-directory chain were verified working and
do not depend on snapshot internals. They repeat once per historical message — a cosmetic,
self-contained bug in that plugin. Nothing in the failing path (documentpreview tab →
workspace-files Remote) touches paste-input. No red console errors from documentpreview or
the sidebar is itself diagnostic: the read fails silently by never resolving, not by
throwing.

**Roster change between the two versions:** `ui-sidebar-textpreview` is gone (0 mentions
in the boot HTML); `ui-sidebar-documentpreview` replaced it (the web-app bundle's
`cordis.patch.yml` row swap, card DSH-0.1.5-A2-09), and with it the tab-type claim
change: old `text` tab claimed `dsh-resource://file/**`; the new document tab accepts
only session scope. **This change explains symptom 2 of the timeline** (the
outside-workspace absolute link finding no claimant) **but not the content-read failure**:
the inside-workspace file *is* accepted (tab opens, correct title), and the failure occurs
afterwards in the resource-service chain. Keep the two symptoms attributed separately.

## 4. Mitigation decision — order of action

**The plugin should NOT work around the unavailable service.** No rewrite, retry, or
fallback in plugin code:

- the failing surface (`api-workspace-files` Remote, `client-resources`,
  `ui-sidebar-documentpreview`) is host/bundle-owned, not plugin-owned code — a plugin
  rewriting around it would encode against a moving alpha seam and mask the defect;
- a client-side fallback (e.g. file-trace-style direct read) would silently hide a
  boot-wiring failure that should fail loud upstream;
- retries are inappropriate for what looks like a non-idempotent *activation/wiring* stall,
  not a transient transport error — per the skill's safety boundaries, don't retry
  unattributed internal failures.

**Order for the maintainer:**

1. **First cheap step — clean full restart:** fully stop every dsh process (a browser
   refresh is not a host stop), restart `dsh web`, hard-refresh the browser, re-verify
   version markers and the six plugins. DSH-0.1.5-A1-20 documents that an in-place
   npm-global upgrade leaves roster/combo state inconsistent and a host restart self-heals
   it; #5999 round 1 confirms on this very deployment. If the tab then reads: done (note
   that in the alpha.1 round the *content read* still failed after the restart — so verify
   the actual read, not just module serving).
2. **If it persists, verify enablement/wiring (read-only):** confirm the resolved profile
   composition points at the alpha.2 bundle with the `workspace-files` host row active,
   that the session's workspace root resolves (session header cwd / sandboxPolicy
   fallback), and that the `client-resources` service and the workspace-files Remote are
   actually registered/answered host-side — attribute to dsh-runtime before touching
   anything.
3. **Escape hatch — rollback:** from an **external terminal** with the host fully stopped,
   pinned re-install of the last known-good published version (`npm i -g
   @deepseek-ai/dsh@0.1.3-alpha.2` was verified as the escape hatch in #5999; 0.1.5-alpha.1
   is the alternative if its roster bug is tolerable). Never run the global install from
   inside a dsh session on that host — the session *is* the host process and dies
   mid-install leaving the shims gone. A bare `npm i -g @deepseek-ai/dsh` must also be
   avoided (resolves `latest`, can silently change lines).
4. **Upstream:** file the forensics (section 5) as round 3 of discussion #5999 / a new
   issue — this is a dsh-runtime defect (resource-provider chain not taking over after
   in-place upgrade on an old profile), not a plugin bug to code around.

## 5. Prevention / upstream

**A complete upstream report needs:**

- exact from/to versions and install channel (0.1.5-alpha.1 → 0.1.5-alpha.2, npm global,
  in-place), OS (Windows 11), Node version, and the pinned install command used;
- profile provenance: created under 0.1.2/0.1.3, the six junction-linked external client
  plugins listed with their versions and DSH dependency cohorts;
- the full `__DSH_BOOT__` boot manifest (HTML/roster with rev) — including the 60-vs-62
  entry-count reconciliation — and the web-app bundle's `cordis.patch.yml` rows
  (workspace-files present, textpreview→documentpreview swap);
- the probe set: per-module sweep results (62/62 200) and a note that joined-URL probing
  is invalid (so nobody downstream "cites" the 404);
- the contrast probe verbatim (file-trace RPC reads fine vs documentpreview Remote stalls,
  `meta.status` stuck at `'none'`), with the session id and both file addresses
  (absolute-scope and session-scoped);
- host terminal log across the restart, browser console excerpt (no red errors;
  paste-input warnings flagged as unrelated), and whether a host restart changed anything;
- pointers to prior art: #5999 rounds 1–2 and skill card DSH-0.1.5-A1-20 for the
  roster/combo family, DSH-0.1.5-A2-01/A2-14 for the reworked seam.

**Host-side checks so this class fails loud instead of rendering an empty tab:**

- **Boot-time manifest↔serving self-check:** after building the roster, the host should
  request each advertised entry/combo itself (or otherwise validate the combo route
  answers for every roster row at the current rev) and refuse/warn at boot on any
  mismatch — this would have caught the alpha.1 A1-20 class automatically.
- **Service-availability assertion before serving the page:** the client packages the
  web-app bundle ships (documentpreview, api-workspace-files) inject named services
  (`client-resources`, the workspace-files Remote); the host should assert at boot that
  every service those shipped clients inject is actually provided/activated, so a missing
  provider chain surfaces in the terminal ("[dsh-profiles] ready" alone is not evidence).
- **Client-side: no silent `'none'` forever:** a Remote read that never resolves should
  time out and render an explicit error state (with the failing service named, plus
  retry/report actions), not a bare 「文件资源服务不可用。」 tab with no error and no
  console output — the current presentation hides the failure from both the user and F12.
- **Regression coverage:** a boot smoke on an upgraded-in-place old profile exercising one
  chat file link → sidebar tab → content render end-to-end (the skill's runtime validation
  layer already prescribes proving registration/mount rather than accepting HTTP 200).

## Report structure per the skill

- **pre-existing (baseline)**: not collected — read-only Mode A diagnosis on a fixture
  evidence pack; no repository, build, or test runs were performed.
- **Completed**: evidence pack read in full; failure attributed to the resource-service
  Remote chain; probe validity adjudicated; distractor separated; mitigation order and
  upstream forensics specified. No writes to the fixture or anywhere outside this report
  file.
- **Skipped**: any mutation (restart, rollback, install) — outside read-only scope and the
  fixture is static evidence; reference-solution/verifier untouched by rule.
- **Pending/residual risk**: the exact root cause *inside* the service chain (Typert
  `workspaceFileScope` lookup failure vs Remote handshake vs provider activation) cannot
  be pinned further from static evidence — needs the live boot check from §4 step 2.
  The 60-vs-62 manifest entry count is unreconciled.
- **Rollback**: nothing to roll back (no changes made outside the report file).
- **Recommendations**: the three host-side fail-loud checks above; keep the absolute-scope
  link behavior change documented as intended alpha.2 semantics (consider a friendly
  "outside-workspace links are not previewable" message instead of a claim error dialog).
