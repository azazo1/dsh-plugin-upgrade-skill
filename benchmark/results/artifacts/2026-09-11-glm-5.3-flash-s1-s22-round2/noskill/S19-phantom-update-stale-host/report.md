# S19 Diagnostic Report — The Phantom Update, the Stale Host Half, and the Corrupted Payload

Evidence pack: `E:/deepseek-harness/dsh-plugin-upgrade-skill/benchmark/tasks/S19-phantom-update-stale-host/environment/fixture` (read-only; nothing modified).
Plugin: `@dsh-external/dsh-file-trace`, release session of 2026-09-05 (v0.3.7 markdown fix, v0.3.8 SVG render preview).

---

## 1. Phantom self-update root cause (v0.3.7 badge on v0.3.7)

**Where the compared version constant comes from — build time, not runtime.** The shipped bundle `client-bundle-excerpt.js` (verbatim from the served `lib/client.js` at tag v0.3.7) contains:

```js
/** The running plugin version (from package.json at build time). */
export const PLUGIN_VERSION = "0.3.6";
// tsdown inlined this constant from package.json WHEN THE BUNDLE WAS BUILT —
// it is not read dynamically at runtime.
```

The self-update check is `newerTag(latestTag)`: it shows a badge when `compareSemver(latestTag, PLUGIN_VERSION) > 0`. Since the bundle baked `"0.3.6"` while the tag it shipped under is `v0.3.7`, the check evaluates `newerTag("v0.3.7")` → `"v0.3.7"` → badge "新版本 v0.3.7 可用" on the just-released v0.3.7 itself. The released client is literally announcing its own tag as an update.

**The actual operation-order mistake.** `release-log.md` v0.3.7, steps 3–4:

- 16:22 `pnpm run build` — client bundle emitted ← **build ran here**
- 16:23 bump `package.json` version 0.3.6 → 0.3.7 ← **version bumped AFTER the build**

The bundle was emitted while `package.json` still said 0.3.6, so tsdown inlined the stale version. The commit then included the already-built stale `lib/client.js` and was tagged v0.3.7. The log confirms the fix: "the rebuild order was corrected for v0.3.8 (bump FIRST, then build)" (amend + rebuild + force-move the tag on all mirrors was required).

**Why mirror/tag integrity is irrelevant.** `git-tags.txt` shows all three mirrors (origin / public / omdsh) serve identical SHAs for both tags — `748b5e5...` for v0.3.7, `d887deb...` for v0.3.8. Every mirror serves the same (stale-constant) bundle correctly; the update check fetched exactly these tags and correctly picked v0.3.7 as highest. The failure is entirely in what was baked into the shipped artifact at build time, not in what any mirror serves. Verifying tag SHAs proves distribution consistency, not build correctness.

