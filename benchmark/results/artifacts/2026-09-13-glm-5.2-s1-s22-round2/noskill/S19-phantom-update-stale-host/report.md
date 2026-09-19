# S19 · The Phantom Update, the Stale Host Half, and the Corrupted Payload — Report

Read-only analysis of the evidence pack for `@dsh-external/dsh-file-trace` v0.3.7/v0.3.8
(release session of 2026-09-05). No fixture file was modified.

---

## 1. Phantom self-update root cause

**What the badge is.** The shipped client bundle's self-update check
(`client-bundle-excerpt.js`) compares the newest `git ls-remote --tags` result against a
baked constant:

```js
export const PLUGIN_VERSION = "0.3.6";   // inlined from package.json AT BUILD TIME
```

**Where the constant comes from.** `PLUGIN_VERSION` is a **build-time** constant: tsdown
inlined `package.json`'s `version` field into `lib/client.js` when the bundle was emitted.
It is *never re-read at runtime*. The runtime comparison is against live mirror tags
(`v0.3.7` on all three mirrors), so the badge logic itself is fine — the constant it
compares is frozen at the wrong value.

**The operation-order mistake.** `release-log.md` pins it:

1. 16:22 `pnpm run build` — client bundle emitted **with `version: "0.3.6"` baked in**
2. 16:23 bump `package.json` 0.3.6 → 0.3.7 — **after** the build
3. 16:24 commit (including the already-built, stale `lib/client.js`) and tag `v0.3.7`

So the artifact published as `v0.3.7` contains a plugin that still believes it is
`0.3.6`. `compareSemver("0.3.7", "0.3.6") > 0` → `newerTag` returns `"v0.3.7"` → the
freshly released plugin announces "新版本 v0.3.7 可用" **to itself**.

**Why mirror/tag integrity is irrelevant.** `git-tags.txt` shows the identical tag SHA
(`748b5e5…`) on origin, public, and omdsh. The tag and the mirrors faithfully serve
exactly what was committed and pushed — the *content under the tag* is internally
inconsistent (label says 0.3.7, baked constant says 0.3.6). No mirror skew, no SHA
tampering, no propagation delay can produce a self-referential badge; only a
build/bump ordering error can. Verifying the tag SHA on every mirror verifies the
delivery of the bad artifact, not its correctness.

**Corrected release order** (as applied for v0.3.8):

1. edit source + tests → typecheck + tests green
2. **bump `package.json` version FIRST**
3. build (so the bundle inlines the new version)
4. verify the artifact (see check below)
5. update README refs, commit, tag, push to mirrors, `git ls-remote` verify

**The check that would have caught it before pushing:** grep the shipped bundle for the
baked constant and assert it equals the tag being cut, e.g.

```sh
grep -o 'PLUGIN_VERSION = "[0-9.]*"' lib/client.js   # must print the version being tagged
```

(or a build-verify step asserting `dist`/`lib` contains the new version string and does
NOT contain the previous one). Run it after build, before `git commit`/`git tag`.

---

## 2. Client vs host plane update asymmetry

**Why the toggle appeared but Render 404'd.** The two halves of the plugin load at
different times and through different mechanisms:

- **Client half** (`lib/client.js`) is fetched by the browser and is refreshed by a
  re-fetch / client reload — the Web shell re-loads the client plugin bundle when the
  session updates it. The browser was confirmed refreshed (the new SVG render toggle was
  visible and clickable), so the running client code is v0.3.8.
- **Host half** (`lib/index.js`) is a Node-side Cordis plugin loaded into the DSH host
  process **at boot time**; its asset route (with the `CONTENT_TYPES` extension
  whitelist) was registered when the host last started — which, per the release log,
  predates the SVG-whitelist change. The host was **not restarted** in this session.

**How the probes pin staleness to the RUNNING host, not the release:**

- PNG probe → **200 `image/png`**: the route handler itself is alive and answering —
  the plugin's host half is loaded and functioning; this is not a missing route or a
  dead plugin.
- SVG probe → **404 "unsupported image type"**: the *old* whitelist (without `svg`) is
  rejecting the extension. The 404 body names the whitelist as the rejecter.
- Disk `lib/index.js` **does** contain `svg: 'image/svg+xml'`
  (`lib-index-excerpt.js`): the *released/shipped artifact is correct*.

A live route + correct artifact + missing whitelist entry can only mean the running host
process still holds the code registered at its last boot. The discrepancy is between
disk and memory, not between release and mirror.

**What makes a host-plane change effective:** a host restart (or a full reload of the
host plugin), so the route is re-registered from the new `lib/index.js`. **Why the usual
"plugins hot-update" rule does not hold here:** dynamic/plugin hot-update applies to
*client-side* bundles (re-fetched on reload) and to *re-activated plugin definitions*,
but this plugin's asset route is a boot-time registration inside the long-lived host
Node process; re-activating the session/plugin on the client plane cannot re-execute the
host-half module already loaded in memory. This is the one case where shipping a new
version is not enough — the process that owns the route must be restarted for the new
whitelist to take effect.

---

## 3. Broken-image attribution

**Where the corruption happened.** `session-log-excerpt.txt` shows:

- The **source file on disk is well-formed** XML ( XmlDocument load: no error), and the
  corresponding source lines 232–247 are intact.
