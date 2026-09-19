# S21 Diagnostic Report — The Resource Service That "Unavailable"

Deployment: npm-global in-place upgrade dsh 0.1.5-alpha.1 → 0.1.5-alpha.2 on Windows 11; profile created under 0.1.2/0.1.3 with six external client plugins junction-linked. Evidence pack: fixture/ (read-only). All quotes verbatim.

## 1. Attribution — which layer fails, and what the two readers rule in/out

**The failing layer is the client-side resource-provider chain (the sidebar tab's read path via the api-workspace-files Remote), not the file system, not the host file service, and not the tab registry.**

Evidence:

- The **contrast probe** (contrast-probe.txt) reads the *same file at the same moment* through two transports:
  - file-trace plugin, own host RPC (`/dsh-file-trace/*` routes): "READS FINE — 原文 and 阅读 modes both show the content".
  - documentpreview sidebar tab, api-workspace-files Remote: "FAILS — meta.status stays 'none', the tab shows 文件资源服务不可用。"
- What this **rules in**: the host can read session files, the workspace root resolution is fine, and the file exists at the session-scoped address `dsh-resource://file/session/session-2844c12c-.../.dsh/tmp/sidebar-open-test-2.md`. What it **rules out**: disk permissions, file-not-found, workspace-scope rejection (contrast-probe.txt explicitly notes "Files OUTSIDE the session workspace are allowed … so .dsh/tmp being under the workspace root is not the blocker"), and any general web/combo-serving failure.
- The **metadata status** is the decisive clue: `meta.status stays 'none'`. A read that reached the host and failed would yield an error status and, per the symptom log, "No error message, no retry hint" — instead the UI falls back to the static string 「文件资源服务不可用。」. `status === 'none'` means the metadata/read **response never arrived at the client at all**: the request either was never sent, or the client-side service that should answer it (`@deepseek-ai/dsh-api-workspace-files` client half, injected with `@deepseek-ai/dsh-client-resources` per the boot manifest row) is not wired, so the tab renders its "service unavailable" empty state. The read **stalls before leaving the client** (or its reply is dropped client-side), not at the host.
- Corroboration from the earlier click (symptom-log step 2): an absolute-scope link still throws `sidebarRight: no registered tab type claims "dsh-resource://file/absolute/…"` — the tab *type registry* now only covers session scope (see §3), which is a separate, narrower registry gap; the session-scoped tab then opens but its content read never completes.

## 2. Probe discipline — valid vs invalid combo probes

- **Valid**: Probe 1 and Probe 3 (combo-probe.txt) — fetching each manifest entry's URL *individually* (`GET /plugins/??@deepseek-ai/dsh-api-gateway/client.js&rev=…` → 200, 73 616 bytes; sweep → "62/62 HTTP 200, zero 404s"). This faithfully measures what the loader actually does: fetch modules one at a time (or in the manifest's own grouping). Static artifact serving is healthy.
- **Invalid**: Probe 2 — "all 62 entries joined into one URL → 404, zero-length body. The joined URL is ~4–5 KB long." This is a self-inflicted artifact: an ~4–5 KB URL exceeds realistic route/URL handling (and the combo route's contract was never "any arbitrary comma join of 62 modules in one request"). It measures URL length/robustness of a hand-built request, not module availability.
- **Why the failing probe must never be cited as "modules missing"**: the boot manifest itself lists the modules (`boot-manifest-excerpt.txt`: total entries 60 in the excerpt, 62 in the sweep), and every listed module serves 200 at the current rev. Citing Probe 2 would send the investigation toward "build/packaging lost modules" — a false conclusion that contradicts both the per-module sweep and the observed behavior (the tab *opens and renders a title*, so its code clearly loaded). The prior round in discussion #5999 was a genuine roster/combo rev mismatch (new roster rows 404 at the old rev); alpha.2 is explicitly "related-but-narrower": "modules serve individually (62/62 probes 200)".
- **How the real loader fetches the roster**: it fetches `__DSH_BOOT__` same-origin after restart (boot-manifest-excerpt.txt header: "the __DSH_BOOT__ roster, fetched same-origin after the restart") and loads each entry's own `url` (`/plugins/??<id>/client.js&rev=…`) — the manifest, not a giant hand-joined URL, is the source of truth.

## 3. Distractor separation

- **The `dsh-paste-input` warnings are unrelated.** console-excerpt.txt shows the only console output is repeated `▲ dsh-paste-input: fold skipped (parse failed)` — per-message warnings about collapsing historical paste-attachment bubbles (the `==== DSH_PASTE_INPUT_V1 ====` marker protocol). They are warnings, not errors; there are "no red errors from documentpreview or the sidebar". Paste-input's own note says its "full chain was verified successfully in practice". This is a simultaneous, independent cosmetic bug (bubble folding on old messages), not a cause of the resource-read failure. Keep the two bugs in separate workstreams.
- **What did change in the roster**: `ui-sidebar-textpreview` is **absent** in alpha.2 — "the 0.1.5-alpha.2 tree REPLACED packages/client/ui-sidebar-textpreview with packages/client/ui-sidebar-documentpreview (packages/bundle/web-app/cordis.patch.yml carries the ui-sidebar-documentpreview row; the old ui-sidebar-textpreview row is gone)".
- **Does that change explain the symptom?** Partly — it explains the two halves precisely:
  - The absolute-scope dialog: "the text tab type ('text', claiming `dsh-resource://file/**`) was registered by ui-sidebar-textpreview in 0.1.5-alpha.1. In 0.1.5-alpha.2 the replacement package ui-sidebar-documentpreview registers a document tab whose canOpen accepts `parseFileAddress(address)?.scope === 'session'` only." So absolute-scope links lost their claiming tab type — a real regression for out-of-workspace links.
  - But the rename **does not by itself explain the empty content**: the session-scoped tab opens and titles correctly, so the document tab loads and registers. The content failure is that the resource metadata read (`meta.status stays 'none'`) never completes — i.e., the api-workspace-files Remote / client-resources wiring behind the tab, likely an upgrade-wiring/resolution issue on this long-lived profile (the same "resource-provider chain did not take over" noted in discussion #5999 round 1, which a restart did not heal then either).

## 4. Mitigation decision and action order

**Do NOT work around it in the plugin.** No rewrite, retry loop, or fallback reader in dsh-file-trace (or any client plugin) is appropriate: the plugin's own RPC already works; papering over a broken host-provided resource chain would mask the host defect, duplicate the read path, and survive silently into later versions. This is a host/upstream bug.

Order of action for the maintainer:

1. **First cheap step — clean restart / reload of the web host process** (not just the browser tab). Discussion #5999 shows one restart self-healed the alpha.1 roster/combo mismatch; verify after restart whether `meta.status` moves off 'none' and whether the workspace-files client half initializes (F12 network: does the metadata request fire at all?). Zero risk, takes a minute, and distinguishes stale-process wiring from a deterministic defect. Also re-verify on a *fresh* profile if possible to separate the legacy 0.1.2/0.1.3-profile factor from the upgrade itself.
2. **Escape hatch — rollback**, already verified in the prior round: `npm i -g @deepseek-ai/dsh@0.1.3-alpha.2` (discussion-excerpt.txt: "Rollback to the previous published version … was verified as the escape hatch"). Use it if the workspace is needed for productive work before a fix lands; note it also restores the textpreview tab type that claimed absolute-scope links.
3. **Goes upstream** — file/append the issue with the forensics in §5. The two sub-defects to report: (a) session-scoped resource metadata read never resolves (`meta.status === 'none'` → 「文件资源服务不可用。」 silent empty tab), (b) documentpreview's `canOpen` accepting session scope only leaves `dsh-resource://file/absolute/**` links with no claiming tab type.

## 5. Prevention / upstream

**Forensics a complete upstream report needs** (most of it already collected in this pack):

- Exact versions and upgrade mode: 0.1.5-alpha.1 → 0.1.5-alpha.2, npm-global in-place, Windows 11, profile lineage (created under 0.1.2/0.1.3, six junction-linked external client plugins) — plus a fresh-profile control result.
- The session-scoped resource address and the failing tab's `meta.status === 'none'` observation (contrast-probe.txt), contrasted with the working same-file read via file-trace's own RPC.
- F12 network capture: whether the workspace-files/resource metadata request is ever issued, its status/body if issued, and any client-side exception swallowed (console shows none — the tab fails *silently*, which is itself evidence).
- The boot manifest rows for `@deepseek-ai/dsh-api-workspace-files` (with its `inject` of `@deepseek-ai/dsh-client-resources`) and `@deepseek-ai/dsh-client-ui-sidebar-right`, and the census showing `ui-sidebar-textpreview` absent / `ui-sidebar-documentpreview` present via `packages/bundle/web-app/cordis.patch.yml`.
- The probe discipline section: 62/62 per-module 200s, and an explicit statement that the 62-module joined-URL 404 is an invalid probe (URL-length artifact) not evidence of missing modules.
- Prior-art linkage: discussion #5999 round 1 (comment 18371079 forensics), including that a restart self-healed the roster/combo mismatch once but the content read still failed.

**What the host could check at boot (fail loud instead of an empty tab):**

- **Registration/claim invariant**: at client start, verify that for every resolvable resource scheme/scope (here: `dsh-resource://file/session/**` *and* `dsh-resource://file/absolute/**`) at least one registered sidebar tab type's `canOpen` claims it; if none does, log a loud host-side/console error naming the unclaimed scheme — instead of the current `sidebarRight: no registered tab type claims …` surfacing only as a user dialog, or nothing at all for the content path.
- **Service-wiring invariant**: when a tab renders, assert that its declared resource provider's metadata read is wired (the injected `@deepseek-ai/dsh-client-resources` / api-workspace-files Remote resolves and answers a liveness/metadata probe). If the read stalls or `meta.status === 'none'` past a timeout, render an explicit diagnostic ("resource service X not connected; rev …") with a retry affordance — never the bare 「文件资源服务不可用。」 with "No error message, no retry hint".
- **Roster↔artifact consistency check at boot** (generalizes #5999 round 1): after building the `__DSH_BOOT__` roster, self-probe each listed entry's URL at the published rev and refuse/warn loudly on any non-200, so roster/combo drift is detected at startup rather than as per-plugin "loaded without registering" symptoms.
- Silent-empty-tab anti-pattern: any UI fallback string like 「文件资源服务不可用。」 should be paired with a logged, actionable error identifying which service/URL failed — the absence of any red console output is what made this failure expensive to attribute.
