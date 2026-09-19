# H4 — build-cache false-positive diagnosis

## Conclusion

Do not change `src/`. The reported missing export is caused by stale generated
artifacts from the 0.1.1-rc.2 build, not by the migrated source.

## Evidence and actual origin

Before cleanup, the real obsolete reference was:

- `/app/fixture/lib/index.js:2`: `import { resolveSessionPreset } from '@deepseek-ai/dsh-agent-presets'`
- `/app/fixture/lib/index.js:4`: `resolveSessionPreset(ctx.session)`

That generated JavaScript is what asks the bundler to resolve the missing
export. The error's mention of
`node_modules/@deepseek-ai/dsh-agent-presets/src/index.ts` is the dependency
module where the bundler fails to find the export; it is not evidence that the
current plugin source references the symbol.

The stale incremental cache also confirmed the same cause:

- `/app/fixture/lib/tsconfig.tsbuildinfo` listed
  `../node_modules/@deepseek-ai/dsh-agent-presets/src/session.ts`.
- Its `referencedMap` contained `resolveSessionPreset` for both
  `../src/index.ts` and `../lib/index.js`.
- Its `exportedModulesMap` contained `"resolveSessionPreset": true`.
- `semanticDiagPerFile` was empty, so this metadata was stale dependency/build
  state rather than a current TypeScript source diagnostic.

By contrast, `/app/fixture/src/index.ts` contains no occurrence of
`resolveSessionPreset` or `@deepseek-ai/dsh-agent-presets`. It imports only the
type `Context` from `@deepseek-ai/cordis` and calls the current
`ctx.llm.listProviders()` API. The source file was not modified.

## Remediation

1. Keep the migrated `src/` unchanged; do not apply the colleague's proposed
   DSH-0.1.2-A1-21 source rework based on this diagnostic.
2. Remove the stale generated output and incremental cache (`lib/`, including
   `lib/index.js` and `lib/tsconfig.tsbuildinfo`). This cleanup was performed
   in the fixture using its permitted `npm run clean` command.
3. In the real checkout, run a clean build from the current source (for
   example, `npm run clean && npm run build`) after normal dependencies and
   build tooling are available.
4. Before packaging or bundling, verify the regenerated output and cache do
   not contain `resolveSessionPreset` or the old presets-module import. CI
   should either clean generated output before building or correctly invalidate
   the incremental cache when migration changes dependencies.
5. Retain `tsc --noEmit` as the source typecheck, but do not treat its success
   as validation of stale emitted JavaScript or stale `.tsbuildinfo` consumed
   by a later bundling step.

## Cleanup verification

After cleanup, `/app/fixture/lib/` contains no files, and the SHA-256 of
`/app/fixture/src/index.ts` remains
`28701b82eae87cb9234288fa56a0658189d566154fdc036c58ea1503f4eeb81f`.

