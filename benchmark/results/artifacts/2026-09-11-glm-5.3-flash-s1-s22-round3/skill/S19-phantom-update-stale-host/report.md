# S19 · The Phantom Update, the Stale Host Half, and the Corrupted Payload — Diagnostic Report

Evidence pack: `/app/fixture/` (read-only), release session of `@dsh-external/dsh-file-trace` v0.3.7/v0.3.8, 2026-09-05.

---

## 1. Phantom self-update root cause (v0.3.7 announces an update to itself)

**Where the compared version constant comes from — build time, not runtime.**
The shipped client bundle `client-bundle-excerpt.js` (the `lib/client.js` actually served after the release) contains, verbatim:

```js
/** The running plugin version (from package.json at build time). */
export const PLUGIN_VERSION = "0.3.6";
// tsdown inlined this constant from package.json WHEN THE BUNDLE WAS BUILT —
// it is not read dynamically at runtime.
```

The self-update check compares the newest mirror tag against this **baked-in** constant: `newerTag(latestTag)` returns the tag when `compareSemver(latestTag, PLUGIN_VERSION) > 0`.

**The actual operation-order mistake.** `release-log.md` records the v0.3.7 order:

1. 16:22 `pnpm run build` — "build ran here"
2. 16:23 bump `package.json` version 0.3.6 → 0.3.7 — "version bumped AFTER the build"
3. 16:24 commit (including the already-built `lib/client.js`) and tag `v0.3.7`

Because the build ran while `package.json` still said `0.3.6`, the shipped bundle — the code that defines v0.3.7 — carries `PLUGIN_VERSION = "0.3.6"`. The update check then fetches mirror tags (`git-tags.txt`: the check "fetches exactly these tags ... and picks the highest vX.Y.Z"), sees `v0.3.7`, and evaluates `newerTag("v0.3.7")` against `"0.3.6"` → badge "新版本 v0.3.7 可用" on the very release that satisfies it. The tag says 0.3.7; the served code believes it is 0.3.6.

**Why mirror/tag integrity is irrelevant.** `git-tags.txt` shows all three mirrors (origin / public / omdsh) list identical tag SHAs (`748b5e56...` for v0.3.7, `d887deb0...` for v0.3.8) — the release was pushed and verified perfectly. The badge is computed from two locally-consistent inputs (a correct newest tag vs a stale baked constant); no mirror tampering or SHA mismatch can cause or fix it. The defect is inside the built artifact, sealed at build time.

**Corrected release order + the check that would have caught it.** Correct order (which `release-log.md` says was adopted for v0.3.8): bump `package.json` **first**, then build, then commit the built bundle, then tag, then push mirrors. The pre-push check: after building, grep the emitted bundle for the baked constant — e.g. `grep -o 'PLUGIN_VERSION = "[^"]*"' lib/client.js` must equal `package.json`'s `version` — before committing/tagging. Also a functional smoke: the freshly served client must not render its own update badge for its own tag.

---

## 2. Client vs host plane update asymmetry (SVG toggle visible, host route still 404)

**Where each half loads and when.**

- **Client half**: the browser fetches/reloads the client bundle at page load. After the v0.3.8 push the client was refreshed, so the new UI — the SVG render toggle — appears and is clickable (`release-log.md`: "the client half was confirmed refreshed: the new toggle button was rendered by the browser"). A page reload is sufficient for client-plane changes.
- **Host half**: `lib/index.js` runs in the host process, and the asset route + its `CONTENT_TYPES` whitelist are registered **once at host boot**. Pushing new code to disk does not re-execute a process that already started; the running process keeps the module table it loaded at boot.

**How the probes pin the staleness to the RUNNING process, not the release.** `asset-route-probe.txt`:

- PNG probe: `200 OK`, `content-type: image/png` → the route handler itself is alive and registered (not a missing/dead route).
- SVG probe: `404 Not Found`, `"unsupported image type"` → the **whitelist** is rejecting `svg`.
- Disk copy of `lib/index.js` (`lib-index-excerpt.js`) at the same moment **does** whitelist svg: `svg: 'image/svg+xml',`.

Three facts together: route alive (PNG 200) + svg rejected (404) + disk whitelists svg ⇒ the code deciding the 404 is an older in-memory copy from before the whitelist change, i.e. the **running host process is stale**, not the release artifact. `release-log.md` confirms: "a host restart had NOT been performed in this session".

**What makes a host-plane change effective, and why hot-update does not hold here.** The host process must be **restarted** so boot-time route registration re-runs against the new `lib/index.js`. This is the exception to the usual "plugins hot-update" rule: hot-update covers the client plane (browser re-fetches the bundle), but code whose effects are bound into a long-lived process at boot — routes, services, event handlers registered in `apply()` — lives in that process's memory until it restarts. Disk state ≠ process state.

---

## 3. Broken-image attribution (well-formed file, spliced log payload, clean re-read)

**Where the corruption happened — upstream of the plugin, in result-text assembly.** `session-log-excerpt.txt` shows the stored read-result text for the SVG at log line 232:

