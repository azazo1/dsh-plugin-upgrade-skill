# S21 · The Resource Service That "Unavailable" — Analysis Report

Task: S21-resource-service-unavailable-trap (read-only evidence analysis)
Evidence: fixture pack from a 2026-09-09 dsh 0.1.5-alpha.1 → 0.1.5-alpha.2 in-place npm-global upgrade on Windows (profile created under 0.1.2/0.1.3, six external client plugins junction-linked).

## 1. Attribution — which layer actually fails

**The failing layer is the host-side file-resource read behind the `api-workspace-files` Remote, not the sidebar UI, not the tab-type registry, and not the filesystem.**

What the two readers of the same file rule in and rule out (contrast-probe.txt):

| Reader | Transport | Result | What it rules in / out |
|---|---|---|---|
| file-trace plugin | its own HTTP face (`/dsh-file-trace/*` routes to its own host RPC) | READS FINE (原文 and 阅读 both render) | Rules **in**: the file exists, is readable by the host process, and session/permission policy is not blocking `.dsh/tmp` under the workspace root. Rules **out**: filesystem damage, sandbox denial, and any client-side rendering defect. |
| documentpreview sidebar tab | `api-workspace-files` Remote (RPC) | FAILS — `meta.status` stays `'none'`, tab shows 「文件资源服务不可用。」 | Rules **in**: the specific Remote call chain used by the sidebar never delivers a result. Rules **out**: a client rendering bug (the tab shell and title render correctly) and a tab-claim problem for the session-scoped address (the document tab *opens*). |

**What `meta.status === 'none'` says about where the read stalls:** it is the initial/absent state, not an error or `'failed'` terminal state. The metadata request was sent but never resolved — neither success nor failure came back. That means the read is stalled or silently dropped host-side (an unanswered RPC: the workspace-files host service is listed in the roster/bundle patch but is not actually answering the Remote call), not rejected by policy and not answered-with-error. Combined with the F12 console showing **zero red errors** from the sidebar or resource system, this is a silent non-response, not a thrown, logged failure.

