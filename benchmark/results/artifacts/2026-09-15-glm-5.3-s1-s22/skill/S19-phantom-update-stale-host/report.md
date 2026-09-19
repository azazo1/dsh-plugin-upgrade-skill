# S19 · The Phantom Update, the Stale Host Half, and the Corrupted Payload — Read-Only Analysis

Task: root-cause and remediate-design three post-release defects of `@dsh-external/dsh-file-trace` (v0.3.7 / v0.3.8), using only the read-only evidence pack. Mode: **A · inspect** (plugin-upgrade skill) — no migrations, installs, or writes to the fixture.

---

## 1. Phantom self-update root cause ("新版本 v0.3.7 可用" on v0.3.7)

**Where the compared constant comes from.** The shipped `lib/client.js` (v0.3.7 tag, verbatim in `client-bundle-excerpt.js`) contains:

```js
export const PLUGIN_VERSION = "0.3.6";
```

`PLUGIN_VERSION` is a **build-time constant**: tsdown inlined the value from `package.json` *at the moment the bundle was emitted*. It is never read dynamically at runtime. The update check runs `git ls-remote --tags` (no auth) against the mirrors, picks the highest `vX.Y.Z`, and `newerTag(latestTag)` returns the tag when `compareSemver(latestTag, PLUGIN_VERSION) > 0`.

**The operation-order mistake.** `release-log.md` for v0.3.7:

- 16:22 `pnpm run build` ← bundle emitted
- 16:23 bump `package.json` 0.3.6 → 0.3.7 ← **version bumped AFTER the build**
- 16:24 commit (including the already-built `lib/client.js`) + tag `v0.3.7`

So the committed-and-tagged artifact carries the *old* version 0.3.6 baked in, while the tag says v0.3.7. At runtime the freshly installed plugin compares `latestTag = "v0.3.7"` (from mirrors) against `PLUGIN_VERSION = "0.3.6"`, semver says 0.3.7 > 0.3.6, and the drawer announces an update to itself.

**Why mirror/tag integrity is irrelevant.** The tag SHA was verified identical (`748b5e56…`) on all three mirrors and all mirrors serve the same bundle. The check compares *tag-space* against *bundle-space*. Integrity guarantees both sides are consistent copies of the same (wrong) artifact; it cannot detect that the artifact itself embeds a stale constant. Verifying tag SHAs validates transport, not build inputs.

**Corrected release order.**

1. bump `package.json` version first;
2. build (so the bundler inlines the new version);
3. verify the baked constant (below);
4. commit, tag, push to mirrors, verify tag SHAs.

This is exactly the correction the maintainer applied for v0.3.8 ("bump FIRST, then build"); the v0.3.7 artifact required a re-release (amend + rebuild + force-move the tag on all mirrors).

**The check that would have caught it before pushing.** After build, before commit/tag/push:

```sh
grep -o 'PLUGIN_VERSION = "[^"]*"' lib/client.js
# or: grep -o '"0.3.[0-9]*"' lib/client.js | sort -u
```

and assert the output equals the version just written to `package.json` (ideally wired into the release script / CI as a hard gate). Any mismatch aborts the release.

---

## 2. Client-plane vs host-plane update asymmetry

**Symptom.** After the v0.3.8 push the browser shows the new SVG render toggle (client half refreshed), but clicking Render gets a 404 from the host asset route for the `.svg`, while a PNG probe returns 200 and the shipped `lib/index.js` *does* whitelist `svg: 'image/svg+xml'`.

**Where each half is loaded.** The plugin has two planes:

- **Client half** (`lib/client.js`) is fetched by the browser. A page refresh / client re-fetch re-evaluates the current artifact — so the new toggle UI reached the browser without touching the host process.
- **Host half** (`lib/index.js`) is loaded when the DSH host process boots it and its routes/services are registered **at boot time**. This session never restarted the host after the SVG whitelist change.

**Why the probes pin staleness to the running host process, not the release.**

| Observation | Implication |
|---|---|
| PNG probe → 200 `image/png` | the route handler is alive and registered; the 404 is the *extension whitelist* rejecting svg, not a missing route |
| SVG probe → 404 "unsupported image type" | the *executing* whitelist has no `svg` key |
| disk `lib/index.js` contains `svg: 'image/svg+xml'` | the *released and link-installed* artifact is correct |

A live route rejecting svg while the on-disk file whitelists svg is only possible if the code answering the request is not the code on disk — i.e., the running host process still holds the pre-change module in memory. The defect is in the **running process**, not the release.

**What makes a host-plane change effective.** The host must be stopped and re-booted (restart `dsh web`; per the skill's host-upgrade discipline: fully stop, then start — a browser refresh is *not* a host stop). After restart the route re-registers from the current `lib/index.js` and the SVG probe will answer 200 `image/svg+xml`.

**Why "plugins hot-update" does not hold here.** Client-plane artifacts are re-fetched per page load, so a rebuilt client appears to "hot-update". Host-plane code is bound into the long-lived host Node process at activation/boot; nothing re-reads `lib/index.js` until that process restarts. This incident is exactly the case where the client refreshes and the host does not — the one case where relying on the usual hot-update rule leaves the new host route dark while the new UI is visible.

---

## 3. Broken-image attribution

**Given:** well-formed source file on disk; corrupted text in the session log's read-result block (line 232 = source line 232 truncated at `stro` + source line 247's tail spliced at the shared prefix, lines 233–247 absent); clean re-read afterwards; the read tool's TYPE result delivered to the caller was clean.

