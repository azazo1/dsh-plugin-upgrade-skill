# S19 · The Phantom Update, the Stale Host Half, and the Corrupted Payload — Report

Task: S19-phantom-update-stale-host (read-only analysis)
Evidence pack: `environment/fixture/` (release-log.md, package.json, git-tags.txt, client-bundle-excerpt.js, asset-route-probe.txt, lib-index-excerpt.js, session-log-excerpt.txt, README.md)

---

## 1. Phantom self-update root cause

**What the badge compares.** The shipped client bundle contains (client-bundle-excerpt.js):

```js
export const PLUGIN_VERSION = "0.3.6";
```

with the comment: tsdown **inlined** this constant from `package.json` **at build time**; it is not read dynamically at runtime. The self-update check runs `git ls-remote --tags` (git-tags.txt confirms this fetches the tags live, no auth) and picks the highest `vX.Y.Z`; `newerTag()` shows a badge when `latest > PLUGIN_VERSION`.

**The operation-order mistake.** release-log.md shows the actual v0.3.7 order:

1. 16:20 edit source + tests
2. 16:21 typecheck + vitest green
3. 16:22 `pnpm run build` — **client bundle emitted here** ← the bundle baked `PLUGIN_VERSION = "0.3.6"`
4. 16:23 bump `package.json` 0.3.6 → 0.3.7 ← **version bumped AFTER the build**
5. 16:24 commit (including the already-built `lib/client.js`) + tag `v0.3.7`
6. 16:25 push main + tag to three mirrors; tag SHA verified on all three

So the artifact that was committed and tagged as v0.3.7 still carries the *old* constant "0.3.6". At runtime the freshly released client compares live tags (max = `v0.3.7`) against its baked "0.3.6": `0.3.7 > 0.3.6` → badge "新版本 v0.3.7 可用" — the plugin announcing an update to itself.

**Why mirror/tag integrity is irrelevant.** git-tags.txt shows all three mirrors (origin / public / omdsh) list both tags with identical SHAs (`748b5e56...` for v0.3.7). The distribution channel is perfectly consistent — every mirror serves the *same* (stale-constant) bundle. The defect is inside the artifact's content, not in how it was distributed; verifying tag SHAs only proves all mirrors agree, not that the committed bundle was rebuilt after the bump. Integrity ≠ freshness.

**Corrected release order** (as the maintainer himself adopted for v0.3.8): bump `package.json` **first**, then build, then commit + tag + push:

1. edit source + tests → checks green
2. bump version 0.3.6 → 0.3.7
3. `pnpm run build` (bundle now inlines "0.3.7")
4. commit, tag, push, verify tag SHA per mirror

**The check that would have caught it before pushing:** grep the shipped bundle for the baked constant — e.g. `grep -n 'PLUGIN_VERSION' lib/client.js` (or `grep -o '0\.3\.[0-9]*' lib/client.js | sort -u`) and assert the emitted value equals the version in `package.json`. A one-line CI/release step "bundle version == manifest version" fails loud before anything is tagged. (For v0.3.7 it would have printed `PLUGIN_VERSION = "0.3.6"` against a manifest of 0.3.7 — immediate red flag.)

---

## 2. Client vs host plane update asymmetry

**Where each half is loaded, and when.**

- *Client half* (`lib/client.js`): loaded in the **browser**. The browser re-fetches/re-evaluates the client plugin per page load / plugin refresh — so after the v0.3.8 push, the new SVG render toggle appeared and was clickable. The client plane refreshes effectively on reload.
- *Host half* (`lib/index.js`): loaded in the **DSH host Node.js process** at plugin **activation/boot time**. The asset route and its extension whitelist were registered when the plugin was (re)loaded — and the probe header states explicitly: "host NOT restarted since before the SVG whitelist change" (asset-route-probe.txt lines 2–3, release-log.md lines 26–27). The running process is still executing the **old** module instance whose `CONTENT_TYPES` map lacks `svg`.

**How the probes pin staleness to the running host process, not the release:**