So the alpha.2 symptom is narrower than the alpha.1 round (#5999): static artifact serving is now healthy (62/62 modules serve) and the tab type is claimed for session-scoped addresses, but the **resource-provider chain still does not take over** — the same end-state the discussion recorded after its one-time roster self-heal.

## 2. Probe discipline — which combo probe is valid

- **Valid measurement of static artifact serving:** the **per-module sweep** (Probe 3: all 62 manifest entries fetched one by one, 62/62 HTTP 200, zero 404s). Each request matches the real route shape (`/plugins/??<one-module>/client.js&rev=…`) and returns real bytes (cf. Probe 1: 200, 73,616 bytes).
- **Invalid measurement:** the **all-62-joined single URL** (Probe 2: 404, zero-length body). It must never be cited as "modules missing" because:
  - The real loader **never issues that request**. It fetches modules according to the `__DSH_BOOT__` roster — individual per-entry URLs (as the manifest excerpt shows, one `url` per entry, each already carrying its own rev suffix).
  - The joined URL is a hand-fabricated ~4–5 KB request whose shape/size simply doesn't match a route the combo handler serves; a 404 with a zero-length body is the route declining the malformed/unmatched request, not evidence about artifact availability.
  - It directly contradicts the valid per-module sweep on the same rev; when a synthetic probe and a per-artifact sweep disagree, the synthetic probe is the one measuring nothing real.
- **How the real loader fetches the roster:** the browser reads `window.__DSH_BOOT__` (same-origin, fetched after restart), which lists each client package with its id, per-entry combo `url` (module + rev), and `inject` list; the loader then requests those entries as the manifest specifies — per entry, not as one giant join. Roster/combo consistency (alpha.1's failure mode) is therefore about *roster rows vs. what the combo route will serve at that rev*, which the per-module sweep is the correct instrument for.

## 3. Distractor separation

**Are the `dsh-paste-input` fold warnings related? No.** They come from a different plugin's client code (bubble collapsing of historical paste-attachment messages using the `==== DSH_PASTE_INPUT_V1 ====` marker protocol) and fire per historical message, independent of any sidebar/resource activity. They share only timing and console real estate with the failure. Treating them as a lead would be a classic distractor trap.

**What actually changed in the roster between the two versions, and does it explain the symptom?** The alpha.2 tree **replaced `ui-sidebar-textpreview` with `ui-sidebar-documentpreview`** (the manifest census shows `ui-sidebar-textpreview` ABSENT, 0 mentions; `cordis.patch.yml` now carries the documentpreview row).

- This rename **does explain symptom (2) from the timeline — partially**: the old `text` tab type (claiming `dsh-resource://file/**`) is gone; the new document tab's `canOpen` accepts only `parseFileAddress(address)?.scope === 'session'`. Hence clicking a link **outside** the session workspace now finds *no claiming tab type* → the `sidebarRight: no registered tab type claims "dsh-resource://file/absolute/…"` dialog. That is a deliberate scope-narrowing regression in claim coverage, a distinct defect from the read failure.
- It **does not explain** the 「文件资源服务不可用。」 content failure: for a session-scoped address the new tab opens and claims correctly, and the read still never arrives. The content failure lives in the `api-workspace-files` Remote/host-service chain (per §1) and is exactly what survived the alpha.1 restart self-heal in #5999.

So there are **three separate issues** in play: (a) absolute/out-of-workspace links no longer claimed (roster/rename, scope narrowing), (b) session-scoped file metadata read silently never resolving (resource-service chain), and (c) benign, unrelated paste-input fold warnings.

## 4. Mitigation decision — ordering

**Should the plugin work around the unavailable service? No.** The failing service is a host-provided capability (`api-workspace-files`), not something the external client plugin owns. Rewriting the plugin to read files through a private side channel (as file-trace happens to do) would bypass the product's resource/permission model; retry loops can't fix a request that never resolves; and a silent fallback would mask a host regression. The plugin's only defensible behavior is exactly what it does: render the service-unavailable state honestly. The fix belongs host-side/upstream.

**Order of action for the maintainer:**

1. **First cheap step — clean full restart of the host** (`dsh web` restart, ideally after closing the session), then re-verify: roster rows, per-module probe still 62/62, and whether `meta.status` now advances. Rationale: in the alpha.1 round (#5999) a restart self-healed a roster/combo mismatch once; an in-place npm-global upgrade over a 0.1.2/0.1.3-era profile is exactly the situation where stale process/roster state lingers. Also cheap: confirm the workspace-files host row is actually loaded (terminal/log check for the service, not just the bundle patch row) and that the session's `header.cwd`/workspace root resolution (the typert `lookups.register` path) returns a sane value for the live session id.
2. **Escape hatch — rollback** to the last known-good published version (`npm i -g @deepseek-ai/dsh@0.1.3-alpha.2`), already verified working for this deployment in #5999. Use it if the restart does not restore the read, since an empty-content tab is a daily-use blocker.
3. **Upstream — file the report** (append to discussion #5999 as round 3 / open an issue) with full forensics (§5), so the resource-chain regression and the absolute-scope claim gap both get fixed at the source.

## 5. Prevention / upstream

**Forensics a complete upstream report needs:**

- Versions and provenance: from/to versions (0.1.5-alpha.1 → 0.1.5-alpha.2), install mode (npm global in-place), profile creation version (0.1.2/0.1.3), OS (Windows 11), junction-linked external plugins list (all six present).
- The full `__DSH_BOOT__` roster (or the excerpt plus entry count: 60 rows listed / 62 probed) with rev strings.
- Probe results: per-module sweep (62/62 × 200) and a note that the joined-URL probe is non-representative (explicitly flag it so no maintainer chases "missing modules").
- The contrast probe: file-trace RPC succeeds vs. documentpreview Remote stalls, with `meta.status === 'none'` observed on the failing tab.
- Console excerpt showing no red errors (silent failure), and explicitly noting the paste-input warnings are unrelated.
- A concrete repro address pair: the absolute/outside-workspace link (claim dialog text) and the session-scoped link (`dsh-resource://file/session/<id>/.dsh/tmp/…`) with the session id, plus the file's existence.
- Host-side evidence about the workspace-files service: bundle-patch row present, and what its workspace-root resolution (typert `lookups.register`, `sessions.get(sessionId)?.header.cwd` → `sandboxPolicy.workspaceRoot` fallback) actually returned for that session id — the most likely silent-dead end.
- Reference to #5999 round 2 (comment 18371079) to tie the failure family together.

**What the host could check at boot so this class fails loud:**

- **Service liveness, not just roster presence:** after assembling the roster, the host should health-check that each roster-advertised host service is actually instantiated and answering — e.g., a boot-time (or first-bind-time) self-test RPC through the same Remote path the client uses (a trivial resource metadata read of a known file). A roster row without a responding service is precisely the silent gap here.
- **Roster/combo consistency assertion:** verify every roster entry's combo URL at the current rev returns 200 before printing the web URL (generalizes the alpha.1 self-heal into a loud check).
- **RPC deadline + surfaced error:** Remotes used for file metadata should have a timeout and an error event/dialog, so a stalled read terminates in a visible "read failed/timed out" state instead of `meta.status: 'none'` forever and a bare 「文件资源服务不可用。」 with no retry hint.
- **Claim-coverage check:** on boot, log/announce which `dsh-resource://` schemes have no claiming tab type, so the absolute-scope narrowing (symptom 2's dialog) is a documented, visible behavior change rather than a surprise dialog.
