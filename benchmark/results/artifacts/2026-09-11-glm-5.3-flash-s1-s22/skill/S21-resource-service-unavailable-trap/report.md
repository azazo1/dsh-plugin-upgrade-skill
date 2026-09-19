# S21 Diagnostic Report — The Resource Service That "Unavailable"

Deployment: dsh 0.1.5-alpha.1 → 0.1.5-alpha.2, in-place npm-global upgrade, Windows 11,
profile created under 0.1.2/0.1.3, six external client plugins junction-linked.
Evidence pack: `environment/fixture/` (README.md, symptom-log.txt, boot-manifest-excerpt.txt,
combo-probe.txt, contrast-probe.txt, console-excerpt.txt, discussion-excerpt.txt).
Skill framing: plugin-upgrade Mode A (read-only inspection / post-upgrade diagnosis); no
files were modified and no installs or migrations were run.

## 1. Attribution — the failing layer is the workspace-files resource metadata chain, not static serving and not the file itself

Three candidate layers exist for "tab renders a title but no content": (a) static client
artifact serving, (b) the tab plugin's registration, (c) the runtime resource read that
fills the tab's content.

- (a) is ruled out: `symptom-log.txt` step 5 and `combo-probe.txt` Probe 3 show all 62
  manifest modules serve individually with HTTP 200 — the module containing the tab loaded.
- (b) is ruled out: the tab opens at all, with the correct title
  ("sidebar-open-test-2.md"), so `ui-sidebar-documentpreview` registered its tab type and
  mounted. Compare symptom step 2, where the out-of-workspace link got
  `sidebarRight: no registered tab type claims "dsh-resource://file/absolute/…"` — that is
  what layer (b) failure looks like, and this is not it.
- (c) is where it fails. `contrast-probe.txt` runs two readers of the *same file at the
  same moment*:
  - the file-trace plugin via its own host RPC (`/dsh-file-trace/*`): **reads fine**,
    原文 and 阅读 modes both show content — so the file exists, is readable, and the Host
    filesystem path is intact;
  - the documentpreview sidebar tab via the `api-workspace-files` Remote: **fails**, and
    the decisive detail is that `meta.status stays 'none'`.

  A metadata `status` of `'none'` means the resource snapshot was never populated at all:
  the read request stalls before any file content or error status is produced. This is not
  a "read returned an error" state (which would surface a status or message); it is the
  provider chain for the workspace-files resource never completing/arriving. This matches
  the prior-art note in `discussion-excerpt.txt`: on the alpha.1 round "the sidebar tab's
  content read STILL failed (文件资源服务不可用) — the resource-provider chain did not take
  over."

Host-side corroboration in `contrast-probe.txt`: the workspace-files host row **is** in the
bundle patch (`cordis.patch.yml: "- id: workspace-files / name: '@deepseek-ai/dsh-api-workspace-files'"`),
and the service resolves each session's workspace root through a Typert
`lookups.register` entry (`sessions.get(sessionId)?.header.cwd`, falling back to
`sandboxPolicy.workspaceRoot`). Per the skill's 0.1.5-alpha.2 card **DSH-0.1.5-A2-01**,
this exact edge rewires that surface: `workspaceFiles` drops the `Agent` first parameter
for a Typert `workspaceFileScope` lookup, and a failed lookup surfaces as
`gateway/lookup-not-found`. A stalled metadata fetch with `status: 'none'` is consistent
with that lookup/provider chain not resolving on this upgraded profile — the request never
reaches a successful Host read, while an independent RPC face (file-trace) proves the Host
side is healthy.

