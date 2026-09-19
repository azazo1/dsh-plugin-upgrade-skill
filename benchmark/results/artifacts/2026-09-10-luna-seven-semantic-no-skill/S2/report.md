# S2 — Negative scan

## Conclusion

**Result: one hit; compatibility with dsh 0.1.2-alpha.2 is not established.**

The source has a concrete legacy host/API touchpoint in category **#3, internal service/Remote: `apiProxy`**. The other six categories have no hits in this fixture, but those negative results only say that those particular surfaces were not found. They do not prove that the one positive surface is compatible, and they do not replace post-migration verification.

## Seven-category scan

The fixture README is the only local source that names the taxonomy: it explicitly identifies category #3 as “internal service/Remote: `apiProxy`” and says the remaining categories are zero-hit. No separate change-card/corridor catalog is present in the workspace. Accordingly, the table preserves all seven category numbers and does not invent labels for the six categories whose names are not supplied by the fixture.

| Touchpoint category | Result | Evidence |
|---|---|---|
| #1 | **No hit** | No version-sensitive host/API reference attributable to this category appears in `package.json`, `index.js`, `src/session-notes.js`, or `cordis.patch.yml`. |
| #2 | **No hit** | Same complete source scan; there is no category-specific host coupling beyond the `apiProxy` surface called out below. |
| #3 — internal service/Remote: `apiProxy` | **HIT** | `package.json:17` depends on `@deepseek-ai/dsh-host-apiproxy` at `0.0.1-rc.1`; `index.js:3` injects `apiProxy`; `index.js:9` calls `ctx.apiProxy.llm.providers()`. The file comments identify this as the old `0.1.1-rc.2`-style API. |
| #4 | **No hit** | No additional version-sensitive host/API reference is present in the source. |
| #5 | **No hit** | No additional version-sensitive host/API reference is present in the source. |
| #6 | **No hit** | No additional version-sensitive host/API reference is present in the source. |
| #7 | **No hit** | No additional version-sensitive host/API reference is present in the source. |

The apparently suspicious `src/session-notes.js` is not evidence of a session or host touchpoint: it contains only `String`, array slicing, looping, and whitespace formatting (`src/session-notes.js:2-9`). Likewise, `apply`, `inject`, `ctx.effect`, and the patch export are plugin scaffolding/registration; the fixture explicitly classifies the plugin as having only the category #3 migration hit (`README.md:3-5`).

## Change-card mapping

The hit maps to the specific, source-supported card/surface:

- **Card #3 — internal service/Remote: `apiProxy`.** The dependency declaration (`package.json:16-18`), injection (`index.js:3`), and dot-domain call (`index.js:9`) are one connected legacy `apiProxy` touchpoint. This card must be checked and migrated for dsh 0.1.2-alpha.2; the exact replacement contract cannot be inferred from this static source alone.

There are no hit touchpoints to map to cards #1, #2, or #4–#7. That is a scan result, not a compatibility approval. The local inputs do not include the named card text or corridor rules, so this report cannot responsibly assert an exact replacement method for Card #3.

## Can the zero-hit categories establish compatibility?

**No.** Zero hits narrow the migration review: they provide no source evidence that the six categories need changes. They cannot establish that the plugin is compatible because:

1. The remaining `apiProxy` usage is directly runtime-dependent. Whether injection resolves and whether `llm.providers()` still exists with the same shape cannot be determined by a negative scan.
2. The declared host package is an older release (`0.0.1-rc.1`), while the requested target is dsh `0.1.2-alpha.2`; dependency and contract compatibility are therefore still open questions.
3. This is a static, non-executable copy. The scan cannot check module resolution, package/build output, service startup order, isolated-profile behavior, or the actual provider lookup result.

The correct status is **needs migration and verification**, not “roughly compatible.”

## Mandatory verification after migration

After updating the dependency and the Card #3 API contract, perform all of the following:

1. **Build/typecheck** the plugin and verify its exports and package metadata resolve for dsh 0.1.2-alpha.2.
2. **Cold-boot with an isolated profile**, confirming that the plugin loads, its service injection resolves, and no startup/unresolved-service errors occur.
3. **Functional smoke test** the `llm.providers()` behavior (including the failure path), and confirm the patch registration/load path works in the target host.

No files under `/app/fixture/` were modified.
