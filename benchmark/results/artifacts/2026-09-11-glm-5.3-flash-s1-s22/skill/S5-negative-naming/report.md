# S5 · Naming Four-State Judgment Report — `acme/greet` (`dsh-greet`)

Mode A (read-only inspection) per the `plugin-upgrade` skill. Fixture reviewed at
`environment/fixture/` (files: `package.json`, `dsh-plugin.naming.json`, `README.md`);
nothing was modified, no environment was built, no network or registry query was made
(closed-book). Skill reference files consulted locally; the skill defers manifest/naming
ownership to the dsh-community-standard, which is not available offline — anything not
decidable from the fixture alone is marked unknown/not-checked.

## Inputs

- `package.json`: `"name": "dsh-greet"`, `"version": "0.1.0"`, `"private": true`.
- `dsh-plugin.naming.json` (`policy: "dsh-plugin-naming/v1"`, `schemaVersion: 1`): plugin
  coordinate `acme/greet`, package `dsh-greet`; declared names:
  pluginNames `["greet"]`, loaderIds `["acme-greet"]`, services `["search"]`,
  tools `["acme_greet_hi"]`, commands `["acme-greet-hi"]`, skills `["greet"]`,
  skillProviders `["acme-greet-filesystem"]`, events `["web-search/ready"]`,
  settingsNamespaces `["acme-greet"]`, route `{ kind: "exact", path: "/api/plugins/acme-greet/hi" }`.

## Per-surface verdicts

State scale: **compatibility error / collision recommendation / needs registry context / unknown**.

| # | Surface | Value | Verdict | Reasoning |
|---|---------|-------|---------|-----------|
| 1 | Plugin name (coordinate) | `acme/greet` with short name `greet` | **No compatibility error** | The short name `greet` is the plugin's own name inside its own `acme` namespace; the coordinate is namespaced (`acme/greet`), and the loader id `acme-greet` and settings namespace `acme-greet` are consistently prefixed with the namespace. Nothing in the declaration is malformed or self-contradictory. This is the valid case — prefixes are only a collision consideration, not an error. |
| 2 | Loader id / settings namespace | `acme-greet` | **No compatibility error** | Namespaced by the plugin namespace `acme`; grammar-conforming (lowercase + `-`). Consistent with the coordinate. |
| 3 | Service name | `search` | **Collision recommendation** (warning, not an error) | `search` is a completely unprefixed, maximally generic name. A Cordis service name is a flat injection key; an unprefixed `search` has a high prior of colliding with a host or other community plugin service of the same name (web capability, search providers, etc.). It still resolves today if nothing else claims it, so it is a recommendation to rename (e.g. `acme-greet.search` or `acme-greet-search`), not a compatibility error. |
| 4 | Tool name | `acme_greet_hi` | **No compatibility error** | Fully namespaced with the plugin coordinate in snake_case. Collision risk negligible. |
| 5 | Command name | `acme-greet-hi` | **No compatibility error** | Fully namespaced (`acme-greet-` prefix); consistent with loader id. |
| 6 | Skill name | `greet` | **Collision recommendation (mild)** | Unprefixed short name. Unlike the plugin short name (which is scoped by the `acme` coordinate), a bare skill id `greet` sits in a shared skill catalog namespace; a generic word like `greet` is plausible for other plugins. Grammar is fine, so this is advisory (consider `acme-greet`), not an error. |
| 7 | Skill provider id | `acme-greet-filesystem` | **Needs registry context** | The id is namespaced, so syntactically fine — but the trailing domain word `filesystem` is a domain the host itself owns (host filesystem capability / filesystem skill providers). Whether a community provider may claim a `*-filesystem` provider id, or whether that suffix is reserved to the host's own filesystem capability, cannot be decided from the fixture. Not-checked: no registry/host catalog query was performed. |
| 8 | Event name | `web-search/ready` | **Needs registry context** (informational) | `web-search/ready` follows the `<domain>/<reason>` naming pattern (the same shape the harness uses for RemoteError domains), but the domain segment `web-search` is **not** the plugin's namespace (`acme`/`acme-greet`). Declaring a `ready` event on a `web-search` domain this plugin does not own looks like emitting on a shared/foreign channel. Whether `web-search/*` is host-owned, reserved, or free for community use cannot be verified offline — reported as informational/needs context, not as an error. |
| 9 | Route | `/api/plugins/acme-greet/hi` (exact) | **No compatibility error** | Embedded under the plugin's own namespaced segment `acme-greet` inside the standard `/api/plugins/` prefix; exact-kind route, no wildcard squatting. Collision risk negligible. |
| 10 | npm package name | `dsh-greet` | **Unknown (registry not checked)** | `dsh-greet` is an **unscoped** npm name (no `@acme/` scope). Whether it is free, taken, or squatted on the registry cannot be determined without a registry query, which this closed-book review does not perform. Note also the fixture is `private: true` (test material, do-not-publish discipline) — publishing would require flipping that deliberately. |

## Explicit non-claims (negative capability / restraint)

- **No "reserved" or "globally available" claims anywhere.** Without an online registry
  query I do not assert that `dsh-greet`, `acme/greet`, `search`, or `web-search/ready`
  are free or taken. All availability questions are reported **unknown / not-checked**.
- **No finding of a compatibility error.** Every declared name is grammar-conforming and,
  where a namespace exists, consistently namespaced; the only negative findings are
  collision *recommendations* (`search`, mild: skill `greet`) and context-dependent items
  (`web-search/ready`, `acme-greet-filesystem`). Restraint here is deliberate: a warning
  is not an error, and an unavailable registry is not evidence of availability.
- Self-consistency (plugin coordinate ↔ loader id ↔ settings namespace ↔ route prefix ↔
  tool prefix) checks out across all ten surfaces; no internal mismatch found.
- Skipped / not performed: registry lookup, host skill/service catalog enumeration,
  publish dry-run, any build or migration. Nothing outside the report was written.

## Recommendations (advisory only)

1. Rename service `search` to a namespaced key (`acme-greet.search` or similar) before publishing.
2. Consider prefixing the skill id `greet` (`acme-greet`).
3. Before publishing, resolve the ownership question for event domain `web-search` and the
   `*-filesystem` skill-provider suffix against the host's owned-domain list and the registry;
   both remain **not-checked** in this report.
4. Verify `dsh-greet` availability on npm at publish time (or switch to a scoped name such as
   `@acme/dsh-greet`), and remove `private: true` deliberately at that point.