- stored line 232 = source line 232 up to `...stroke="#dde6ea" stro` **+ source line 247's tail** from `0 0,1 821,730` onward; source lines 233–247 are absent.
- The splice lands on the shared prefix `stro` (`stroke-width...` vs the arc flags of line 247's `A 122,122 0 0,1 821,730`).
- The source file on disk is clean (line 232 ends `stroke-width="6.5"`; line 247 is the intact arc `<path d="M 587,730 A 122,122 0 0,1 821,730" ...`), and an `System.Xml XmlDocument` load confirms: source file **well-formed**; log payload **NOT well-formed** — "error on line 233 at column 54: Specification mandates value for attribute stro0".
- Critically: "the read tool's TYPE result delivered to the caller was clean; the corrupted text is the model-visible result block persisted into the session log" — and a re-read came back clean (non-deterministic). So the corruption occurred in the **session log's result-text persistence layer** (the harness's payload assembly), not in the traced file, not in the plugin's renderer, and not in the live tool result.

**Why the plugin must treat the session payload as untrusted rendering input.** The payload the plugin receives through the session may have been assembled with upstream corruption (here: a mid-file splice at a shared prefix, non-deterministically). Treating it as trustworthy text means the plugin renders harness bugs as "my SVG is broken". The payload is one candidate source among several, each with independent failure modes, so it must be validated (well-formedness check, item 4) before being fed to a renderer.

**Why editing/"repairing" the traced file would have been wrong.** The source file on disk is demonstrably well-formed — the defect exists only in the stored log text. "Fixing" the traced file would corrupt a good artifact to match a bad copy (the repaired content would be based on the spliced lines 233–247, which do not exist on disk), it would mask a genuine upstream harness bug that will strike other reads non-deterministically, and it addresses a layer (file on disk) that was never broken. The correct move is to attribute via forensics (item 5) and report the upstream text-corruption bug.

---

## 4. Defensive render chain for the SVG preview

Ordered render-source design, each level with its justification:

1. **Disk-bytes asset route first.** Serve `daigo-bicycle.svg` bytes straight from disk via the host asset route (`GET /dsh-file-trace/asset?path=...`). Justification: the disk file is the artifact of record and was proven well-formed (`System.Xml` load); bytes-from-disk bypasses the session payload entirely, eliminating the corruption class from item 3. (Prerequisite from item 2: the host must be restarted so the `svg: 'image/svg+xml'` whitelist is live, otherwise this level 404s and we fall through.)
2. **Session payload only after an XML well-formedness check** (`DOMParser`, reject on `parsererror`, or server-side `XmlDocument` load). Justification: the payload is a fallback when the asset route is unavailable, but item 3 proved it can be corrupted (spliced line 232, "attribute stro0"). Parsing before rendering converts a silent broken image into a detected, explainable rejection — the exact failure the log shows ("NOT well-formed — error on line 233 at column 54") becomes an explicit fallback signal rather than a renderer mystery.
3. **Sandboxed iframe as the last render fallback** — `<iframe sandbox>` without `allow-scripts` (scripts blocked) but with SMIL animations still permitted to run. Justification: SVG can embed `<script>` and event handlers; a scriptless sandbox contains hostile or merely unexpected markup while preserving the legitimate animation features a traced SVG may use.
4. **Explicit error state instead of a silent broken image.** When all sources fail validation, render a visible error ("preview unavailable: payload not well-formed / asset route 404"). Justification: the incident's visible symptom was a bare broken image with no attribution; an explicit state names the failing layer (route down vs payload corrupt), making the diagnosis of items 2–3 immediate instead of forensic.

---

## 5. Forensics method + prevention

**Decoding the session log frame-by-frame.** The session log persists as a **concatenated-Zstandard generation file**: one physical file that is a stream of independent zstd frames back-to-back. Method:

1. Read the generation file as raw bytes; locate zstd frame boundaries (each frame's magic number 0xFD2FB528) and split the concatenation into individual frames.
2. Decompress **each frame separately** with a zstd decoder (a single-pass decompressor that stops at the first frame will lose everything after it — the concatenation is the reason frame-by-frame splitting is required).
3. Sequence the decompressed frames in order to reconstruct the session event stream; index to the payload of interest (here, the read-result block around log line 232) and recover the **exact stored text**.
4. Diff the recovered stored text against the on-disk source (this is exactly what produced the item-3 evidence: splice at the `stro` prefix, lines 233–247 absent, XML verdict "error on line 233 at column 54"). This turns "the render looked broken" (anecdote) into "the persisted payload differs from the well-formed disk file; the corruption is upstream of the plugin" (evidence).

**Release-checklist items this incident adds:**

- **Version-bump-before-build**: bump `package.json` before `pnpm run build` so the bundler inlines the new version (v0.3.8 followed the corrected order per `release-log.md`).
- **Grep the shipped bundle for the baked constant**: after build, verify `lib/client.js` contains `PLUGIN_VERSION = "<package.json version>"` — this check would have caught `"0.3.6"` inside the v0.3.7 bundle before tag/push, preventing the phantom badge without needing the amend + rebuild + force-move-the-tag-on-all-mirrors re-release.
- **Per-mirror tag SHA verification**: `git ls-remote --tags` on every mirror (origin / public / omdsh) must show identical SHAs for the released tag, as recorded in `git-tags.txt`.
- **Report the upstream text-corruption bug instead of papering over it**: the session-log result-text assembly corrupts read results non-deterministically (splice at a shared prefix, clean on re-read). That is a harness bug; the plugin's job is to validate its inputs (item 4) and file the upstream report — never to "repair" a well-formed traced file to match a corrupted copy.
- (From item 2:) **host-plane changes require a host restart** — a release that touches `lib/index.js` is not effective until the host process re-registers its routes; verify with the PNG-200/SVG-404-vs-disk-whitelist probe before declaring the release live.