- PNG probe → `200 OK, content-type: image/png`: the route handler itself is alive and answering — this is not a missing/unregistered route, nor a dead plugin.
- SVG probe → `404 "unsupported image type"`: the exact failure mode of the whitelist branch rejecting an extension — the *code path that exists and runs* rejects `svg`.
- Disk `lib/index.js` at v0.3.8 **does** whitelist `svg: 'image/svg+xml'` (lib-index-excerpt.js line 12).

If the release were wrong (bad artifact), the disk file would lack `svg`. It doesn't — so the only remaining explanation is that the process is executing an older in-memory copy of the module, registered before the whitelist change. Code-on-disk ≠ code-in-memory.

**What makes a host-plane change effective:** reactivating the plugin / restarting the host process so the new `lib/index.js` is (re)imported and the route re-registered with the updated `CONTENT_TYPES`. Until then, no amount of browser refresh helps, because the 404 is produced host-side.

**Why the usual "plugins hot-update" rule does not hold here:** client-half code is re-fetched and re-evaluated by the browser on refresh, so client-only changes (like the new toggle UI) appear without a restart. But the host half's contributions — here, an HTTP route registered at activation time — live in the Node process's module registry and closure state. Replacing the file on disk does not retroactively change an already-registered route handler or an already-evaluated `CONTENT_TYPES` constant. This is precisely the case where the "just refresh / plugins update live" intuition fails: **host-plane registration is boot-time state, not per-request state.**

---

## 3. Broken-image attribution

**Where the corruption happened.** session-log-excerpt.txt §2–§4 gives three mutually consistent observations:

1. The source file on disk is well-formed XML (`System.Xml` load: no error) and its lines 232–247 are intact.
2. The session log's stored read-result **text** is NOT well-formed — parse error at line 233 col 54 (`Specification mandates value for attribute stro0`).
3. The corruption shape: log payload line 232 = source line 232 truncated at the shared prefix `stro`, spliced with source line 247's tail (`0 0,1 821,730...`); source lines 233–247 are missing.

The excerpt is explicit (§4 closing note): the read tool's result delivered to the caller was clean; the corrupted text is the **model-visible result block persisted into the session log** — i.e. the corruption happened in **result-text assembly, upstream of the plugin**, while the tool-result text was being produced/persisted. A subsequent re-read came back clean, so it is a non-deterministic upstream text-assembly bug — not a property of the file.

**Why the plugin must treat the session payload as untrusted rendering input.** The payload crosses a persistence boundary (session log) and is later replayed to the renderer; nothing guarantees it is byte-identical to the file on disk, and this incident is direct proof it can be spliced/corrupted. Rendering invalid markup — especially SVG, which can carry scripts and structurally exploit malformed input — straight from a stored string without validation turns an upstream data bug into a broken (or worse, unsafe) render. The plugin's correct posture: session-payload text is *untrusted rendering input*, to be validated (well-formedness) before it ever reaches a render surface, and never silently trusted as "the file".

**Why editing/repairing the traced file would have been wrong:** the disk file is well-formed and correct — there is nothing to fix there. "Repairing" it would (a) corrupt a good source file to match one bad copy of its text, (b) destroy the evidence of the upstream bug, and (c) paper over a non-deterministic defect that would keep recurring for other files. The right move is to attribute the corruption to its actual layer (result-text assembly / session persistence upstream of the plugin) and report it upstream.

---

## 4. Defensive render chain for an SVG preview

Render-source order, first match wins, each level justified:

1. **Disk-bytes asset route first.** `GET /<plugin>/asset?path=...` served by the host from the file on disk. Justification: disk is the authoritative copy — proven well-formed here, immune to session-log text corruption, and served with a proper `image/svg+xml` content-type by the (fixed) whitelist. Prefer ground truth over derived copies whenever available.

2. **Session payload only after an XML well-formedness check.** When disk is unavailable (e.g. replaying an archived session) and the payload must be used, first parse it with `DOMParser` (application/xml) and check for a `<parsererror>` document element. Justification: the incident shows the payload can be spliced at a shared prefix into invalid XML; a cheap syntactic gate rejects exactly that (the log payload here fails with "mandates value for attribute stro0") before it can become a broken image or an unsafe parse. Only a well-formed document proceeds to render.

