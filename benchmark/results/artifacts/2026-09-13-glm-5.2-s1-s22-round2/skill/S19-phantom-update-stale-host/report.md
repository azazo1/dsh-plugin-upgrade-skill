# S19 · The Phantom Update, the Stale Host Half, and the Corrupted Payload — Read-Only Analysis

Task: `S19-phantom-update-stale-host` · Mode A (inspect, read-only) under the `plugin-upgrade` skill.
Evidence pack: `fixture/` (release-log.md, package.json, git-tags.txt, client-bundle-excerpt.js, asset-route-probe.txt, lib-index-excerpt.js, session-log-excerpt.txt). Fixture untouched; no migration, install, or write performed outside the report directory.

---

## 1. Phantom self-update root cause ("新版本 v0.3.7 可用" on v0.3.7 itself)

**Where the compared constant comes from.** The shipped client bundle's self-update check compares the newest mirror tag against `PLUGIN_VERSION`, and `PLUGIN_VERSION` is a **build-time constant inlined by tsdown from `package.json` when the bundle was built** — not a value read dynamically at runtime (`client-bundle-excerpt.js`: `export const PLUGIN_VERSION = "0.3.6"`, with the comment "tsdown inlined this constant from package.json WHEN THE BUNDLE WAS BUILT"). So the badge logic compares `latest tag (v0.3.7) > baked constant (0.3.6)` → true → badge.

**The operation-order mistake.** `release-log.md` for v0.3.7:

1. 16:22 `pnpm run build` — client bundle emitted
2. 16:23 bump `package.json` 0.3.6 → 0.3.7   ← **bump AFTER the build**
3. 16:24 commit (including the already-built `lib/client.js`) and tag `v0.3.7`

The bundle committed and tagged as v0.3.7 still carries the inlined `0.3.6`. At runtime the plugin fetches `git ls-remote --tags` (highest `vX.Y.Z`), sees `v0.3.7`, compares against its baked `0.3.6`, and announces an update to itself. The v0.3.8 release corrected the order (bump first, then build), per the release log.

**Why mirror/tag integrity is irrelevant.** The check never compares file content or tag-to-bundle consistency; it compares a *tag string* against a *baked string*. `git-tags.txt` shows all three mirrors (origin/public/omdsh) listing both tags at identical SHAs — the distribution pipeline is perfectly consistent; it consistently distributes a bundle whose baked constant is one version behind its tag. No amount of per-mirror SHA verification can catch this, because the tag SHA genuinely points at the commit containing the stale bundle. (It is a build/repo hygiene defect, not a distribution defect.)

**Corrected release order:**

1. bump `package.json` version **first**;
2. then `pnpm run build` (so tsdown inlines the new version);
3. then commit, tag, push.

Equivalent alternative: build from a clean checkout of the tag, or derive the version at runtime — but bump-before-build is the minimal fix.

**The check that would have caught it before pushing:** after the build and before committing/tagging, grep the emitted bundle for the baked constant and assert it equals the version being released, e.g.

```sh
grep -o 'PLUGIN_VERSION = "[0-9]*\.[0-9]*\.[0-9]*"' lib/client.js
# must print the version in package.json about to be tagged
```

