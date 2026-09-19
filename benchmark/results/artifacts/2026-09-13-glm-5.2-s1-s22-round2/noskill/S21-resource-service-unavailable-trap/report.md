# S21 · The Resource Service That "Unavailable" — Analysis Report

Task: attribute a runtime file-read failure after an in-place dsh upgrade
(0.1.5-alpha.1 → 0.1.5-alpha.2, npm global, Windows, profile created under
0.1.2/0.1.3, six junction-linked external client plugins) from the read-only
evidence pack. All evidence citations below are to the fixture files.

## 1. Attribution: which layer actually fails

**The failing layer is the host-side file-resource service chain behind the
`api-workspace-files` Remote — not static artifact serving, not tab
registration, not the browser.**

Two independent facts pin this:

- **The tab itself works.** On alpha.2 a session-scoped link opens a right-Sidebar
  tab with the correct title ("sidebar-open-test-2.md"). Tab creation, tab-type
  claiming, and title rendering are client-side and succeed. Only the content
  area fails, with 「文件资源服务不可用。」 ("file resource service unavailable")
  — the tab's own message for a resource service that never delivered.
- **The two readers of the same file rule layers in and out**
  (contrast-probe.txt):

  | Reader | Transport | Result | Rules out / rules in |
  |---|---|---|---|
  | file-trace plugin panel | its own host RPC (`/dsh-file-trace/*` routes) | reads fine, 原文 and 阅读 both show content | Rules out: filesystem permissions, sandbox denial of `.dsh/tmp`, host process health, session workspace-root misconfiguration for this session |
  | documentpreview sidebar tab | `api-workspace-files` Remote | fails; `meta.status` stays `'none'` | Rules in: the workspace-files Remote → host service chain specifically |

  The same host process can read the file through one face but not the other, so
  the failure is specific to the workspace-files service path (the Remote, the
  service registration behind it, or its dependencies — per the manifest excerpt
  the package `inject`s `@deepseek-ai/dsh-api-gateway` and
  `@deepseek-ai/dsh-client-resources`, and the host resolves the workspace root
  via a typert `lookups.register` entry over
  `sessions.get(sessionId)?.header.cwd` with a `sandboxPolicy.workspaceRoot`
  fallback).

**What `meta.status === 'none'` says about where the read stalls:** `'none'` is
the never-answered state, not an error state. The metadata request either never
reached a live service or the service never responded — the read **stalls before
producing a result**, as opposed to being denied or erroring. That is consistent
with the resource-provider chain not taking over after the upgrade (the same
residual failure #5999 observed on alpha.1 after a restart self-healed the
roster/combo mismatch). It is *not* a read of the file that failed — the file is
provably readable on the same host one transport over.

## 2. Probe discipline: which combo probe is valid

- **Valid: the per-module sweep (combo-probe.txt, Probe 3) — 62/62 HTTP 200 —
  and Probe 1's single-module combo URL.** Each fetches exactly a URL form the
  boot manifest itself advertises, so a 200 is a genuine measurement that the
  static artifact serving works for every rostered module at the current rev.
- **Invalid: Probe 2, the all-62-modules joined URL (404).** This is a synthetic
  construction nobody's loader issues: the combo route does not promise that an
  arbitrary ~4–5 KB join of every entry is a servable resource (URL-length and
  route-format limits alone can produce the 404). Its failure measures the probe,
  not the server.

**Why the 404 must never be cited as "modules missing":** the per-module sweep on
the *same host at the same rev* proves every module is served (200, non-zero
bodies). The joined-URL 404 therefore cannot indicate absence of artifacts; it
only indicates the joined URL is not a valid request. Citing it as "modules
missing" would send the investigation chasing static serving that is demonstrably
healthy — exactly the trap this scenario is built around. (In the *prior* alpha.1
round, #5999, modules genuinely were missing at the rev — *individual* probes
404'd there. That differential is what per-module probing is for.)

**How the real loader fetches the roster:** it does not join anything. The host
injects `__DSH_BOOT__` with the boot manifest (60 entries in the excerpt), and
each entry carries its own `url` (`/plugins/??<id>/client.js&rev=…`) plus its
`inject` dependencies. The client loads those per-entry URLs — i.e., the loader's
access pattern is the per-entry one that probes 200/200, not the all-in-one join.

## 3. Distractor separation

**Are the `dsh-paste-input` warnings related? No.** They are "fold skipped
(parse failed)" repeats from bubble-collapsing of *historical paste-attachment
messages* (console-excerpt.txt) — a display nicety in an external plugin over
old message markers. They share no transport, service, or code path with the
sidebar's resource read. The console correspondingly shows **no** errors from
documentpreview, the sidebar, or the resource system — which itself corroborates
the "stalled, not thrown" attribution in §1: nothing errors because nothing
answers.

**What else changed in the roster:** alpha.2 replaced
`ui-sidebar-textpreview` with `ui-sidebar-documentpreview` (manifest census:
0 mentions of the old id; the web-app `cordis.patch.yml` carries the new row).
The old package registered the `text` tab type claiming
`dsh-resource://file/**`; the new document tab's `canOpen` accepts only
`parseFileAddress(address)?.scope === 'session'`.

**Does that explain the symptom? It explains exactly one of the two observed
behaviors — the *other* one it cannot explain:**

- It *does* explain timeline step 2: an outside-workspace link
  (`dsh-resource://file/absolute/…`) now has no claiming tab type → the
  "no registered tab type claims" dialog. That is an intended-ish scope
  narrowing of the new tab, not a service failure.
- It does *not* explain step 3: the in-workspace link *is* session-scoped, the
  new tab *does* claim and open it, and the content still never arrives. The
  rename changed who renders the tab, not the read path; the read failure is
  the workspace-files service chain from §1. Two separate bugs from one
  upgrade; keep them separate.

## 4. Mitigation decision

**Should the plugin work around it? No.** The failing service is a platform
(host) capability consumed through `api-workspace-files`; the external plugins
are bystanders. Retrying in the plugin would just re-stall on a dead chain;
rewriting the plugin to read files by another route (as file-trace happens to
do) duplicates platform capability and masks the regression; a silent fallback
hides the failure from the very forensics needed upstream. The correct plugin
behavior is roughly what it does: surface "service unavailable" and stop.

**Order of action for the maintainer:**

1. **First cheap step — restart and re-verify the chain.** #5999 documents that
   a host restart once self-healed a roster/combo mismatch on this same
   profile. Re-run the per-module probe after restart and re-click the link. If
   it still fails, capture §5's forensics *before* anything else (evidence on a
   broken state is perishable).
