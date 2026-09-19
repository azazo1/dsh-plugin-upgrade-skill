# S19 — The Phantom Update, the Stale Host Half, and the Corrupted Payload

Read-only diagnostic report for the `@dsh-external/dsh-file-trace` v0.3.7/v0.3.8 release incident.
Evidence source: `environment/fixture/` (README.md, release-log.md, package.json, git-tags.txt, client-bundle-excerpt.js, asset-route-probe.txt, lib-index-excerpt.js, session-log-excerpt.txt). The fixture was not modified.

---

## 1. Phantom self-update root cause

**What the evidence shows.** The shipped `lib/client.js` for tag v0.3.7 contains, verbatim (`client-bundle-excerpt.js`):

> `export const PLUGIN_VERSION = "0.3.6";` — "tsdown inlined this constant from package.json WHEN THE BUNDLE WAS BUILT — it is not read dynamically at runtime."

And the self-update check:

> `function newerTag(latestTag) { return latestTag !== undefined && compareSemver(latestTag, PLUGIN_VERSION) > 0 ? latestTag : undefined; }`
> — "newerTag(\"v0.3.7\") with PLUGIN_VERSION \"0.3.6\" -> \"v0.3.7\" → badge shows \"新版本 v0.3.7 可用\" on the just-released v0.3.7 itself."

**Where the compared version comes from: build time, not runtime.** `PLUGIN_VERSION` is a compile-time constant inlined into the bundle when `pnpm run build` ran. The running plugin compares its own **baked** version against the newest mirror tag (fetched via `git ls-remote --tags`, per `git-tags.txt`).

**The operation-order mistake.** `release-log.md` for v0.3.7:

> "3. 16:22 `pnpm run build` — client bundle emitted ← build ran here"
> "4. 16:23 bump `package.json` version 0.3.6 → 0.3.7 ← version bumped AFTER the build"

The build ran **before** the version bump, so the bundle was baked with `0.3.6` even though the tag, commit, and package.json all said `0.3.7`. The result served to the browser is a "v0.3.7" release that believes it is v0.3.6 — so when it sees the v0.3.7 tag it correctly concludes a newer version exists. The badge is not a bug in the comparison logic; the input constant is stale.

**Why mirror/tag integrity is irrelevant.** `git-tags.txt` shows all three mirrors (origin / public / omdsh) list both tags with **identical SHAs**:

> `748b5e56e41ca4dc22da1631569fb29d8ae0b99d  refs/tags/v0.3.7` — same on every mirror.

Tag distribution, SHA consistency, and push completeness are all perfect. The corruption is entirely inside the already-built artifact, so no amount of mirror or tag verification could detect it: the tag points at the commit that contains the wrongly-built bundle.

**Corrected release order.** Exactly what the maintainer did for v0.3.8:

1. bump `package.json` version first (and any install refs that encode the version, e.g. README `#v0.3.7` anchors);
2. commit;
3. build (so the inlined `PLUGIN_VERSION` reads the new manifest);
4. commit the built artifacts;
5. tag and push, then verify SHAs on every mirror.

**The check that would have caught it.** A post-build, pre-push assertion that greps the shipped bundle for the baked constant, e.g. `grep -E 'PLUGIN_VERSION = "\d+\.\d+\.\d+"' lib/client.js` must equal the package.json version. More generally: run the verification against the artifact, not the manifest — a green typecheck + 104 vitest passes (`release-log.md` step 2) proves nothing about a build-order bug.

---

## 2. Client vs host plane update asymmetry

**Symptom (after the v0.3.8 push):** the browser shows the new SVG render toggle (client half refreshed), but `asset-route-probe.txt` shows:

> `GET /dsh-file-trace/asset?path=...daigo-final.png` → `200 OK / content-type: image/png`
> `GET /dsh-file-trace/asset?path=...daigo-bicycle.svg` → `404 Not Found / "unsupported image type"`