(or an automated `node -e` check comparing `package.json`'s `version` with the constant parsed out of `lib/client.js`, wired into the release script / CI). This is cheap, deterministic, and catches bump-after-build every time.

---

## 2. Client vs host plane update asymmetry (SVG toggle visible, SVG asset 404)

**Where each half loads.** The client half is served to the browser as an artifact (`lib/client.js`); the browser re-fetches/reloads it on page refresh or client-bundle HMR, so the new v0.3.8 client code — including the new SVG render toggle — reached the browser without restarting anything. The host half (`lib/index.js`, which registers the asset route and its extension/content-type whitelist) is **Node module code loaded into the DSH host process at plugin activation/boot time**; the running process keeps the module it already loaded, regardless of what the link-installed repo on disk now contains.

**How the probes pin staleness to the running host process, not the release:**

- PNG probe → **200 `image/png`**: the route itself is registered and alive in the running host; this is not a missing route or a dead plugin.
- SVG probe → **404 "unsupported image type"**: the *whitelist* in the **loaded** module rejects `svg` — the 404 body names the extension gate, not a filesystem miss.
- Disk `lib/index.js` (v0.3.8, `lib-index-excerpt.js`) **does** contain `svg: 'image/svg+xml'`: the *released* code is correct.

Only one explanation fits all three observations: the route handler executing in the host process is an older in-memory copy (pre-SVG whitelist), while both the disk artifact and the browser client are current. The release is fine; the *running host* is stale — the host had not been restarted since before the whitelist change.

**What makes a host-plane change effective:** a host restart (or a full plugin deactivate/reactivate that re-imports the module from disk). Editing files, refreshing the browser, re-pushing tags, or re-linking does nothing for code already imported into the Node process.

**Why "plugins hot-update" doesn't hold here:** the usual rule of thumb applies to the *client plane* (browser artifacts re-fetch on refresh) and to pure configuration. Host-plane code is bound at import time into the long-lived host process; there is no reload path that reaches an already-registered route's closure. This is exactly the class of change where the rule fails — a behavior change implemented inside host module code that was already loaded. (Cf. the skill's v0.1.5-alpha.1 card A1-20: an in-place npm-global upgrade can serve a stale host/client combo until a host restart; host restart is the reconciliation point for both directions of mismatch.)

---

## 3. Broken-image attribution (corrupted session payload, not the traced file)

**Where the corruption happened.** `session-log-excerpt.txt` shows:

- the session log's stored read-result text has line 232 spliced — source line 232's head (`...stroke="#dde6ea" stro`) fused with source line 247's tail (`0 0,1 821,730"...`) at the shared prefix `stro`; source lines 233–247 are absent from the payload;
- the source file on disk is well-formed XML (verified), and a **re-read of the same region afterwards came back clean** (non-deterministic);
- the excerpt's attribution: the corrupted text is the *model-visible result block persisted into the session log* — i.e. the corruption occurred in **result-text assembly upstream of the plugin**, in the read-tool/session-persistence layer, while the tool's TYPE result delivered to the caller was clean.

Three facts triangulate the layer: (a) disk is clean, (b) the persisted log text is corrupt, (c) a later read of the same bytes is clean. The one mutable, non-deterministic stage between disk bytes and rendered output is the upstream result-text assembly/persistence path — not the file, not the plugin's renderer.

**Why the plugin must treat the session payload as untrusted rendering input.** The payload crossed a durable boundary (session log) whose contents the plugin neither produced nor controls; the observed splice produced text that is *not well-formed XML* (verdict: "Specification mandates value for attribute stro0"). Any render path that feeds stored text directly into an image URL / data URI / DOM will break or, worse, execute injected content. The plugin's renderer must validate before rendering and fail into an explicit error state — it cannot assume upstream text is faithful.

**Why editing/"repairing" the traced file would have been wrong:** the traced file was never broken — repairing it would (a) corrupt a good source file, (b) destroy the evidence needed to diagnose the real bug, and (c) paper over an upstream, non-deterministic defect that would recur on other files. The correct move is to report the upstream session-payload corruption bug (with the decoded-log forensics as evidence) and make the plugin's render chain defensive.

---

## 4. Defensive render chain for the SVG preview

Ordered render sources, cheapest-and-most-faithful first, each level justified:

1. **Disk-bytes asset route first.** Once the host is restarted so the v0.3.8 whitelist is loaded, `GET /dsh-file-trace/asset?path=...svg` serves the actual bytes from disk with `content-type: image/svg+xml`. Disk bytes are the ground truth (shown well-formed here), bypass the corrupted session-payload layer entirely, and avoid re-encoding text. Prefer it whenever the file still exists at its traced path.

2. **Session payload only after an XML well-formedness check.** When the file is gone from disk and the only remaining copy is the session payload, parse the text first (`DOMParser` with `image/svg+xml`, then check for a `parsererror` document element). The observed splice yields exactly a `parsererror`; a splice that happened to remain well-formed could still be wrong content, so this is a necessary-not-sufficient gate — but it deterministically rejects this class of corruption before it reaches a renderer. Only well-formed documents proceed to render.

3. **Sandboxed iframe as the last render fallback.** Render the (validated) SVG inside a sandboxed `<iframe sandbox>` (no `allow-scripts`): scripts are blocked even if malicious markup slipped through, while declarative features — SMIL/CSS animations — still run, preserving preview fidelity. This contains the residual risk of rendering untrusted-origin markup; it is the fallback, not the primary path, because it is heavier and still renders possibly-corrupt content.

4. **Explicit error state instead of a silent broken image.** When every level fails (route 404 *and* payload fails the well-formedness gate), show a visible error state ("SVG preview unavailable: stored copy failed XML validation — source file may have been read again to recover") with the failure reason and a retry/re-read affordance. A silent broken image is what turned an upstream persistence bug into a mysterious plugin symptom in the first place; an explicit state makes the failure attributable and non-action-misleading.

---

## 5. Forensics method + prevention

**Decoding the session log.** The session log is a concatenated-Zstandard generation file. Method to recover the exact stored text:

1. locate the log generation file for the session (per the DSH session-format/status authorities);
2. split the file into its concatenated zstd frames (zstd streams are self-terminating; decode frame-by-frame — e.g. repeatedly feed a zstd stream decoder until each frame's end, or use a tool that handles skippable/multi-frame concatenation);
3. decompress each frame in order and reassemble the decoded event stream (session events, per the `SessionEventMap`/format-version authorities for that generation);
4. find the read-result event for the SVG path and extract its result text verbatim — that extracted text is the evidence: compare it line-by-line against a fresh disk read to characterize the splice (shared-prefix splice at `stro`, missing lines 233–247) and record the XML well-formedness verdict of each copy.

This turns "the preview looked broken" into reproducible evidence: exact stored bytes, exact divergence point, and a clean re-read proving non-determinism upstream.

**Release-checklist items this incident adds:**

- **Version-bump-before-build**: bump `package.json` *before* running the build that inlines it (corrected order already applied for v0.3.8).
- **Grep the shipped bundle for the baked constant** pre-push: assert the constant in `lib/client.js` equals the version about to be tagged (automatable in CI/release script); this is the check that would have caught the phantom badge before pushing.
- **Per-mirror tag SHA verification** (already done here — keep it): `git ls-remote --tags` on every mirror, SHAs identical across origin/public/omdsh. Note explicitly that this verifies *distribution* integrity only and cannot detect a stale baked constant — the two checks are complementary, not redundant.
- **Host-plane changes require a host restart to take effect**: add "restart the host (or fully deactivate/reactivate the plugin) and re-probe" to the release verification for any change touching host-loaded module code; probe the asset route for each newly whitelisted type (SVG 200 `image/svg+xml`) before declaring the release live.
- **Report the upstream text-corruption bug** (session-payload splice in result-text assembly/persistence) with the decoded-log forensics attached, instead of papering over it in the plugin (no "repair the traced file", no silent retry that hides the defect). The plugin's defensive render chain (§4) is mitigation, not a fix.

---

## Summary of attributions

| Symptom | Root cause | Layer |
|---|---|---|
| Self-update badge on v0.3.7 | Build-time `PLUGIN_VERSION` inlined as 0.3.6 because `package.json` was bumped *after* the build; runtime compares tag vs baked constant | Release process (repo), not distribution |
| SVG 404 while toggle visible | Client plane refreshes via browser re-fetch; host plane registered its route/whitelist at boot — running host still has the pre-SVG whitelist while disk `lib/index.js` is correct | Stale running host process, not the release |
| Broken image | Session-log read-result text spliced upstream (result-text assembly/persistence); disk file well-formed; re-read clean | Upstream session-payload corruption, not the traced file, not the renderer |

**Completed**: full read-only analysis of all seven evidence files; report written.
**Skipped**: no baseline/migration/validation runs — Mode A read-only task; no code changes to inspect beyond the fixture excerpts.
**Pending/residual risk**: the upstream session-payload corruption bug is identified but not root-caused to a specific host code path (out of scope for this evidence pack; the fix belongs upstream, reported with forensics). The host-staleness fix (restart) and bundle-grep release check are recommendations for the maintainer, not applied here.
**Rollback**: nothing to roll back — read-only; report file is the only artifact written.
