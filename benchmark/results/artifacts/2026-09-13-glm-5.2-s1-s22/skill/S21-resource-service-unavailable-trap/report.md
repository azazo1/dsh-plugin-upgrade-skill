# S21 · The Resource Service That "Unavailable" — Analysis Report

Task: attribute a runtime file-read failure after an in-place npm-global dsh upgrade
(0.1.5-alpha.1 → 0.1.5-alpha.2, Windows, profile created under 0.1.2/0.1.3, six external
client plugins junction-linked), using only the read-only evidence pack.

Method: plugin-upgrade skill, Mode A (inspect / read-only diagnosis). No migrations,
installs, or fixture modifications were performed. Baseline not collected (no mechanical
suite applies — this is evidence triage, not a source migration).

---

## 1. Attribution — which layer actually fails

**The failing layer is the client→host `api-workspace-files` Remote read chain, not the
file on disk, not static artifact serving, and not the sidebar tab registration.**

Evidence chain:

- The tab *opens and renders a title*. In 0.1.5-alpha.2 the replacement package
  `ui-sidebar-documentpreview` registered a document tab whose `canOpen` accepted the
  session-scoped address — so client plugin loading, combo serving, and tab-type
  registration all worked on this boot.
- The **contrast probe** is decisive: two readers read the *same file at the same moment*.
  - `dsh-file-trace` reads it **fine** over its own HTTP RPC (`/dsh-file-trace/*` routes).
    This rules out: the file missing on disk, filesystem permissions, the host process
    being dead, and generic host-side RPC being broken.
  - The documentpreview sidebar tab reads it through the `@deepseek-ai/dsh-api-workspace-files`
    Remote and **fails**: `meta.status` stays `'none'` and the tab renders
    「文件资源服务不可用。」.
- The host side *declares* the seam: `cordis.patch.yml` carries the `workspace-files`
  row, and the boot manifest lists `@deepseek-ai/dsh-api-workspace-files/client.js` with
  `inject: ["@deepseek-ai/dsh-api-gateway", "@deepseek-ai/dsh-client-resources"]`. So the
  failure is not a missing composition row — it is in the runtime takeover: the host-side
  service behind that Remote never answers the request.

**What `meta.status === 'none'` says:** the read did not *fail* — it never *completed*.
An erroring read would produce an error status surfaced in the tab; `'none'` is the
initial/pending state. The request is silently stalled: the Remote call leaves the client
and no response (success or error) ever arrives. That points at the host-side
workspace-files provider not being activated / not claiming the Remote on this boot — the
"resource-provider chain did not take over" already observed in discussion #5999 round 1,
where a host restart fixed the roster/combo mismatch but this read *still* failed. It is a
host-side service-activation/wiring defect in the upgraded tree, surfaced only when the
client actually exercises the seam.

The outside-workspace dialog (`no registered tab type claims
"dsh-resource://file/absolute/…"`) is a **separate, expected** behavior change: the old
`ui-sidebar-textpreview` "text" tab claimed `dsh-resource://file/**`; the new
documentpreview tab accepts only `parseFileAddress(address)?.scope === 'session'`
(boot-manifest-excerpt note). Absolute-scope links are no longer claimed by design of the
alpha.2 rename — not the same bug as the empty tab.

## 2. Probe discipline — which combo probe is valid

- **Valid:** the per-module sweep (Probe 3) and the single-module combo probe (Probe 1):
  each boot-manifest entry fetched individually at its advertised `rev` — 62/62 HTTP 200.
  This is a real measurement of static artifact serving: every module the host advertises
  is actually served at the advertised revision.
- **Invalid:** Probe 2 (all 62 entries comma-joined into one ~4–5 KB combo URL → 404). The
  404 must **never** be cited as "modules missing" because:
  - the real loader never issues such a URL — it reads the `__DSH_BOOT__` boot manifest
    and fetches each roster entry's own URL (per-entry `url` field, as shown in the
    manifest excerpt); a fabricated URL shape is not a code path the product exercises;
  - a 4–5 KB GET can 404 for reasons unrelated to artifact presence (URL-length / routing
    limits on the `/plugins/??` combo route, unmatched joined-module list), and the
    zero-length body carries no diagnostic information;
  - it directly contradicts the controlled per-module measurement, and the controlled
    measurement wins.
- **How the loader actually gets the roster:** same-origin fetch of `__DSH_BOOT__`
  (boot manifest, keyed by `id`/`url`/`rev`, with `inject` declarations), then a
  fetch per entry. The correct "is serving healthy" probe is therefore per-entry at the
  advertised rev — exactly Probe 1/3, which pass. This also distinguishes this round from
  the #5999 alpha.1 round, where the *legitimate* per-module probe did return 404 for the
  newly added modules (a real roster/combo mismatch healed by restart). Here static
  serving is proven healthy; the failure is purely in the runtime Remote/service chain.

## 3. Distractor separation

- **`dsh-paste-input` fold warnings: unrelated.** They come from a different external
  plugin, in message-bubble rendering (collapsing historical `= DSH_PASTE_INPUT_V1 =`
  paste-attachment markers), on a code path that never touches the workspace-files Remote
  or the sidebar resource system. They repeat per historical paste message, correlating
  with chat history length, not with file reads. Timing, transport, and subsystem all
  differ. They deserve their own issue against that plugin, but must not be bundled into
  this attribution.
