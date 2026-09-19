# S19 · The Phantom Update, the Stale Host Half, and the Corrupted Payload — Report

Task: analyze the v0.3.7/v0.3.8 release incident of `@dsh-external/dsh-file-trace`
from the read-only evidence pack (`environment/fixture/`). All findings below are
grounded in the fixture files cited inline.

---

## 1. Phantom self-update root cause ("新版本 v0.3.7 可用" on v0.3.7 itself)

**Where the compared constant comes from.** The client bundle's self-update check
(`client-bundle-excerpt.js`) compares `compareSemver(latestTag, PLUGIN_VERSION) > 0`,
where `PLUGIN_VERSION` is an ES module constant:

```js
/** The running plugin version (from package.json at build time). */
export const PLUGIN_VERSION = "0.3.6";
```

tsdown **inlined** this value from `package.json` **at build time**. It is a frozen
string baked into `lib/client.js`, not something read dynamically at runtime. The
"latest version" side is fetched live (`git ls-remote --tags` against the mirrors,
picking the highest `vX.Y.Z` — see `git-tags.txt`).

**The operation-order mistake.** `release-log.md` v0.3.7 steps:

1. 16:22 `pnpm run build` — client bundle emitted  ← build ran **first**
2. 16:23 bump `package.json` 0.3.6 → 0.3.7          ← bump ran **after** the build
3. 16:24 commit (including the already-built `lib/client.js`) + tag `v0.3.7`
4. 16:25 push to all three mirrors; tag SHA verified everywhere

So the artifact committed under tag `v0.3.7` still carries `PLUGIN_VERSION = "0.3.6"`.
At runtime the check compares live-latest `v0.3.7` > baked `0.3.6` → true → the badge
announces an update to itself.

**Why mirror/tag integrity is irrelevant.** The integrity chain (identical tag SHA
`748b5e5…` on origin/public/omdsh in `git-tags.txt`) proves only that *the same wrong
artifact* was delivered everywhere. The corruption is semantic, not a distribution
failure: the released bundle's content disagrees with its own tag because of build
ordering. No amount of SHA verification can catch a constant that was stale *before*
the commit was made. That's why the remediation had to be amend + rebuild +
force-move the tag — re-pushing the same bytes would change nothing.

**Corrected release order** (as actually adopted for v0.3.8 in `release-log.md`):

1. edit source + tests, typecheck/tests green
2. **bump `package.json` version FIRST**
3. build (so the bundler inlines the new version)
4. **check the shipped bundle for the baked constant** before committing — e.g.
   `grep -o 'PLUGIN_VERSION = "[0-9.]*"' lib/client.js` and assert it equals the
   tag being cut; fail the release if they differ
5. commit + tag + push mirrors + per-mirror `git ls-remote` SHA verification

The check that would have caught it at step 4 is exactly a one-line grep of the
emitted bundle for the version literal versus the manifest — a build-artifact
version-consistency gate.

---

## 2. Client vs host plane update asymmetry (toggle visible, SVG route 404)

**Where each half loads.** The plugin has two independently-loaded halves:

- **Client half** (`lib/client.js`): loaded by the browser, which re-fetches/reloads
  the bundle (the harness has an active client-plugin HMR/reload path). The new SVG
  render toggle appearing in the browser proves the *new client code* was fetched and
  executed — the browser plane refreshed without a host restart.
- **Host half** (`lib/index.js`): loaded by the DSH Node host process at plugin
  load/boot time. Its asset route and the `CONTENT_TYPES` whitelist were registered
  when the host process started — which, per `release-log.md`, was **before** the SVG
  whitelist change. Host code does not hot-reload; the registered route closure still
  holds the old whitelist (without `svg`).

**How the probes pin the staleness to the running process, not the release**
(`asset-route-probe.txt` + `lib-index-excerpt.js`):

- PNG probe → `200 image/png`: the route handler is alive and serving; the plugin
  (some version of it) is loaded and functional. Not a missing route.
- SVG probe → `404 "unsupported image type"`: the whitelist that *rejected* the
  request does not contain `svg` — that is the pre-v0.3.8 whitelist.
- The **disk** `lib/index.js` at tag v0.3.8 **does** whitelist `svg:
  'image/svg+xml'` (verbatim in `lib-index-excerpt.js`).

Disk artifact ⊇ svg, running behavior rejects svg ⟹ the executing code is an older
in-memory copy: the link-installed repo was updated, but the host process still runs
the module image loaded at boot. The release is correct; the *process* is stale.

**What makes a host-plane change effective:** restart the host (or reload the plugin
in the host), so `lib/index.js` is re-imported and the route re-registered with the
new whitelist. This is the one case where the usual "plugins hot-update" intuition
does not hold: client-plugin reload refreshes only the browser half; host-half
changes (route registration, whitelist constants) take effect at host module-load
time only. As the harness context itself notes, every non-client-bundle change
requires rebuilding/reloading the affected host artifacts and restarting the server —
a page refresh or client HMR event can never update a route registered inside the
running Node process.

---

## 3. Broken-image attribution (corrupted session payload, not the traced file)

From `session-log-excerpt.txt`:

- The **source file on disk** is well-formed XML (`System.Xml` load: no error), and a
  **re-read** of the same region afterwards came back clean.
- The **session log's stored read-result text** is not well-formed: payload line 232
  is source line 232 truncated mid-token at the shared prefix `stro`, spliced with
  the tail of source line 247 (`0 0,1 821,730" …`); lines 233–247 are missing.
  XML parser error: *"error on line 233 at column 54: Specification mandates value
  for attribute stro0"*.
- The read tool's own TYPE result delivered to the caller was clean; the corrupted
  text is the **model-visible result block persisted into the session log**.