**Where the corruption happened.** The corrupted text exists only in the *model-visible result block persisted into the session log* — the result-text assembly layer upstream of the plugin produced it. The chain is: disk bytes (clean) → read-result text assembly (corruption occurred here, non-deterministically — the splice at a shared `stro` prefix and the clean re-read indicate a transient assembly/persistence bug, not a property of the file) → session log payload (stores the corrupted text) → plugin render path. The plugin is the last, innocent consumer.

**Why the session payload must be treated as untrusted rendering input.** The payload is (a) produced upstream by code the plugin does not control, (b) demonstrated here to corrupt silently, and (c) reconstructed from a concatenated-zstd generation file whose decode path is independent of the plugin. Any text handed to a renderer (XML parser, DOM, iframe) must be validated before use; "it came from the session log" is not an authenticity guarantee.

**Why editing/"repairing" the traced file would have been wrong.** The file on disk is well-formed; the corruption lives in one stored payload. Editing the source would (1) modify a good file to match a bad copy, (2) leave the upstream bug intact and unreported, (3) diverge the workspace from what the user actually traced. The correct action is to bypass the bad payload (re-read / render from disk bytes) and report the upstream result-text-corruption bug.

---

## 4. Defensive render chain for the SVG preview

Ordered render-source chain, each level justified:

1. **Disk-bytes asset route first.** After a host restart, `GET /dsh-file-trace/asset?path=…svg` serves the file's raw bytes from disk — bypassing the session-log text entirely. Disk is the authoritative source (proven well-formed here); bytes avoid any text re-encoding. This is the only source that provably reflects the file the user traced.
2. **Session payload only after an XML well-formedness check.** When the payload must be used (e.g., asset route unavailable or the file has since changed), first parse with `DOMParser` (`text/xml`) and reject on `parsererror` (or scan for a `<parsererror>` element). The incident's corrupted payload fails exactly this gate ("Specification mandates value for attribute stro0"), converting silent breakage into a detectable condition. Never feed unvalidated payload text into a renderer.
3. **Sandboxed iframe as the last render fallback.** If inline rendering is not possible, render inside a sandboxed `<iframe sandbox>` with scripts blocked (`sandbox` without `allow-scripts`): SVG can carry `<script>`, `onload` handlers, and external references, so untrusted SVG must never enter the main document directly. SMIL animations (`<animate>` etc.) are declarative and still run under this sandbox, preserving preview fidelity. `<img>`-based display is an alternative script-safe path but loses SMIL/interactive fidelity.
4. **Explicit error state instead of a silent broken image.** Each failure (404 from the asset route, `parsererror` from validation, sandbox load failure) maps to a visible, specific error card — never a bare broken-image glyph. The incident's user-visible symptom was precisely a silent broken image with no diagnostic; explicit states make the failure attributable (host not restarted vs corrupted payload vs unreadable file) and actionable.

---

## 5. Forensics method + prevention

**Decoding the session log.** The session log is a concatenated-Zstandard generation file: a sequence of independently compressed zstd frames (per the DSH session format, one generation with monotonic framing). Frame-by-frame recovery:

1. read the generation file and locate frame boundaries — each zstd frame begins with the magic `0x28 B5 2F FD` (the frame header carries the frame size when known), so scan/split on the magic;
2. decompress each frame independently (e.g., `zstd -d` streaming, or Node `zlib`/`@mongodb-js/zstd` per-frame) — concatenation means no cross-frame dictionary dependency;
3. each decoded frame yields session-event records; locate the `read` tool's result event (here around payload line 232) and extract the stored result text verbatim;
4. diff the stored text against a fresh disk read of the same region and check XML well-formedness of both — this is exactly how the excerpt's verdicts (source well-formed, payload NOT well-formed at line 233 col 54) were obtained, turning "rendering sometimes breaks" into reproducible evidence of an upstream splice.

**Release-checklist items this incident adds:**

- **Version-bump-before-build**: bump `package.json` *before* `pnpm run build`; the build inlines the version at emit time (fixes the phantom badge at the source).
- **Grep the shipped bundle for the baked constant**: `grep 'PLUGIN_VERSION' lib/client.js` and assert it equals the release version, as a hard gate before commit/tag/push (catches the stale constant regardless of human order errors).
- **Per-mirror tag SHA verification**: keep `git ls-remote --tags` SHA comparison across origin/public/omdsh — necessary for transport integrity, and now understood to be *insufficient* for build-input correctness.
- **Restart the host after host-plane changes**: a release touching `lib/index.js` is complete only after the host process is rebooted and the new route/probe verified (SVG probe must return 200 `image/svg+xml`); a refreshed client is not evidence of a refreshed host.
- **Report the upstream text-corruption bug** (result-text assembly splicing lines in the persisted session payload) to the host/read-tool maintainers with the frame-by-frame log evidence — do not paper over it inside the plugin with payload "repair" or by editing traced files; the plugin-side mitigation is the validated render chain (§4), which treats payloads as untrusted input.

---

## Skill-mode note

Executed as Mode A (read-only inspection). No files under the fixture were modified; no installs, migrations, or lifecycle scripts were run. Items beyond the evidence pack (e.g., verifying the actual zstd frame layout of a real generation file) are marked from the excerpt's stated decoding description, not independently reproduced — pending/residual risk: none affecting the three root-cause attributions, which rest on verbatim fixture evidence.
