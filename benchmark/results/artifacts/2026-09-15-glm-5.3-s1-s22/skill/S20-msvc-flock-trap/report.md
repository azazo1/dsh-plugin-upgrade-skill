# S20 · Windows Install Blocker: A Native Build the Runtime Never Calls — Diagnosis and Fix Plan

Task type: static diagnosis (skill Mode A · inspect, read-only). Fixture at
`environment/fixture` was read and left unchanged. No files outside the designated
output directory were written.

## 1. What exactly fails, and why

**Failing package:** `fs-ext@2.1.1`, a pinned runtime dependency of
`@deepseek-ai/dsh-session-persistence-jsonl@0.1.3-alpha.1`
(`manifest-excerpt.json`: `"dependencies": { "fs-ext": "2.1.1" }`).

**Failing install step:** `fs-ext`'s `install` lifecycle script runs
`node-gyp configure build` (`install-error.log`). `node-gyp` must compile the
package's C++ addon, which requires an MSVC toolchain.

**Missing toolchain:** the machine has no Visual Studio / Build Tools at all — no
`vswhere.exe`, no VS directory, and the owner refuses to install them
(`README.md`). The log shows the full node-gyp discovery failure chain:

```
gyp ERR! find VS msvs_version not set from command line or npm config
gyp ERR! find VS VCINSTALLDIR not set, not running in VS Command Prompt
gyp ERR! find VS could not use PowerShell to find Visual Studio 2017 or newer
gyp ERR! find VS You need to install the latest version of Visual Studio
gyp ERR! configure error → Failed → pnpm exit code 1
```

So the upgrade to 0.1.3-alpha.1 cannot even complete dependency installation on this
machine, although "every previous dsh upgrade on this machine installed fine"
(`README.md`) — `fs-ext` is newly introduced by this corridor.

## 2. Why `pnpm install --ignore-scripts` cannot fix this

`--ignore-scripts` would skip the `node-gyp` build, but `src/lease.ts` imports
`flock` **statically at module top level**: `import { flock } from 'fs-ext'`
(`lease-excerpt.md`). The package loader must resolve and load `fs-ext` even on
Windows. With scripts ignored, no prebuilt binary is fetched/kept and no
`.node` addon is built, so the import fails at boot (module-not-found / missing
native binary) even though the install command itself would exit 0. The build must
be skipped **and** the import must still load — that is why a patched entry file with
a pure-JS fallback is needed rather than script suppression alone.

## 3. Which lock path Windows actually takes at runtime

Per `lease-excerpt.md` and `win32-excerpt.ts`:

- POSIX: non-blocking `flock(2)` on `session.lock`, through `fs-ext`.
- Windows: **never a file lock** — `acquireLockHandleWin32` /
  `releaseLockHandleWin32` use a **named kernel semaphore derived from the path**
  (`CreateSemaphoreW` / `WaitForSingleObject` / `ReleaseSemaphore` / `CloseHandle`
  bindings in `win32-excerpt.ts`). Readers, searches, and directory removal proceed
  freely while the lock is held; "Windows has no lock file at all."

**Implication:** the `flock` call from `fs-ext` is dead code on Windows. The native
module is only load-required (because of the static top-level import), never
functionally required. A pure-JS stub of `flock` is semantically safe on Windows
because that branch is never taken.

## 4. Least-invasive fix plan (no Visual Studio, no upstream modification)

Follow the repository's existing patch precedent for native dependencies
(`patches/node-pty@*.patch` registered via pnpm's `patchedDependencies`, per
`README.md`):

1. **Generate the patch against `fs-ext@2.1.1` locally** (non-Windows or a machine
   with MSVC, or by editing the extracted tarball without building):
   `pnpm patch fs-ext@2.1.1`.
2. **Rewrite the install script** in the patched `package.json` so `node-gyp`
   runs only on non-Windows (e.g. `node install.js` guarding on
   `process.platform === 'win32'`); Linux/macOS keep the native build unchanged.
3. **Add a pure-JS `flock` fallback to the entry file**: when the native addon is
   absent (Windows), export a `flock` that warns once and no-ops (or returns the
   fd unchanged via callback). This satisfies the static import in
   `src/lease.ts` without a compiled binary.
4. **Register the patch** in `pnpm-workspace.yaml`:
   `patchedDependencies:` entry for `fs-ext@2.1.1` → `patches/fs-ext@2.1.1.patch`,
   plus `allowBuilds` handling for the remaining (non-Windows) build script; commit
   the patch file.
5. **Re-run `pnpm install`** on the target machine. It now completes without any
   C++ toolchain.
6. **Verify** (per the card): `pnpm install` exits 0; `require('fs-ext')` /
   `import('fs-ext')` loads and the `flock` callback path warns once instead of
   throwing; the service boots (`dsh web --no-open` style smoke, HTTP 200) and the
   session persistence provider mounts without pending services.

Explicitly **not** done: installing Visual Studio / Build Tools, patching the
upstream `fs-ext` package or any other upstream dependency, or relying on
`--ignore-scripts` alone.

## 5. Covering corridor card

**`DSH-0.1.3-A1-03`** — "Windows install fails on the `fs-ext` native build; the
runtime never calls `flock` on Windows" (0.1.2→0.1.3-alpha.1 corridor,
`references/v0.1.3-alpha.1.md` in the plugin-upgrade skill). It records exactly this
symptom (pinned `fs-ext` of `@deepseek-ai/dsh-session-persistence-jsonl`, static
import in `src/lease.ts`, `--ignore-scripts` insufficient, Windows named-semaphore
path making the native module dead code), the pnpm-patch recipe, and the
verification steps reproduced in §4. It is classified *breaking*,
*required-if-hit*, packaging/install surface, anchored to tag
`dsh-v0.1.3-alpha.1` (`d347e70`); single-host Windows field report.

## Summary of evidence mapping

| Question | Fixture evidence |
|---|---|
| What fails | `install-error.log` (fs-ext@2.1.1 node-gyp find VS chain), `manifest-excerpt.json` |
| `--ignore-scripts` insufficient | `lease-excerpt.md` static top-level `import { flock } from 'fs-ext'` |
| Windows lock path | `lease-excerpt.md` (named kernel semaphore, no lock file), `win32-excerpt.ts` (CreateSemaphoreW bindings) |
| Fix mechanism | `README.md` (`patchedDependencies` / `patches/node-pty@*.patch` precedent) |
| Corridor card | `DSH-0.1.3-A1-03` |

## Rollback baseline

The fix touches only repository-owned patch files (`patches/fs-ext@2.1.1.patch`,
`pnpm-workspace.yaml`). Rollback = remove the `patchedDependencies` entry and the
patch file, then `pnpm install`. No third-party side effects are introduced.

## Pending/residual risk

- The pure-JS `flock` fallback must warn (not silently succeed) if ever reached on
  Windows; per the current source that branch is unreachable, but the warning
  preserves fail-loud behavior for future code changes.
- Verification of the patched build on an actual MSVC-less Windows 11 machine was
  not performed in this static-diagnosis task; steps in §4.6 are the acceptance
  criteria for the teammate.