**Corrected release order and the catching check.** Correct order: (1) edit source, (2) bump `package.json` **first**, (3) `pnpm run build`, (4) README/install refs, (5) commit (bundling the freshly built `lib/client.js` that now contains the new version), (6) tag, (7) push mirrors + verify tag SHAs. The check that would have caught it before pushing: **grep the shipped bundle for the baked constant** — e.g. `grep -F 'PLUGIN_VERSION = "0.3.7"' lib/client.js` must succeed after the build (equivalently, assert the emitted bundle contains `version` equal to `package.json`'s `version`). This is a one-line pre-tag gate; see also §5.

---

## 2. Client vs host plane update asymmetry (SVG toggle live, route still 404)

**Observed, per `asset-route-probe.txt` (probed AFTER the browser was confirmed refreshed):**

- `GET /dsh-file-trace/asset?path=...daigo-final.png` → **200 OK, content-type: image/png**
- `GET /dsh-file-trace/asset?path=...daigo-bicycle.svg` → **404 "unsupported image type"**
- The shipped `lib/index.js` on disk (`lib-index-excerpt.js`, tag v0.3.8) **does** whitelist svg: `svg: 'image/svg+xml'` in `CONTENT_TYPES`.

**Where each half is loaded and when:**

- **Client half** (`lib/client.js`): loaded by the **browser**, fetched per page load / plugin refresh. A client-plugin update takes effect when the page re-fetches the bundle and re-renders — hence the new SVG render toggle button appeared and was clickable. Client-plane changes are effectively hot-updating because the browser reloads the bundle.
- **Host half** (`lib/index.js`): loaded by the **Node host process at boot**; route registration (including the asset route and its `CONTENT_TYPES` extension whitelist) happens once at plugin activation/startup. Updating the file on disk changes nothing in a process that already imported the old module.

**How the probes pin the staleness to the RUNNING host process.** Three facts combine:

1. PNG probe 200 → the route handler itself is alive and registered; the 404 is not a missing route but the **extension whitelist inside the running handler** rejecting `svg`.
2. Disk `lib/index.js` whitelists svg → the release artifact is correct.
3. The running process answers differently from the disk artifact → the running process is executing the **pre-v0.3.8 module image** registered at boot. `release-log.md` states it explicitly: "a host restart had NOT been performed in this session."

So the release is fine; the staleness is process-resident module state.

**What makes a host-plane change effective — and why "plugins hot-update" does not hold here.** A host restart (host process restart / plugin re-activation that re-imports the half) re-runs boot-time route registration against the new `lib/index.js`, after which the SVG probe returns 200 `image/svg+xml`. ESM imports are cached for the life of the process; no client-side reload can replace code executing inside the server. This is the one case where the usual "plugins hot-update" rule fails: the rule holds for the browser-resident client half (re-fetched per page load), but **host-half changes are boot-time-bound** and require a host restart to take effect. The release checklist must therefore include "restart the host after shipping host-half changes."

---

## 3. Broken-image attribution (corrupted session payload, not the traced file)

**Where the corruption happened.** `session-log-excerpt.txt` shows:

- **Session log payload** (line 232): `<circle r="98" fill="none" stroke="#dde6ea" stro0,1 821,730" fill="none" ...` — a splice: source line 232 up to `"...dde6ea" stro` joined with **line 247's tail** (`0 0,1 821,730` onward). Source lines 233–247 are absent from the stored text; the splice lands on the shared prefix `stro`.
- **Source file on disk**, same region: clean lines 232–247 (232 = `...stroke="#dde6ea" stroke-width="6.5"/>`).
- **XML verdicts**: source file **well-formed** (`System.Xml XmlDocument` load, no error); log payload **NOT well-formed** — `error on line 233 at column 54: Specification mandates value for attribute stro0`.
- Crucially: "The read tool's TYPE result **delivered to the caller** was clean; the corrupted text is the model-visible result block **persisted into the session log**, i.e. the corruption happened in the **result-text assembly, upstream of the plugin**. A re-read of the same region afterwards came back clean (non-deterministic)."

So the corruption occurred in the harness/session layer that assembles and persists the read-result text into the session log — not in the read tool's in-memory result, not in the traced file, and not in the plugin's rendering code. It is nondeterministic (a clean re-read follows), consistent with an assembly/splice bug rather than file damage.

**Why the plugin must treat the session payload as untrusted rendering input.** The plugin renders whatever text reaches it through the session payload; that text can differ from the disk bytes (this incident proves it). Validating it — parse with DOMParser and reject on `parsererror` (see §4) — is required precisely because the payload is an upstream-assembled, potentially corrupted copy of the file, not the file itself.

**Why editing or "repairing" the traced file would have been wrong.** The source on disk is well-formed (verified); the defect lives only in the stored log text. Any edit to the traced file would (a) modify a healthy asset, (b) mask the real upstream bug in result-text assembly so it would recur silently on other files, and (c) be ineffective as a general fix since the corruption is nondeterministic. The correct move is to attribute via forensics (§5) and report the upstream harness bug.

---

## 4. Defensive render chain for the SVG preview

Render-source order, each level justified:

1. **Disk-bytes asset route first (preferred source).** The file on disk is the authoritative, verbatim bytes; the asset route serves exactly those bytes (`CONTENT_TYPES` incl. `svg: 'image/svg+xml'`). This bypasses the session-payload corruption path entirely (§3). Prerequisite from this incident: the host must be restarted so the running route actually knows `svg`; keep the PNG/SVG probe as a health check.
2. **Session payload only after an XML well-formedness check (fallback source).** If the asset route is unavailable, parse the payload text with `DOMParser` (or equivalent) and fall through only when no `parsererror` element appears — the same check the XML verdict in the excerpt performs. Justification: the payload is untrusted input (§3); `parsererror` detection would have rejected the spliced line 232 ("Specification mandates value for attribute stro0") instead of feeding a broken image to the renderer.
3. **Sandboxed iframe as the last render fallback.** Render accepted SVG inside a sandboxed iframe (no `allow-scripts`) so embedded scripts cannot execute; SVG SMIL animations run without scripts, so legitimate animated traces still preview. Scripts blocked / SMIL allowed is exactly the capability split an SVG viewer needs.
4. **Explicit error state instead of a silent broken image.** When every source fails validation, render a visible error state ("SVG preview unavailable: payload failed XML validation" etc.). Justification: this incident's broken image was silent — the renderer consumed invalid text with no signal. An explicit error converts a visual anomaly into a diagnosable event and prevents mistaking upstream corruption for a broken file.

---

## 5. Forensics method + prevention

**Decoding the session log frame-by-frame.** The session log is a concatenated-Zstandard **generation file**: a sequence of independently compressed zstd frames appended over time. Method:

1. Split the generation file at frame boundaries (zstd magic / frame epilogue), or use a streaming decoder that supports concatenated frames, decompressing **frame by frame** rather than the whole file at once.
2. Decode each frame's session-event envelope and extract the read-result text blocks (the excerpt was recovered this way: "payload around line 232").
3. Compare the recovered stored text against the disk file line by line to localize the splice — this yields the exact evidence: line 232 = source line 232 prefix through `"stro` + source line 247's tail from `0 0,1 821,730`, lines 233–247 missing, and the XML parser verdict pinning the malformed attribute `stro0`.
4. Re-read the region to test determinism (clean re-read here) — this distinguishes a transient assembly bug from persistent file damage and attributes the defect to the result-text assembly layer, upstream of the plugin.

This is what turns "the image renders broken" from an anecdote into a reproducible, layer-attributed finding with the exact corrupted bytes preserved.

**Release-checklist items this incident adds:**

1. **Version-bump-before-build**: bump `package.json` **before** `pnpm run build`, so the bundler inlines the released version (v0.3.7's build-then-bump order baked `PLUGIN_VERSION = "0.3.6"` and caused the phantom self-update).
2. **Grep the shipped bundle for the baked constant**: after building and before tagging, assert `lib/client.js` contains `PLUGIN_VERSION = "<new version>"` (and no stale value) — a CI/pre-tag gate that would have blocked the v0.3.7 tag.
3. **Per-mirror tag SHA verification**: `git ls-remote --tags` on every mirror (origin/public/omdsh) and require identical SHAs, as recorded in `git-tags.txt`.
4. **Restart the host after host-half changes**: a shipped `lib/index.js` change (the SVG whitelist) is boot-time-bound; the release is not effective until the host process restart re-registers the routes. Verify with a probe of the new content type (SVG → 200 `image/svg+xml`).
5. **Report the upstream text-corruption bug instead of papering over it in the plugin**: when forensics attribute a defect to the harness's result-text assembly (§3), file the bug upstream with the decoded frame evidence; do not edit healthy source files or add plugin-side hacks that mask a nondeterministic upstream corruption.

---
*Report grounded entirely in the read-only evidence pack files listed in its README: `release-log.md`, `package.json`, `git-tags.txt`, `client-bundle-excerpt.js`, `asset-route-probe.txt`, `lib-index-excerpt.js`, `session-log-excerpt.txt`.*
