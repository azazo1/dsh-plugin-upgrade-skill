# S5 · Naming Four-State Judgment Report — `acme/greet` (dsh-greet)

**Mode:** read-only review of `fixture/package.json` + `fixture/dsh-plugin.naming.json`.
**Registry status: NOT CHECKED.** This is a closed-book, offline review; no online registry (npm, DSH plugin registry, skill catalog) was queried. Per the brief, absence of findings is **not** evidence of availability — every registry-dependent claim below is reported as **unknown**, never "reserved" or "globally available".

## Verdict legend (four states)

| State | Meaning |
|---|---|
| ❌ compatibility error | Violates the naming policy `dsh-plugin-naming/v1`; must fix before publish |
| ⚠️ collision recommendation | Policy-valid but collision-prone; a prefixed/qualified alternative is recommended |
| ℹ️ needs registry context | Judgment depends on registry/shared-channel ownership that was not (and here cannot be) queried |
| ❓ unknown | Could not be verified offline |

## Surface-by-surface judgment

### 1. Plugin name — `greet` (coordinate `acme/greet`) — ⚠️ collision recommendation
- The coordinate is properly namespaced (`acme/greet`), and the short name `greet` is **policy-valid: no compatibility error**. Under the naming policy, prefixes on the official short name are collision recommendations only, not errors.
- However, `greet` is a highly generic English word with a high prior of prior use by other community plugins. Registry occupancy: **unknown (not checked)**.
- Recommendation: consider a more specific short name or keep the `acme` coordinate prominent in all display surfaces.

### 2. npm package name — `dsh-greet` — ❓ unknown
- `package.json` declares `name: "dsh-greet"`, matching `naming.plugin.packageName` (consistent — no internal mismatch).
- `private: true` is currently set; the fixture README notes this is repo test-material discipline, but it **must be removed before actual publishing** or npm will reject the publish — flag as a pre-publish checklist item, not a naming error.
- Whether `dsh-greet` is free on npm: **unknown (not checked)**. Bare (unscoped) npm names in the `dsh-*` range are also a squatting/consistency concern; a scoped name (e.g. `@acme/dsh-greet`) would be a collision recommendation, not an error.

### 3. Service name — `search` — ⚠️ collision recommendation (NOT a compatibility error)
- Unprefixed, single generic word at the top-level service namespace. This is the classic high-risk surface: `search` is exactly the kind of name a core capability (web/search) or another community plugin would claim.
- Per the policy this is a **warning/recommendation, not an error** — but it is the strongest warning in this manifest. Recommend `acme-greet-search` or dropping the service if it is internal.
- Actual collision with an existing service: **unknown (needs registry context — not checked)**.

### 4. Event name — `web-search/ready` — ℹ️ needs registry context
- The `web-search/` prefix indicates a **shared channel**: the event deliberately lives on another capability's channel rather than a plugin-private one. That is informational, not an error — shared channels are the intended mechanism for cross-capability events.
- Whether `web-search` channel owners sanction `ready` (or it collides with an existing event on that channel): **unknown — requires the registry/shared-channel ownership, which was not queried.** Verify with the `web-search` channel owner before publish.

### 5. Tool — `acme_greet_hi` — ✅ no finding on syntax; ❓ registry unknown
- Namespaced (`acme_greet_`), underscore-delimited, consistent with the command name. No compatibility error. Uniqueness among registered tools: unknown (not checked).

### 6. Command — `acme-greet-hi` — ✅ syntax fine; ❓ registry unknown
- Namespaced with the `acme-greet-` prefix and kebab-case, mirroring the tool. No compatibility error. Global command-collision status: unknown.

### 7. Skill — `greet` — ⚠️ collision recommendation
- Unprefixed single generic word in the shared skill namespace — same risk class as the service name. Recommend `acme-greet` (matching `skills[0]`'s siblings) — recommendation only, not an error. Occupancy: unknown.

### 8. Skill provider — `acme-greet-filesystem` — ✅ syntax fine; ❓ unknown
- Properly prefixed. No compatibility error. Registry availability: unknown.

### 9. Settings namespace — `acme-greet` — ✅ fine; ❓ unknown
- Namespaced, consistent with loader id. No error; uniqueness unverified.

### 10. Route — `/api/plugins/acme-greet/hi` (exact) — ✅ fine; ❓ unknown
- Nested under `/api/plugins/acme-greet/`, so it sits inside the plugin's own slice; collision with other plugins' routes is structurally unlikely. No compatibility error. Global route-table uniqueness: unknown.

### 11. Loader id — `acme-greet` — ✅ fine; ❓ unknown
- Derived mechanically from the coordinate; consistent with settings namespace. No error.

## Consistency checks (offline-verifiable)

- `coordinate` = `namespace + "/" + name` ✓; `packageName` matches package.json `name` ✓; `schemaVersion: 1` / `policy: dsh-plugin-naming/v1` self-declared ✓ (policy content itself not available offline — treated as declared, not verified).
- No internal mismatches found between the manifest and package.json.

## Summary table

| Surface | Value | Verdict |
|---|---|---|
| Plugin short name | `greet` | ⚠️ collision recommendation (valid; generic) |
| Coordinate | `acme/greet` | ✅ namespaced |
| npm package | `dsh-greet` | ❓ unknown (remove `private:true` before publish) |
| Service | `search` | ⚠️ collision recommendation (warning, not error) |
| Event | `web-search/ready` | ℹ️ shared channel — needs registry/owner context |
| Tool | `acme_greet_hi` | ✅ / ❓ registry unknown |
| Command | `acme-greet-hi` | ✅ / ❓ registry unknown |
| Skill | `greet` | ⚠️ collision recommendation |
| Skill provider | `acme-greet-filesystem` | ✅ / ❓ unknown |
| Settings ns | `acme-greet` | ✅ / ❓ unknown |
| Route | `/api/plugins/acme-greet/hi` | ✅ / ❓ unknown |

## Negative-capability statement (explicit)

- **No registry query was performed** (offline, closed-book). Therefore: no name here is claimed "reserved", "available", "free", or "globally unique". All occupancy questions are **unknown / not checked**.
- The fixture README's assertions were treated as fixture commentary, not as registry evidence; the verdicts above were derived from the manifest's own structure plus naming-policy reasoning.
- Nothing under the fixture was modified; no reproduction environment was built.