Note also: the file IS inside the workspace root (`.dsh/tmp/` under
`E:\deepseek-harness\test-lhh010`), and per the alpha.2 read()` doc quoted in the
contrast probe, out-of-workspace files are allowed anyway — workspace-root containment is
not the blocker.

## 2. Probe discipline — the per-module sweep is valid; the all-joined URL is not

`combo-probe.txt` contains three probes:

- **Valid — Probe 1** (single module from the boot manifest:
  `/plugins/??@deepseek-ai/dsh-api-gateway/client.js&rev=234716e8f7370214-0` → 200,
  73 616 bytes) and **Probe 3** (all 62 manifest entries fetched one by one → 62/62 HTTP
  200). These replicate exactly what the real loader does: the boot manifest
  (`__DSH_BOOT__`, see `boot-manifest-excerpt.txt`) lists one URL per module
  (`{"id":"…","url":"/plugins/??<that-module>/client.js&rev=…"…}`), and the loader fetches
  each roster entry individually. Probe 3 therefore measures static artifact serving
  faithfully and answers: **no modules are missing**.
- **Invalid — Probe 2** (all 62 entries comma-joined into one ~4–5 KB URL → 404,
  zero-length body). Nothing in the host or the loader ever issues such a request; the
  combo route simply is not contracted to serve a 62-module hand-joined URL of that
  length. A 404 here is an artifact of the probe's own construction (likely URL length /
  route matching), not evidence about any module's availability. Citing Probe 2 as
  "modules missing" would misdirect the entire diagnosis toward a reinstall that the
  62/62 sweep already proves unnecessary — precisely the trap the symptom log's
  "Zero 404s" line closes.

Discipline rule: a probe is valid only when it reproduces the client's actual fetch shape
(per-roster-entry URL with the manifest's `rev`). Any synthetic join must be validated
against the loader's real behavior before its result is attributed to the system.

## 3. Distractor separation — paste-input warnings are unrelated; the textpreview→documentpreview rename explains only the absolute-scope dialog

- The repeated `▲ dsh-paste-input: fold skipped (parse failed)` warnings
  (`console-excerpt.txt`) come from `dsh-paste-input`'s client-side bubble-folding of
  historical paste-attachment messages (``` ==== DSH_PASTE_INPUT_V1 ====` marker
  protocol). They are emitted per historical message regardless of sidebar/resource
  activity, are warnings (not errors), and have no shared code path with the
  workspace-files Remote read. **Unrelated simultaneous bug — keep it separate.**
- What else changed in the roster (`boot-manifest-excerpt.txt`):
  `ui-sidebar-textpreview` is **absent** from the alpha.2 boot manifest; the alpha.2 tree
  replaced `packages/client/ui-sidebar-textpreview` with
  `packages/client/ui-sidebar-documentpreview` (`cordis.patch.yml` carries the
  documentpreview row; the old textpreview row is gone). This matches skill card
  **DSH-0.1.5-A2-09** (rename) and the excerpt's behavioral note: in alpha.1 the "text"
  tab type claimed `dsh-resource://file/**`; in alpha.2 documentpreview's `canOpen`
  accepts only `parseFileAddress(address)?.scope === 'session'`.
- Does that rename explain the symptom? Only partially. It **fully explains symptom
  step 2** — the out-of-workspace link
  (`dsh-resource://file/absolute/E:/deepseek-harness/dsh-input-history/package.json`) has
  scope `absolute`, which no tab type claims anymore in alpha.2 → "no registered tab type"
  dialog. It **does not explain step 3**: the in-workspace test file has scope `session`,
  its tab opens — and its content read still fails. The content failure is the separate
  resource-provider chain problem from §1, present in both versions (per
  `discussion-excerpt.txt`, it persisted across the alpha.1 self-heal too).

## 4. Mitigation decision — do not work around it in the plugin; restart first, roll back as the escape hatch, report upstream

- **The plugin should NOT work around the unavailable service.** The workspace-files
  resource chain is host-owned; a plugin-side rewrite/retry/fallback would mask a host
  defect, would not restore the mainline documentpreview tab, and per the skill's boundary
  ("must not modify DSH core to conceal plugin incompatibility" / misconfiguration fails
  loud) the correct owner is the host. There is also nothing for the plugin to retry: the
  read stalls with `meta.status: 'none'` on every attempt while an independent RPC works.