while `lib-index-excerpt.js` (the link-installed repo's shipped host half at tag v0.3.8) whitelists SVG:

> `const CONTENT_TYPES = { ..., svg: 'image/svg+xml', ... }`

**Why the halves diverge.**

- **Client half:** served per-request to the browser; the browser re-fetches the client bundle (page refresh / reload) and executes the newest served code. That is why the new toggle button renders — the served client bundle is the v0.3.8 one.
- **Host half:** route registration happens **once at host boot time**. The running host process registered `/dsh-file-trace/asset` — including its `CONTENT_TYPES` whitelist — from the *old* module the moment the host started. Linking a new version on disk does not re-execute that registration; the handler in memory still has the pre-SVG whitelist.

**Why the probes pin the staleness to the RUNNING HOST PROCESS, not the release:**

1. The route handler itself is alive — the PNG probe answers 200 `image/png` (`asset-route-probe.txt`: "the 404 is the extension whitelist rejecting svg — not a missing route"). So this is not a missing route or a broken deployment.
2. The 404 body, "unsupported image type", is exactly the old whitelist's rejection path for an unlisted extension.
3. The disk artifact at the same moment DOES contain `svg: 'image/svg+xml'` (`lib-index-excerpt.js`). Disk ≠ process, so the release is correct and the **running process is stale**.
4. `release-log.md` confirms the precondition: "a host restart had NOT been performed in this session (the client half was confirmed refreshed: the new toggle button was rendered by the browser)."

**What makes a host-plane change effective.** Restarting the host: only a fresh process re-imports `lib/index.js` and re-registers the asset route with the new whitelist. This is the case where the usual "plugins hot-update" rule does **not** hold — a DSH plugin's *client* module is re-served and re-executed on browser refresh, but host-half code loaded into the long-lived Node process (route registrations, services, handlers) persists for the lifetime of the process. This matches the skill's global-host-upgrade discipline (the session IS the host process; in-process code does not swap underneath itself) — the client/browser plane and the host process plane have different reload semantics, and only the browser side can be refreshed from within.

---

## 3. Broken-image attribution

**Symptom:** one traced SVG renders broken through the session payload. The evidence triangulates cleanly:

- **Source file on disk: clean.** `session-log-excerpt.txt` §2: line 232 is `<circle r="98" fill="none" stroke="#dde6ea" stroke-width="6.5"/>` and the arc path on line 247 is intact.
- **Session-log payload: corrupted.** §1: payload line 232 reads `...stroke="#dde6ea" stro0,1 821,730" fill="none"...` — source line 232's head spliced with line 247's tail ("0 0,1 821,730" onward); source lines 233–247 are absent. §3: "log payload: NOT well-formed — 'error on line 233 at column 54: Specification mandates value for attribute stro0'".
- **Re-read: clean.** §4: "A re-read of the same region afterwards came back clean (non-deterministic)."
- **Ownership of the layer that produced the text.** §4: "The read tool's TYPE result delivered to the caller was clean; the corrupted text is the model-visible result block persisted into the session log, i.e. the corruption happened in the **result-text assembly, upstream of the plugin**." The splice pattern (a shared prefix "stro" joining two distant lines' fragments, a whole run of middle lines missing) is a classic buffer/assembly truncation-splice — a nondeterministic, upstream fault in the layer that assembles the persisted result text, not a property of the file.

**Why the plugin must treat the session payload as untrusted rendering input.** The plugin never saw the disk bytes in this path — it rendered whatever text the session payload carried. That text has now been shown to differ from the disk source, to fail XML well-formedness, and to be non-deterministic (a re-read was clean). Any payload is therefore input of unknown provenance, exactly like model/tool output: it must be validated before rendering, and a validation failure must be reported, not silently visualized as a broken image.

**Why editing/repairing the traced file was the wrong move.** The file is provably well-formed on disk ("source file: well-formed, System.Xml XmlDocument load: no error" — §3). Repairing it would corrupt a correct artifact to satisfy a corrupted copy; the actual defect lives upstream in result-text assembly, and patching the file would (a) destroy the evidence and (b) not prevent recurrence on the next corrupted payload. Per the skill's discipline: when local observation conflicts with a primary source, record both, reproduce, and report — do not silently pick one side by "fixing" the innocent artifact.

---

## 4. Defensive render chain (design)

Render-source order for the SVG preview, with the justification for each level:

1. **Disk-bytes asset route first.** If the host asset route serves the file (`GET /dsh-file-trace/asset?path=...` → 200), render those bytes. Justification: the bytes come straight from the authoritative artifact, bypassing session-payload assembly entirely — the one proven corruption point in this incident (§3 above). Note the chain presupposes the §2 fix: the host must be restarted so the route actually serves `image/svg+xml`; the route should also send the correct content-type so the browser treats it as an image.
2. **Session payload only after an XML well-formedness check.** Fall back to the payload text the session carries, but parse it with `DOMParser` and check for a `parsererror` element (the check that already distinguishes the two evidence states in fixture §3: source "well-formed", payload "NOT well-formed"). Justification: the payload is untrusted input (proven §3); a well-formed parse establishes the minimum precondition for the SVG to render at all, and the check is cheap, synchronous, and deterministic — it converts the silent broken image into an actionable signal.
3. **Sandboxed iframe as the last render fallback.** If direct rendering fails or the content type is uncertain, render inside a sandboxed iframe (e.g. `sandbox="allow-same-origin"` without `allow-scripts`). Justification: SVG is an active content format — embedded `<script>` executes when inlined into the DOM. A sandboxed frame blocks scripts while still running declarative SMIL animations (the traced figure's animation still previews), containing the active-content risk without disabling the visual feature.
4. **Explicit error state instead of a silent broken image.** If every level fails, surface a distinct "preview unavailable / source not well-formed" state with the reason. Justification: this incident's worst property was that corruption manifested as a generic broken image, indistinguishable from a missing file — the maintainer nearly blamed the traced file. An explicit, attributed error state points the diagnosis at the right layer and matches the AGENTS.md principle that misconfiguration/corruption fails loud.

Each level independently fails safe: level 1 avoids the corrupt layer, level 2 rejects non-well-formed text, level 3 contains active content, level 4 makes residual failure visible.

---

## 5. Forensics method + prevention

**Decoding the session log frame-by-frame.** The session log on disk is a **concatenated-Zstandard generation file**: many independently compressed zstd frames concatenated back-to-back. Because plain `zstd -d` stops at the first frame, decode each frame individually — e.g. stream the file through a zstd streaming reader with multi-frame mode enabled (zstd `-D`/streaming API with `ZSTD_d_multipleFrames`, or Python `zstandard.ZstdDecompressor(...).decompressobj()` in a loop / the `zstd` CLI with `--stream-size` per frame) until EOF, concatenating the decompressed frames in order. That reproduces the exact stored text — here, the read-result block around "payload around line 232" of `session-log-excerpt.txt`, including the spliced line, byte-for-byte. This is what turns "the image looked broken" (anecdote) into "the persisted result text differs from the disk file at lines 233–247 and fails XML parsing at line 233 column 54" (evidence) — the observation that cleanly attributes the fault upstream of the plugin.

**Release-checklist items this incident adds:**

1. **Version-bump-before-build.** Bump `package.json` (and version-bearing refs) before running the build, so the inlined `PLUGIN_VERSION` is current (the corrected v0.3.8 order in `release-log.md`).
2. **Grep the shipped bundle for the baked constant.** After build, assert `lib/client.js` contains `PLUGIN_VERSION = "<package.json version>"` — verify the artifact, not the manifest; run before tag/push.
3. **Per-mirror tag SHA verification.** `git ls-remote --tags` on every mirror and require identical SHAs (as `git-tags.txt` records for origin/public/omdsh). Necessary but explicitly *not sufficient* — it passed while the bundle was stale; it guards distribution, not build order.
4. **Restart the host after a host-half change.** Any change to host-plane code (route whitelists, services) requires a host restart to take effect; probe the actual route (PNG 200 control + new-type probe) after restart rather than trusting a refreshed browser as evidence.
5. **Report the upstream text-corruption bug instead of papering over it.** The splice is a nondeterministic defect in result-text assembly upstream of the plugin; file it upstream with the decoded-log evidence (spliced line, missing line range 233–247, parsererror, clean re-read) and keep the plugin's job limited to validating untrusted payloads — never edit the well-formed traced file to mask it.