- **Roster change between versions:** `ui-sidebar-textpreview` → `ui-sidebar-documentpreview`
  (tree replaced the package; `cordis.patch.yml` now carries the documentpreview row; the
  old row is gone; manifest census shows textpreview ABSENT, documentpreview present).
  - This change **explains symptom 2's dialog** (absolute/outside-workspace links no
    longer claimed → "no registered tab type claims …") — an intentional scope
    restriction of the new tab's `canOpen` to `scope === 'session'`.
  - It does **not** explain the empty tab: the session-scoped link *was* claimed and the
    tab opened; the content read then stalled in the workspace-files Remote chain, which
    the rename does not touch. So one roster change, one explained symptom, one
    unexplained-by-it runtime failure — keep them separate.

## 4. Mitigation decision — ordering

**Should the plugin work around it? No.** The evidence shows a stalled host-side Remote
(no response, `meta.status: 'none'`), which is not a retryable-with-effect condition, and
the skill's boundaries apply: do not rewrite plugin code to conceal a host-side
incompatibility, do not retry non-idempotent-looking failures by default, and a fallback
in the plugin would hide the defect from upstream. The correct actor is the maintainer of
the deployment first, the dsh host second.

Order of action for the maintainer:

1. **Cheapest first: full stop + clean restart of the host, then hard-refresh the
   browser.** Every dsh process must be stopped (native-module file locks on Windows;
   a browser refresh is not a host stop), then `dsh web` restarted and the page
   hard-refreshed. Precedent: in #5999 round 1 a restart self-healed the roster/combo
   mismatch. If the read now works, the residual cause was stale in-place-upgrade state
   (roster/combo/rev inconsistency from the npm overlay) — still worth reporting upstream.
2. **If it persists: confirm the seam on the host.** Read-only checks: host terminal /
   session logs for the workspace-files service activation or a pending Cordis service;
   verify the resolved profile composition actually contains the `workspace-files` host
   row (it is declared in the bundle patch per the evidence) and that no junction-linked
   external plugin shadows it. This distinguishes "service never activated" from
   "Remote route not claimed".
3. **Escape hatch: pinned rollback to the last known-good version.** From an *external*
   terminal with all dsh processes stopped: `npm install -g @deepseek-ai/dsh@0.1.5-alpha.1`
   (or `0.1.3-alpha.2`, the verified rollback in #5999), then restart and hard-refresh.
   Never execute the global install from inside a session on that host.
4. **Upstream: file the round-2 forensics** (see §5) as a follow-up to
   deepseek-harness discussion #5999 (comment 18371079 already references this round).
   The bug to fix lives in the host (workspace-files service takeover after in-place
   upgrade), not in any of the six external plugins.
5. Separately, route the `dsh-paste-input` fold-skip warnings to that plugin's own
   tracker — parallel bug, unrelated fix.

## 5. Prevention / upstream

**Forensics a complete upstream report needs:**

- exact from/to versions and install channel (npm global in-place, 0.1.5-alpha.1 →
  0.1.5-alpha.2), profile creation vintage (0.1.2/0.1.3), OS, and the six junction-linked
  external client plugins listed;
- the full `__DSH_BOOT__` roster (not just the excerpt) plus the served combo `rev`s;
- per-module probe results at the advertised revs (the 62/62 sweep) and an explicit note
  that the joined-URL 404 is a non-representative artifact;
- the contrast probe: same file, two transports, one success one stall, with
  `meta.status: 'none'` observed over time (not just once);
- browser Network trace showing the workspace-files RPC request pending / unanswered;
- host-side activation evidence: terminal/session logs around boot, resolved composition
  (profile cordis patch rows) for the `workspace-files` host entry, and whether the
  Remote route was registered;
- the two dialogs verbatim (absolute-scope claim error vs 「文件资源服务不可用。」) and the
  F12 console excerpt showing the *absence* of errors;
- prior-art pointer to #5999 round 1 and what a restart did/did not heal.

**What the host could check at boot so this fails loud:**

- **Serving consistency gate:** after composing the client roster, self-probe every
  advertised entry URL at its advertised rev (the per-module sweep, run by the host
  itself); a mismatch fails boot loudly instead of serving a client that cannot load.
- **Remote/provider completeness gate:** before serving the client bundle, verify that
  every Remote a roster client module declares in `inject` (here
  `dsh-api-workspace-files` → `dsh-client-resources` chain) has an activated host-side
  provider; a client whose required Remote has no live provider should be refused at boot
  with a named error, not deferred to first use.
- **Stall-to-error conversion in the tab:** a metadata read that stays `status: 'none'`
  past a timeout should render an explicit error with a retry affordance (and a console
  diagnostic), never a bare 「服务不可用」 dead end — the current UI erases the distinction
  between "never answered" and "answered with failure", which is exactly the forensic
  signal the maintainer needed.

---

## Report per the skill's structure

- **pre-existing**: not collected (Mode A read-only evidence triage; no mechanical suite run).
- **Completed**: full attribution of the empty-tab failure to the stalled
  `api-workspace-files` Remote chain; validation of the per-module probe and rejection
  of the joined-URL 404 as a measurement; separation of the paste-input and
  textpreview→documentpreview distractors; ordered mitigation plan; upstream forensics
  and boot-gate recommendations.
- **Skipped**: no source migration, install, rollback, or restart executed (task is
  read-only analysis; the fixture is evidence only). The joined combo probe (Probe 2)
  treated as non-evidence per §2.
- **Pending/residual risk**: root cause inside the 0.1.5-alpha.2 host tree (why the
  workspace-files provider does not answer after in-place upgrade despite the composition
  row) is narrowed but not pinpointed — it requires host-side logs from a live
  reproduction, which the read-only evidence pack cannot provide.
- **Rollback**: no changes were made; nothing to roll back. The *deployment's* escape
  hatch (pinned rollback to 0.1.5-alpha.1 / 0.1.3-alpha.2) is documented in §4.
- **Recommendations**: ship the three boot-time gates of §5 upstream; append this round's
  forensics to discussion #5999; track paste-input fold warnings separately.
