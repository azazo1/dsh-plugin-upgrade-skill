# S21 Diagnostic Report — The Resource Service That "Unavailable"

Deployment: dsh 0.1.5-alpha.1 → 0.1.5-alpha.2 npm-global in-place upgrade, Windows 11, profile created under 0.1.2/0.1.3 with six external client plugins junction-linked. Evidence pack: fixture README.md, symptom-log.txt, boot-manifest-excerpt.txt, combo-probe.txt, contrast-probe.txt, console-excerpt.txt, discussion-excerpt.txt.

## 1. Attribution — which layer actually fails

The failing layer is **the client-side resource-provider chain that the documentpreview tab depends on — not the host file read, not the file, and not static artifact serving.**

What the two readers of the same file rule in and rule out (contrast-probe.txt):

- **file-trace plugin** reads `E:\deepseek-harness\test-lhh010\.dsh\tmp\sidebar-open-test-2.md` fine over its **own host RPC face** (`/dsh-file-trace/*` routes) — both 原文 and 阅读 modes show content. This **rules out**: file missing/unreadable, permissions, workspace-scope rejection on the host, and any host-side storage failure.
- **documentpreview sidebar tab** reads through the **api-workspace-files Remote** (the boot manifest row shows `@deepseek-ai/dsh-api-workspace-files` with `inject: ["@deepseek-ai/dsh-api-gateway","@deepseek-ai/dsh-client-resources"]`). This read **never arrives**. Because the two readers differ only in transport, the failure is isolated to the workspace-files resource chain between the tab and the host.

What the failing tab's metadata status says about where the read stalls (contrast-probe.txt): `meta.status stays 'none'` — the metadata never arrives at all. The tab renders its title (so the tab-type registration and the resource address parsing both succeeded) but shows the literal fallback string 「文件资源服务不可用。」. A status of `'none'` means the read stalled **before any response was produced**: the client-side Remote/service handle for workspace-files is effectively unavailable to the tab (e.g. the plugin never finished activating because an injected dependency never appeared, or its client half "loaded without registering" — the same family as discussion #5999 round 1). It is not a read that returned an error; it is a read that never happened. That also explains the console (console-excerpt.txt): no red errors from documentpreview or the sidebar, because nothing threw — the dependency simply was not there.

Supporting host-side facts from contrast-probe.txt: the workspace-files host row IS in the web-app bundle patch (`cordis.patch.yml: "- id: workspace-files / name: '@deepseek-ai/dsh-api-workspace-files'"`), the workspace root resolves via `sessions.get(sessionId)?.header.cwd` (typert `lookups.register`), and the host read() doc explicitly allows files outside the workspace — so the session-scoped address `dsh-resource://file/session/session-2844c12c-.../.dsh/tmp/sidebar-open-test-2.md` is not blocked by scope on the host.

## 2. Probe discipline — valid vs invalid combo probes

- **Valid measurement of static artifact serving: Probe 3, the per-module sweep** (combo-probe.txt): all 62 manifest entries fetched one by one → **62/62 HTTP 200, zero 404s**, plus Probe 1 (single module `/plugins/??@deepseek-ai/dsh-api-gateway/client.js&rev=234716e8f7370214-0` → 200, 73,616 bytes). Every module the boot roster lists is served correctly at the current rev.
- **Invalid: Probe 2, the all-in-one join** — all 62 modules comma-joined into one URL → 404 with zero-length body. The joined URL is **~4–5 KB long**. A 404 here is an artifact of the request itself (route/URL length limit), not evidence about any module. **It must never be cited as "modules missing"**: the per-module sweep of the exact same 62 entries contradicts it directly. Citing it would misdirect the whole investigation toward static serving, which the sweep already proves healthy.

