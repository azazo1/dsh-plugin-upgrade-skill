# S5 · Naming Four-State Judgment Report (Read-Only)

Task: judge naming compatibility and registry status for a community plugin about to be published, based only on the read-only fixture (`package.json`, `dsh-plugin.naming.json`, `README.md`). No reproduction environment was built, no file was modified, and no network/registry query was performed.

## Four-state verdict summary

| Surface | Value | Verdict |
|---|---|---|
| Plugin coordinate / official name | `acme/greet` / `greet` | No compatibility error (valid) |
| npm package name | `dsh-greet` | Collision recommendation (scoped-prefix convention) |
| Loader id | `acme-greet` | No compatibility error |
| Service name | `search` | Collision recommendation (unprefixed generic name — warning, not error) |
| Tool name | `acme_greet_hi` | No compatibility error |
| Command name | `acme-greet-hi` | No compatibility error |
| Skill name | `greet` | Collision recommendation (generic, unprefixed) |
| Skill provider | `acme-greet-filesystem` | No compatibility error |
| Event name | `web-search/ready` | Needs registry context (shared-channel style name — informational) |
| Settings namespace | `acme-greet` | No compatibility error |
| Route | `/api/plugins/acme-greet/hi` (exact) | No compatibility error |
| Global registry availability (all names) | — | Unknown / not checked |

## Per-surface reasoning

### Plugin name `greet` (coordinate `acme/greet`)
Verdict: **no compatibility error**. The name is syntactically valid and namespaced by the `acme` namespace in the coordinate, so there is no compatibility error. Prefixes/namespace usage elsewhere in the manifest are collision-mitigation conventions only: failing to add them would at most be a **collision recommendation**, never a hard error. Note that `pluginNames: ["greet"]` itself is an unprefixed generic word — identical in kind to the `search` service case — so it likewise carries a collision *recommendation* (see below), but not an error.

### npm package name `dsh-greet`
Verdict: **collision recommendation**. It matches the declared `packageName` and is unprefixed by any npm scope (`@acme/...`). Unscoped generic package names are a common collision surface on public registries; the conventional recommendation is a scoped name. Whether `dsh-greet` is taken on npm is **unknown — not checked** (no network access; see negative-capability section).

### Loader id `acme-greet`, settings namespace `acme-greet`
Verdict: **no compatibility error**. Both are consistently namespaced with `acme-` and match each other, which is the expected symmetry for parallel values.

### Service name `search`
Verdict: **collision recommendation** (warning, not error). `search` is a highly generic, unprefixed service name on a shared service registry; a service named `search` will very plausibly collide with or shadow other plugins' search services (e.g. a web-search capability). This is exactly the class the policy treats as a warning: unprefixed generic names get a prefix recommendation (e.g. `acme-greet-search` or a namespaced equivalent), but it is not a compatibility *error*. Whether some other plugin already registers `search` is **unknown** without a registry query.

### Tool `acme_greet_hi` and command `acme-greet-hi`
Verdict: **no compatibility error**. Both are prefixed and specific; the tool uses underscores and the command dashes, which is conventional symmetry across the two surfaces.

### Skill name `greet`
Verdict: **collision recommendation**. Like `search`, `greet` is a bare generic word with no namespace prefix, while the skill provider (`acme-greet-filesystem`) *is* prefixed — an unexplained asymmetry. Recommendation: align the skill name with the prefixed convention. Not an error.

### Skill provider `acme-greet-filesystem`
Verdict: **no compatibility error**. Namespaced and specific.

### Event name `web-search/ready`
Verdict: **needs registry context**. The `web-search/ready` form reads as a shared/ambient channel owned by a web-search capability rather than a plugin-private event. Whether emitting it is safe depends on who else declares/consumes that channel in the live registry — information the fixture cannot provide. Treat as informational: verify against the running registry before publishing. Not an error on syntax grounds.

### Route `/api/plugins/acme-greet/hi` (exact)
Verdict: **no compatibility error**. It sits under a plugin-specific prefix (`/api/plugins/acme-greet/...`), so collision risk is low by construction. Absolute global uniqueness of the path is **unknown** without a registry query, but given the prefix this does not rise to a recommendation.

## Negative capability — what was NOT checked

Per requirement 2, **no finding does not mean no problem**, and this is a closed-book, offline review:

- **No online registry query was performed** (no network access permitted). Therefore no claim is made that any name — `dsh-greet`, `greet`, `search`, `acme-greet`, `acme_greet_hi`, `acme-greet-hi`, `acme-greet-filesystem`, `web-search/ready`, or the route — is 'reserved', 'taken', or 'globally available'. Global availability of every identifier is **unknown / not checked**.
- The fixture's `private: true` is repository test discipline; it says nothing about registry state.
- Whether `web-search/ready` is actually emitted/consumed by another installed plugin is **unconfirmed** — it requires live registry context.
- Whether the unprefixed `search` service would concretely collide depends on the target installation's plugin set — **unknown**.

## Method notes

- Read-only analysis of the three fixture files only; nothing under the fixture (or benchmark repo) was modified, created, deleted, or renamed.
- No reproduction environment was built; no dependencies installed; no external services accessed.
- Verdict vocabulary used: compatibility error / collision recommendation / needs registry context / unknown.