**Where the corruption happened:** in the **result-text assembly layer upstream of
the plugin** — the machinery that assembles/persists the read result into the session
log. The evidence triangulates: identical bytes read cleanly before and after, so the
file never changed; the corruption exists only in the persisted payload; the splice
(at a shared prefix) and non-deterministic reproduction point to a text-assembly bug
(e.g. concurrent buffer/line handling), not to anything the plugin controls.

**Consequences:**

- The plugin **must treat the session payload as untrusted rendering input**. Payload
  text is a *copy* produced by upstream layers; it is not guaranteed byte-identical
  to disk (this incident is the proof) nor guaranteed well-formed. Any render path
  that feeds it into the DOM must validate it first (see §4).
- **Editing or "repairing" the traced file would have been wrong** because the file
  was never broken: it was well-formed on disk and re-read cleanly. "Fixing" it would
  (a) destroy the evidence of an upstream bug, (b) mutate a user file based on a
  corruption the file does not contain, and (c) leave the real bug free to corrupt
  the next payload. The correct action is to report the upstream session-payload
  text-corruption bug with the decoded log excerpt attached.

---

## 4. Defensive render chain for the SVG preview

Render-source order, most-trusted first, each level justified:

1. **Disk-bytes asset route first.** The host asset route reads the file from disk
   and serves it with `image/svg+xml` — no opportunity for session-log corruption,
   no model-visible text path at all. Once the host half is actually restarted (§2),
   this is the authoritative source. Render via `<img src=…asset?path=…>`: images
   referenced this way do not execute scripts, giving the safest default display.
   Justification: bytes straight from the filesystem, shortest path, immune to the
   §3 corruption class.

2. **Session payload, but only after a well-formedness gate.** When disk access is
   unavailable (path deleted, sandboxed away), fall back to the payload text the
   client already has — but first run `new DOMParser().parseFromString(text,
   "image/svg+xml")` and check for a `<parsererror>` element. Only a document with
   no parser error is rendered; anything else drops to level 3 / the error state.
   Justification: §3 proves payloads can be silently corrupted; parsing is cheap,
   local, and catches exactly the observed splice (attribute `stro0` with no value).

3. **Sandboxed iframe as the last render fallback** — used when the validated SVG
   must be rendered as a live document (e.g. features `<img>` won't render).
   Sandbox flags: `sandbox="allow-same-origin-off"` i.e. `sandbox` without
   `allow-scripts` (scripts blocked, no `allow-same-origin` so it stays opaque-origin),
   while SMIL animations still run because they are declarative and not gated on
   script permission. Justification: even a well-formed SVG can carry `<script>` or
   event-handler attributes; the sandboxed iframe confines any residual active
   content while preserving the animated preview.

4. **Explicit error state instead of a silent broken image.** Every failure (404
   from the asset route, parser error, empty payload) renders a visible,
   user-comprehensible error card naming the failed source level and reason —
   never a bare broken-image icon. Justification: this incident was *diagnosable
   only because probes were run manually*; a surfaced error state turns the next
   occurrence into an immediate signal, and tells the user the file itself is fine
   when the payload is the culprit.

---

## 5. Forensics method + prevention

**Decoding the session log.** The session log is a concatenated-Zstandard
("zstd") generation file: a sequence of independently compressed frames
concatenated back to back. Frame-by-frame recovery:

1. open the generation file as a byte stream;
2. repeatedly locate the next zstd frame (magic `0x28 B5 2F FD`), decompress that
   single frame with a streaming/multi-frame-capable zstd reader
   (`zstd -d --long`, `DecompressStream`, or a loop of `ZSTD_decompressFrame`);
3. each decompressed frame yields event records; select the read-result event
   (payload around line 232 in the excerpt) and extract its stored text verbatim;
4. diff that stored text against a fresh disk read of the same file (and against
   the clean TYPE-result) to demonstrate the splice and the missing lines 233–247.

This is what turns "the image is broken" from an anecdote into evidence: the exact
stored bytes, the exact splice point, and the well-formedness verdicts.

**Release-checklist items this incident adds:**

- **Version-bump-before-build** — bump `package.json` before running the bundler, so
  build-time-inlined constants match the tag being cut.
- **Grep the shipped bundle for the baked constant** — assert
  `PLUGIN_VERSION` in `lib/client.js` equals the release version before commit/push;
  automate it as a release gate.
- **Per-mirror tag SHA verification** — keep `git ls-remote --tags` on every mirror
  (already practiced here); it proves distribution integrity even though it cannot
  catch semantic staleness — both checks are needed.
- **Host-plane restart after host-half changes** — a release checklist item: any
  change to host-loaded code (`lib/index.js`, route registration, whitelists)
  requires a host restart/reload and a post-restart probe (e.g. the PNG/SVG asset
  probes) before declaring the release live.
- **Report the upstream session-payload text-corruption bug** — file the splice bug
  (with decoded log excerpt, repro notes, non-determinism) against the session-log /
  read-result assembly layer; do not paper over it in the plugin (no silent
  "repair", no swallowed parse errors).

---

## Verdict summary

| Symptom | Root cause | Plane / layer |
|---|---|---|
| v0.3.7 badges "update to v0.3.7" | `PLUGIN_VERSION` inlined at build time (still `0.3.6`) because version bump ran **after** the build; tag/mirror SHAs are irrelevant to baked content | client bundle build order |
| Toggle visible, SVG 404 (PNG 200, disk lib whitelists svg) | running host process still holds the pre-v0.3.8 route/whitelist loaded at boot; client refresh ≠ host reload; host restart required | host plane, boot-time registration |
| Traced SVG renders broken | session-log read-result text spliced at a shared prefix (`stro`) by upstream result-text assembly; disk file well-formed; re-read clean | upstream session-payload layer — report, don't repair |
