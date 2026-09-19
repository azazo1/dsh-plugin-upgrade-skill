# S5 · Naming Four-State Judgment Report (acme/greet · dsh-greet)

**Mode:** A · inspect (read-only judgment, no writes, no installs, no registry queries)
**Fixture read (unchanged):** `package.json`, `dsh-plugin.naming.json`, `README.md` under the evidence pack (local adaptation of `/app/fixture/`).
**Declaration under review** (`dsh-plugin.naming.json`): namespace `acme`, name `greet`, coordinate `acme/greet`, packageName `dsh-greet`.

## Executive summary

The declaration is largely **self-consistent and namespaced**. Exactly one surface is a compatibility-shaped problem (the unprefixed service name `search`), and it is a **collision recommendation (warning), not a compatibility error**. The shared event channel `web-search/ready` is informational and needs registry/community context. The npm package name `dsh-greet` cannot be judged "available" or "reserved" without a live registry query — reported as **unknown / not checked**. Per requirement 2, no surface is claimed "globally available" or "reserved" anywhere in this report.

## Per-surface verdicts

| # | Surface | Declared value | Verdict |
|---|---|---|---|
| 1 | Plugin name | `greet` (`acme/greet`, loader id `acme-greet`) | **Compatibility: none.** Namespace-qualified coordinate `acme/greet` and loader id `acme-greet` are consistent with each other and with `packageName` `dsh-greet`. The short name `greet` alone is generic, but within a namespaced coordinate that is a design choice, not an error; see collision note below. |
| 2 | Service name | `search` | **Collision recommendation (warning).** Bare, un-namespaced `search` in a flat service namespace risks colliding with any other plugin exposing `search` (a web capability, a workspace search, etc.). Per the fixture's own README framing this is a warning, not a compatibility error — the manifest schema accepts it; it merely invites a collision. Recommendation: `acme-greet.search` (matching the `acme-greet` prefix used by loader id, commands, and settings). |
| 3 | Event name | `web-search/ready` | **Needs registry context (informational).** The `web-search/` scoped prefix is a **shared** channel vocabulary, not owned by `acme`. `web-search/ready` is a plausible ready-signal on a channel other plugins may also emit or listen to. That is acceptable if intentional (inter-plugin signaling), but the author should confirm against the community naming standard's scoped-event conventions that `web-search/*` is the right shared scope and that emitting `ready` there matches its semantics. Not verifiable offline → informational, "needs registry/community context", not an error. |
| 4 | Tool name | `acme_greet_hi` | **Compatibility: none.** Correctly prefixed with the underscore convention; matches the plugin identity. No offline-detectable problem. |
| 5 | Command name | `acme-greet-hi` | **Compatibility: none.** Correctly prefixed with the hyphen convention; consistent with loader id `acme-greet`. |
| 6 | Skill name | `greet` | **Collision recommendation (weak, warning-level at most).** Unprefixed short skill name; a generic verb-noun likely to be chosen by other plugins. Skill lists are user-facing and selectable, so collisions degrade UX but are not schema violations. Note the asymmetry: the skill-provider row right below it (`acme-greet-filesystem`) *is* prefixed — adopting `acme-greet-greet` (or similar) would be symmetric. |
| 7 | Skill provider | `acme-greet-filesystem` | **Compatibility: none (flag an inconsistency instead).** Well-prefixed. However, the name claims a `filesystem` provider while the plugin is named `greet` — either a copy-paste residue from a filesystem plugin or a deliberate reuse; the author should confirm the identifier matches the actual provider implemented. Not judgeable from the manifest alone → flagged, not a verdict of error. |
| 8 | Settings namespace | `acme-greet` | **Compatibility: none.** Correctly prefixed, consistent with the loader id. |
| 9 | Route | `/api/plugins/acme-greet/hi` (exact) | **Compatibility: none.** Sits under the host's `/api/plugins/<loader-id>/` convention with the correct `acme-greet` prefix; exact-kind route cannot shadow siblings. |
| 10 | npm package | `dsh-greet` v0.1.0 | **Unknown / not checked (registry-dependent).** Whether `dsh-greet` is free, squatted, or conflicts with an existing `dsh-*` community package **cannot be determined offline**, and this report deliberately makes no "available"/"reserved" claim (requirement 2). Also: `private: true` in `package.json` currently blocks npm publish — the fixture README states this is repository test discipline, not part of the brief, so it is recorded here only as a pre-publish consideration for the real release. |

## Cross-cutting consistency observations

- Prefix discipline is inconsistent across three rows: loader id, commands, tools, settings, skill-provider, and route all carry the `acme-greet` / `acme_greet_hi` identity, while **service (`search`) and skill (`greet`) are bare**. Both bare rows are the only collision-recommendation findings; both would be resolved by the same one-line prefix change each.
- No internal contradictions found: `plugin.coordinate` = `namespace + "/" + name`, `loaderIds` = `namespace + "-" + name`, `packageName` = `dsh- + name` are all mutually consistent.
- Manifest metadata (`schemaVersion: 1`, `policy: dsh-plugin-naming/v1`) is well-formed; no unknown fields to flag.

## Explicit non-findings (negative capability / restraint)

- **No "reserved" or "globally available" claims.** No online registry (npm, plugin directory, community standard registry) was queried and none may be inferred. Package-name availability, scope ownership of `acme`, and uniqueness of `greet`, `search`, `web-search/ready` in the wild are all **unknown / not checked**.
- **Not a compatibility error:** the generic short name `greet` (item 1), the shared event channel (item 3), and the `filesystem` wording in the skill-provider id (item 7) — none violates the naming schema; they are recommendations or context questions, and overcalling them errors would be false positives.
- **Not checked (honest gaps):** actual service/event registration behavior at runtime (would require mounting the plugin — out of scope, and building a reproduction environment is forbidden); host-side enforcement rules that might reject bare service names at load; any existing community plugin named `dsh-greet`.

## Recommendations (pre-publish, none applied — read-only review)

1. Rename service `search` → `acme-greet.search` (or another `acme-` prefixed id) to eliminate the only material collision risk.
2. Consider prefixing the skill name for symmetry with the adjacent `acme-greet-filesystem` provider row.
3. Confirm the `acme-greet-filesystem` identifier actually matches the implemented provider.
4. Before the real publish: verify `dsh-greet` availability on npm and confirm the `web-search/` shared-scope convention against the dsh-community-standard — both require online/registry context unavailable in this offline review.