- **Order of action for the maintainer:**
  1. **First cheap step — full host restart** (stop all dsh processes, restart
     `dsh web`, hard-refresh the browser). Prior art shows a restart self-healed the
     roster/combo mismatch once on alpha.1 (`discussion-excerpt.txt`); it is free and
     either fixes it or produces a clean reproducing boot.
  2. If it persists: **reproduce cleanly and collect the evidence of §1–§3** — verify
     composition (the workspace-files row is present in `cordis.patch.yml`), the boot
     manifest revs, and whether the Typert `workspaceFileScope` lookup resolves
     (`gateway/lookup-not-found`) on the new alpha.2 semantics of card DSH-0.1.5-A2-01.
     Check the six junction-linked external plugins' client manifests against the new
     roster for stale alpha.1-era links (the known in-place-upgrade hazard from the
     0.1.5-alpha.1 corridor, A1-20).
  3. **Escape hatch — verified rollback**: `npm i -g @deepseek-ai/dsh@0.1.3-alpha.2` from
     an external terminal with all dsh processes stopped (per `discussion-excerpt.txt`,
     verified on this deployment; per the skill, pinned exact-version external install,
     never an in-session upgrade).
  4. **Upstream**: file/report the resource-provider-chain failure with the §5 forensics
     (appended as round 2 to discussion #5999, comment 18371079).
  5. Separately and independently, fix the two unrelated items: the `absolute`-scope tab
     claim loss is by-design alpha.2 behavior (absolute paths need a claiming tab or
     host guidance), and the `dsh-paste-input` fold-parse warnings belong to that plugin's
     own parse robustness.

## 5. Prevention / upstream — forensics checklist and fail-loud boot checks

A complete upstream report (as packaged here and appended to #5999 round 2) needs:

- exact versions and install shape: 0.1.5-alpha.1 → 0.1.5-alpha.2, npm-global in-place,
  Windows 11, profile vintage (0.1.2/0.1.3), six junction-linked external client plugins;
- the boot manifest excerpt with module `rev` values (`234716e8f7370214-…`), showing the
  workspace-files row with its `inject: ["@deepseek-ai/dsh-api-gateway",
  "@deepseek-ai/dsh-client-resources"]` and the textpreview→documentpreview swap;
- the valid probe (62/62 per-module 200) plus the explicit statement that the joined-URL
  404 is an invalid probe, so nobody re-derives "modules missing";
- the **contrast probe** — two readers of the same file, one succeeding via its own RPC,
  the other stuck at `meta.status: 'none'` — this is the single decisive attribution
  artifact;
- the exact failing address and scope
  (`dsh-resource://file/session/session-2844c12c-…/.dsh/tmp/sidebar-open-test-2.md`);
- console excerpt showing zero resource-system errors (the silence is itself evidence of a
  stall, not an exception);
- host-side pointers: the `cordis.patch.yml` workspace-files row and the Typert
  `lookups.register` `workspaceFileScope` resolution path
  (`sessions.get(sessionId)?.header.cwd` fallback `sandboxPolicy.workspaceRoot`), with the
  card DSH-0.1.5-A2-01 semantic change as the suspect edge.

What the host could check at boot to make this class fail loud instead of rendering an
empty tab:

1. **Registration proof, not HTTP 200**: after loading a client module, assert the
   expected tab types/resource providers actually registered (the skill's validation rule:
   "prove registration/mount rather than accepting a bare HTTP 200"); a module that loads
   without registering its claimed resource type should raise a visible boot error.
2. **Resource-provider readiness gate**: before serving the UI, verify the injected
   provider chain (`api-workspace-files` + `client-resources`) is wired — a required
   Cordis service remaining pending, or the first probe `workspaceFileScope` lookup
   failing (`gateway/lookup-not-found`), should surface a startup diagnostic.
3. **Tab-level failure loudness**: when a sidebar tab's resource metadata never arrives
   (`meta.status` stays `'none'` after a timeout), render an explicit error state naming
   the stalled service — "文件资源服务不可用。" with no error and no retry hint converts a
   diagnosable stall into a silent empty tab.
4. **In-place-upgrade invariant**: on version change, reconcile the persisted profile's
   roster/junctions against the new manifest and either self-heal or refuse-with-message,
   so the alpha.1/A1-20 family (roster/combo drift) cannot recur silently.
