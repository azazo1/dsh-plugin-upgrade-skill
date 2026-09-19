# S5 · Naming Four-State Judgment Report (Read-Only Review)

Reviewed surfaces: fixture directory 'dsh-plugin-upgrade-skill/benchmark/tasks/S5-negative-naming/environment/fixture' — 'package.json' and 'dsh-plugin.naming.json' (schemaVersion 1, policy 'dsh-plugin-naming/v1'). Read-only; nothing under the fixture was modified, and no reproduction environment was built.

## Judgment states used

Per the brief, every surface gets exactly one of: **compatibility error** (violates a naming rule determinable from the manifest alone) · **collision recommendation** (syntactically valid but generic enough that a prefix is recommended to avoid collisions) · **needs registry context** (validity depends on live registry state that was not queried) · **unknown** (cannot be verified closed-book).

**Global caveat (negative capability):** no online registry query was performed — this is a closed-book, offline review. Therefore no surface here can be claimed 'reserved' or 'globally available'. Any statement about uniqueness in any registry is **unknown / not checked**, reported as such rather than guessed.

## Per-surface verdicts

| # | Surface | Declared value | Verdict | Reasoning |
|---|---------|----------------|---------|-----------|
| 1 | Plugin name (official short name) | 'greet' | **No compatibility error; collision recommendation (prefix advised); registry availability unknown** | 'greet' is syntactically valid as a short name — the naming policy treats a missing namespace prefix as a recommendation, not an error. However 'greet' is a highly generic English word likely to collide with other community plugins; the manifest already carries namespace 'acme' and loaderId 'acme-greet', so the prefixed coordinate 'acme/greet' is the safer public identity. Whether the bare short name is already taken in the registry is **not checked (unknown)**. |
| 2 | npm package name | 'dsh-greet' (v0.1.0, private: true) | **Needs registry context — availability unknown; packaging note** | 'dsh-greet' follows the dsh-* convention and has no in-manifest conflict, but npm-name availability can only be known via a registry query → unknown. Also 'private: true' will make npm publish refuse; that is a packaging fact, not a naming compatibility error, but must be flipped deliberately before publishing. |
| 3 | Loader id | 'acme-greet' | **No compatibility error; low collision risk (namespaced)** | Derived from namespace + name; prefixed, so collision likelihood is reduced. Registry uniqueness: unknown / not checked. |
| 4 | Service name | 'search' | **Collision recommendation (warning, not an error)** | Unprefixed generic noun. 'search' is exactly the kind of name other plugins (and possibly the platform's own capability seams) are likely to claim, risking Service collisions when composed in one runtime. Recommend 'acme-greet/search' or an 'acme-search' style name. Not a compatibility error per the policy. |
| 5 | Tool name | 'acme_greet_hi' | **No compatibility error; low collision risk** | Namespaced with the 'acme_greet_' prefix; conservative and unlikely to collide. Global uniqueness: unknown / not checked. |
| 6 | Command name | 'acme-greet-hi' | **No compatibility error; low collision risk** | Prefixed consistently with the loader id. Registry uniqueness: unknown / not checked. |
| 7 | Skill name | 'greet' | **Collision recommendation** | Same generic-word concern as the plugin short name; skill names typically share a flat catalog namespace, so an unprefixed 'greet' is likely to collide with other greeting-style skills. Recommend 'acme-greet'. Not an error. Availability: unknown. |
| 8 | Skill provider | 'acme-greet-filesystem' | **No compatibility error; low collision risk** | Fully namespaced. Registry uniqueness: unknown / not checked. |
| 9 | Event name | 'web-search/ready' | **Informational — shared-channel usage; needs registry context** | 'web-search/ready' reads as an event on the shared 'web-search' domain rather than a plugin-owned 'acme-greet/*' event. That is informational: it may be intentional (extending a shared channel), but if it is this plugin's own event it should live under its own namespace. Whether 'web-search/ready' is an established shared channel is **unknown / not checked offline**. |
| 10 | Settings namespace | 'acme-greet' | **No compatibility error; low collision risk** | Namespaced; consistent with the loader id. Uniqueness: unknown. |
| 11 | Route | '/api/plugins/acme-greet/hi' (exact) | **No compatibility error; low collision risk** | The prefixed 'acme-greet' path segment keeps it out of generic route space. Whether the exact path is already served is unknown / not checked. |

## Aggregate judgment

- **Compatibility errors: 0.** Nothing in the manifest violates a deterministic naming rule checkable from the manifest alone.
- **Collision recommendations: 3** — plugin short name 'greet', service 'search', skill 'greet' (the unprefixed/generic surfaces). The service name 'search' is the highest-priority fix: unprefixed capability-level names collide at runtime composition, not just in a catalog.
- **Needs registry context / unknown: all uniqueness claims.** No online registry query was performed, so **no surface — including the npm package name 'dsh-greet' — may be reported as 'reserved' or 'globally available'.** That is an honest unknown, not an implicit pass.

## Non-goals honored

- Fixture left byte-identical; only read operations were used against it.
- No reproduction environment built; no dependencies installed; no network or external services accessed; no skill, verifier, or reference material modified.
- Output written solely to the designated report directory.