How the real loader fetches the roster: it fetches each entry **as the boot manifest lists it** — per-module combo URLs like `/plugins/??<id>/client.js&rev=...-N` from `__DSH_BOOT__` (boot-manifest-excerpt.txt), i.e. one module per request (or the manifest's own grouping), never one giant concatenation of all 62 entries. The all-in-one URL is a probe artifact that no real client ever issues.

## 3. Distractor separation

- **The repeated `dsh-paste-input: fold skipped (parse failed)` warnings are unrelated.** console-excerpt.txt shows they come from `dsh-paste-input` client.js:1010 and fire "for every historical paste-attachment message" — they are the bubble-collapsing feature failing to parse old `==== DSH_PASTE_INPUT_V1 ====` attachment-marker blocks in history. They touch neither the sidebar tab nor the resource read chain, and there are **no other console outputs on the failing page** — in particular no documentpreview or sidebar errors.
- **What changed in the roster between the two versions (boot-manifest-excerpt.txt):** `ui-sidebar-textpreview` is **ABSENT** (0 mentions) from the alpha.2 boot HTML; the alpha.2 tree **replaced** `packages/client/ui-sidebar-textpreview` with `packages/client/ui-sidebar-documentpreview` (`packages/bundle/web-app/cordis.patch.yml` carries the new row; the old row is gone). The new package registers a document tab whose `canOpen` accepts only `parseFileAddress(address)?.scope === 'session'`.
- **Does the rename explain the symptom?** Only the **first** dialog, not the empty tab. The absolute-scope link failure ("no registered tab type claims `dsh-resource://file/absolute/...`") is directly explained by the new `canOpen` accepting session scope only. But the second symptom — a session-scoped link that opens a correctly-titled tab with 「文件资源服务不可用。」 — is accepted by `canOpen`, so the rename does **not** explain it; the stall is in the workspace-files resource chain (Section 1). Keeping these two bugs separate matters: one is a deliberate scope-narrowing regression in tab claiming, the other is a service-availability failure that survived the rename.

## 4. Mitigation decision and ordering

**The plugin should NOT work around the unavailable service** (no rewrite to another transport, no retry loop, no silent fallback render). The contrast probe proves the host can read the file; papering over the broken workspace-files chain in plugin code would mask a host/package defect and diverge further on the next upgrade.

Order of action for the maintainer:

1. **First cheap step — recycle and re-verify.** Hard-refresh the page and restart the host, then re-check the boot roster and re-run the per-module sweep. discussion-excerpt.txt shows a host restart self-healed the roster/combo mismatch once in the alpha.1 round ("A host restart self-healed the roster/combo mismatch once"), so a clean boot with the alpha.2 tree is the lowest-cost fix candidate. While there, capture the network panel of the failing tab to see whether the workspace-files Remote call is ever issued.
2. **Escape hatch — rollback.** `npm i -g @deepseek-ai/dsh@0.1.3-alpha.2`, verified working in discussion #5999 ("Rollback to the previous published version ... was verified as the escape hatch"). This restores the deployment while the defect is fixed upstream.
3. **Upstream — file/append the report** to discussion #5999 (round 2 forensics were appended as comment 18371079), with the package contents of Section 5. Do not ship a plugin-local shim in the meantime.

## 5. Prevention / upstream

**Forensics a complete upstream report needs** (all captured here, per file):

- Exact version transition and deployment shape: alpha.1 → alpha.2, npm global, Windows, profile vintage 0.1.2/0.1.3, six junction-linked external plugins (symptom-log.txt header).
- Timeline distinguishing the two symptoms (absolute-scope claim dialog vs session-scoped 「文件资源服务不可用。」) with the exact unregistered-tab-type message text (symptom-log.txt).
- Boot manifest excerpt with the verbatim workspace-files row (including its `inject` list) and the textpreview→documentpreview census (boot-manifest-excerpt.txt).
- Both probes with their results and the ~4–5 KB joined-URL caveat, so maintainers don't repeat the invalid probe (combo-probe.txt).
- The two-reader contrast probe with `meta.status stays 'none'` — the single most diagnostic fact (contrast-probe.txt).
- Console excerpt proving no errors from the failing surface and isolating the paste-input distractor (console-excerpt.txt).
- Prior art: discussion #5999 round 1 and the round-2 forensics comment 18371079 (discussion-excerpt.txt).
- For the next iteration: the browser network panel for the failing tab (was the Remote call issued? to which rev?), and the host-side activation log for `@deepseek-ai/dsh-api-workspace-files` and its injected dependencies.

**What the host could check at boot to fail loud:**

- Serve-and-register check: after building the `__DSH_BOOT__` roster, verify every listed module actually answers HTTP 200 at its recorded rev (the #5999 round-1 roster/combo mismatch — 404 at the same rev — would have been caught at boot instead of surfacing as "loaded without registering").
- Dependency-closure check: for each loaded client plugin, verify every entry in its `inject` list (e.g. `@deepseek-ai/dsh-api-gateway`, `@deepseek-ai/dsh-client-resources` for workspace-files) activated on the same boot; log a loud terminal error naming the missing dependency when a plugin finishes loading with an unresolvable injection instead of letting it sit in waiting.
- Loud empty-tab rendering: a tab whose resource `meta.status` remains `'none'` after a bounded wait should surface a diagnostic (which service, which address, which plugin) instead of the generic 「文件资源服务不可用。」 with no error anywhere in the console — today the failure is invisible in F12.
- Upgrade-time rename notice: when a client package a running profile references (ui-sidebar-textpreview) is replaced by a renamed one (ui-sidebar-documentpreview) with a narrower `canOpen`, print the substitution and the scope-narrowing at upgrade/restart time.