2. **Escape hatch — rollback.** `npm i -g @deepseek-ai/dsh@0.1.3-alpha.2` is
   the previously-verified escape hatch on this deployment. Use it to restore
   usability once evidence is captured; it does not fix the bug.
3. **Upstream — file/append the report.** This is round 2 of a known failure
   family (#5999, comment 18371079 already carries the forensics). The fix
   (service not taking over after in-place upgrade on old profiles) belongs in
   the host, not in any consumer.

## 5. Prevention / upstream

**Forensics a complete upstream report needs:**

- Versions and path: 0.1.2/0.1.3-created profile, npm-global in-place upgrade
  0.1.5-alpha.1 → 0.1.5-alpha.2, Windows, junction-linked external client
  plugins; the exact `npm i -g` and restart commands.
- The two-symptom split: absolute-scope "no registered tab type claims" dialog
  (explained by the textpreview→documentpreview scope narrowing) vs the
  session-scoped empty tab with 「文件资源服务不可用。」.
- The contrast probe verbatim: file-trace RPC reads the same file fine while
  the documentpreview Remote stalls with `meta.status === 'none'`.
- Boot manifest excerpt (the 60-entry roster, the `inject` rows for
  `dsh-api-workspace-files`, the documentpreview/textpreview census).
- Probe results with methodology: per-module 62/62 × 200 (valid) and the joined
  62-module 404 explicitly labeled an invalid synthetic probe, so nobody chases
  it.
- Console excerpt showing absence of sidebar/resource errors (stall, not
  throw) and the unrelated `dsh-paste-input` warnings marked as distractors.
- Host-side: whether the workspace-files service registered on boot, whether
  its `inject` deps (`dsh-api-gateway`, `dsh-client-resources`) activated,
  whether the typert `lookups.register` entry resolved
  `sessions.get(sessionId)?.header.cwd` vs the `sandboxPolicy.workspaceRoot`
  fallback, and any host log lines from those packages.

**What the host could check at boot to fail loud:**

- **Roster/combo self-consistency probe:** after building the boot manifest,
  have the host issue (locally) the very per-entry combo URLs it is about to
  advertise and refuse to print "ready" (or print a loud warning) on any
  non-200 — this turns the #5999 roster/combo mismatch class into a boot-time
  failure instead of six "loaded without registering" client mysteries.
- **Required-service presence for registered UI claims:** when the web-app
  bundle registers a tab that consumes a resource Remote, verify at boot that
  the backing host service is actually registered and activated (the inject
  graph resolved), not merely that its manifest row exists.
- **Client-side watchdog:** a resource request whose metadata stays
  `status: 'none'` for a deadline should escalate to an explicit error state
  with a retry affordance and a diagnostic (which Remote, which service) — an
  empty tab with a bare "service unavailable" and zero console output is the
  silent failure mode this whole scenario suffered from.

## Summary table

| Question | Answer |
|---|---|
| Failing layer | Host-side workspace-files resource service chain (Remote → service/deps), evidenced by the two-reader contrast; static serving and tab registration are healthy |
| `meta.status: 'none'` | Read stalls unanswered (service never takes over), not denied/errored |
| Valid probe | Per-module sweep (62/62 × 200); the all-in-one joined 404 is a synthetic non-loader request and must not be cited as "modules missing" |
| Loader's real fetch | Per-entry URLs from the `__DSH_BOOT__` manifest, each with its own rev |
| paste-input warnings | Unrelated distractor (historical-message bubble folding in an external plugin) |
| Roster change | textpreview → documentpreview; explains the absolute-scope dialog only, not the content stall |
| Mitigation order | (1) restart + re-probe (cheap, once self-healed this family), (2) rollback to 0.1.3-alpha.2 (escape hatch), (3) upstream report; no plugin-side workaround |
| Prevention | Boot-time roster self-probe, required-service presence check, client watchdog for stalled metadata with loud error + retry |