3. **Sandboxed iframe as the last render fallback.** Render the (validated) SVG inside a sandboxed `<iframe sandbox>` with scripts blocked (no `allow-scripts`); SMIL declarative animations still run because they don't require script. Justification: SVG is active content; a sandboxed frame confines any residual risk (embedded event handlers, external references) while preserving the animated preview experience. It is the fallback so that validation failure of *either* source degrades to a contained render rather than an unsafe direct DOM injection.

4. **Explicit error state instead of a silent broken image.** If the asset route fails (e.g. the 404 from §2) AND the payload fails the well-formedness check, show a visible error state: the failure reason (route status / parsererror message), the source that was tried, and the recovery action (e.g. "host restart required for SVG route whitelist", "re-read the file"). Justification: a silent broken image is unauditable — the user can't tell stale-host from corrupt-payload from bad file, which is exactly what made this incident need forensics. An explicit error turns a mystery into a diagnosis and prevents the user from concluding the file itself is broken.

(Operational note: level 1 also depends on §2's fix — the host must be restarted so the whitelist actually includes `svg`; the error state should surface that dependency rather than hide it.)

---

## 5. Forensics method + prevention

**Decoding the session log.** The session log is a concatenated-Zstandard generation file: many independently zstd-compressed frames appended in event order. To recover the exact stored text:

1. Locate the generation file for the session (per-session, monotonic generations; do not modify it — work on a copy).
2. Decompress frame-by-frame: stream through the file, splitting on zstd magic bytes (`28 B5 2F FD`) and decompressing each frame (e.g. `zstd -d` in a streaming loop, the `zstd` library's streaming concat support, or a small script that slices frames at magic boundaries and inflates each) — the concatenation of decoded frames is the ordered event stream.
3. Decode each frame's structured event; find the read-result event whose text block covers the file region in question (here, "payload around line 232").
4. Extract the stored text **verbatim** (byte-exact, no normalization) and diff it against a fresh read of the same region of the disk file — that diff (payload line 232 vs source lines 232–247) *is* the evidence: identical inputs, divergent stored text, clean re-read ⇒ corruption occurred between the tool's delivery and the log's persistence, i.e. in result-text assembly upstream of the plugin. This converts the anecdote ("rendering was broken once") into attributable evidence (a spliced payload line at a shared prefix, non-deterministic).

**Release-checklist items this incident adds:**

- **Version-bump-before-build**: bump `package.json` *before* running the build, always; any build artifact committed for a tag must have been produced after the bump.
- **Grep the shipped bundle for the baked constant**: post-build, pre-push check that the constant inlined into `lib/client.js` (e.g. `PLUGIN_VERSION = "X.Y.Z"`) equals the manifest version; fail the release on mismatch.
- **Per-mirror tag SHA verification**: keep verifying `git ls-remote --tags` on every push mirror (all three agreed here) — necessary for distribution integrity, while understanding it does *not* cover artifact freshness (see §1).
- **Host-plane restart after host-half changes**: when a release touches host code (routes, whitelists, registrations), reactivate/restart the host and probe the new behavior (e.g. the SVG asset route returning 200) before declaring the release done; a refreshed client UI is not evidence the host half took effect.
- **Report the upstream text-corruption bug** (result-text assembly splicing lines at a shared prefix when persisting the model-visible read result to the session log, non-deterministic) to the harness owners with the decoded-log evidence — do **not** paper over it inside the plugin (no "repair the text", no silent fallback that masks the divergence); the plugin's job is validated, fail-loud rendering, not compensating for an upstream persistence defect.

---

## Summary verdicts

| Symptom | Root cause | Layer |
|---|---|---|
| v0.3.7 badge "新版本 v0.3.7 可用" on itself | `PLUGIN_VERSION = "0.3.6"` baked into the bundle at build time; version bumped *after* build; live tag compare beats stale constant | release process (build-order) |
| Toggle visible but SVG Render 404s (PNG 200) | Running host process still executes the pre-v0.3.8 module whose whitelist lacks `svg`; disk `lib/index.js` *does* whitelist svg — needs host restart/re-activation | host plane (boot-time registration) |
| Broken image for traced SVG | Session-log read-result text spliced/corrupted upstream (result-text assembly); disk file well-formed; re-read clean | upstream session persistence |

No files inside the fixture were modified; this report is the only output written.