- The **session log's stored read-result text** for the same region is corrupt: payload
  line 232 is source line 232 truncated mid-attribute (`…stroke="#dde6ea" stro`) with
  source line 247's tail (`0,1 821,730…`) spliced on at the shared prefix `stro`
  ("stro**ke-width**" vs the arc-flag "…0 **0,1** 821,730"); source lines 233–247 are
  absent. The spliced payload fails XML parsing ("Specification mandates value for
  attribute stro0").
- The corruption sits in the **result-text assembly layer upstream of the plugin** — the
  model-visible result block persisted into the session log — not in the file, not in
  the read tool's typed result, and not in the renderer. A **re-read came back clean**
  (non-deterministic), confirming a transient assembly/persistence fault.

**Why the plugin must treat the session payload as untrusted rendering input.** The
payload crosses a durable/wire-style boundary (session log → plugin renderer) and has
been *observed corrupted in practice*; it is not the file's bytes. Rendering it
unvalidated propagates upstream corruption into a user-visible broken image and can
serve malformed markup (an SVG is XML that can carry scripts/hrefs) to the DOM. The
plugin therefore must validate before render and must never assume payload ≡ disk.

**Why "repairing" the traced file would have been the wrong move.** The file is
well-formed; the defect lives in the logged text of one read. Editing the SVG would (a)
destroy a correct file based on corrupted evidence, (b) mask the real upstream bug so it
never gets reported/fixed, and (c) still leave the session-log corruption free to strike
the next read. The correct action is to fall back to a trusted source (disk bytes via
the asset route) and report the upstream text-corruption bug.

---

## 4. Defensive render chain for the SVG preview

Render-source order, most-trusted first, each level justified:

1. **Disk bytes via the host asset route (first source).** `GET …/asset?path=…` serves
   the file's actual bytes from disk — the authoritative copy, immune to session-log
   payload corruption. This is why the (restarted, svg-whitelisting) host route is the
   primary render source.
2. **Session payload, only after an XML well-formedness check.** When disk is
   unavailable, the logged text can be used — but only behind `DOMParser`
   (MIME `image/svg+xml`) with a `parsererror` check: the corruption incident proves
   this input can be malformed; the check converts a silent broken image into a
   detectable, reportable condition. Reject on any parse error — never "best-effort"
   render malformed XML.
3. **Sandboxed iframe as the last render fallback.** If the payload parses clean but
   must not be inlined into the app DOM (defense against scripts/foreign-object/hrefs in
   untrusted SVG), render it inside `<iframe sandbox>` with scripts blocked — `<script>`
   and event handlers cannot run, while declarative content including **SMIL animations
   still runs** (SMIL is declarative SVG, not script), preserving animated previews
   safely.
4. **Explicit error state instead of a silent broken image.** When every source fails,
   show a named error ("SVG could not be rendered: payload failed XML validation /
   asset route 404") with the reason — a silent `<img>` broken-icon hides the fault,
   invites wrong user action (like editing the file), and forecloses diagnosis.

Each level is justified by a boundary: disk bytes are the file itself; the payload is a
durable-boundary copy that has been observed corrupt; the sandboxed iframe is a
containment boundary for hostile-but-well-formed XML; the error state is the honesty
requirement when no trusted source remains.

---

## 5. Forensics method + prevention

**Decoding the session log.** The session log is a concatenated-Zstandard generation
file: a sequence of independently zstd-compressed frames appended per generation. To
recover the exact stored text frame-by-frame:

1. read the generation file as bytes;
2. walk it with a streaming/multi-frame zstd decoder (e.g. `zstd -d --long` won't do for
   concatenations of independent frames — use a streaming reader that consumes frames
   until EOF, emitting each frame's decompressed output in order);
3. split the concatenated decompressed stream into events/records (the session event
   framing), locate the read-result event for the SVG path, and extract its result-text
   field verbatim — that is the "exact stored text" (`session-log-excerpt.txt` §1);
4. compare against a fresh read of the same file region and record an XML
   well-formedness verdict for both (§3) — the splice shape (missing lines 233–247,
   shared-prefix `stro` join) then becomes reproducible evidence rather than anecdote.

**Release-checklist items this incident adds:**

- **Version-bump-before-build**: bump `package.json` *before* the build step, always;
  make the bump an explicit, ordered checklist item (not bundled with the commit).
- **Grep the shipped bundle for the baked constant**: after build, assert the artifact
  contains `PLUGIN_VERSION = "<new version>"` and not the previous version — this single
  grep would have caught the v0.3.7 stale constant before any push.
- **Per-mirror tag SHA verification** (already done, keep it): `git ls-remote --tags` on
  every mirror and confirm identical SHAs — it verifies delivery integrity (and, as this
  incident shows, delivery integrity alone is necessary but not sufficient).
- **Host-plane restart after host-half changes**: add "restart/reload the host process
  so boot-time route registrations pick up the new `lib/index.js`" to the release
  checklist whenever the host half ships — client refresh alone cannot do it.
- **Report the upstream text-corruption bug** (session-log result-text assembly splicing
  lines at a shared prefix, non-deterministic, re-read clean) to the harness owners with
  the decoded log excerpt as evidence — do **not** paper over it inside the plugin (no
  auto-"repairing" of payloads or files); the plugin's job is validated rendering plus a
  visible error state, while the corruption itself is fixed at its producing layer.

---

## Verdict summary

| Symptom | Root cause | Layer at fault |
|---|---|---|
| v0.3.7 shows "新版本 v0.3.7 可用" | build ran before the version bump; `PLUGIN_VERSION = "0.3.6"` baked into the shipped bundle; mirrors/tags served exactly the (bad) artifact faithfully | release process order |
| Render toggle visible but SVG asset 404, PNG 200, disk lib whitelists svg | host half loads at boot; running host process still holds the pre-SVG whitelist; client half re-fetches on reload | running host process (stale), not the release |
| Traced SVG renders as broken image | session-log read-result text spliced (source line 232 + line 247 tail at shared prefix `stro`, lines 233–247 missing); source file well-formed; re-read clean | upstream result-text assembly / session-log persistence |
