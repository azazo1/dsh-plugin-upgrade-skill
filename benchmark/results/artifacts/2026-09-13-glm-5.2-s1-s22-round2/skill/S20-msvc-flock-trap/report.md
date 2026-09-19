# S20 · Windows Install Blocker: `fs-ext` Native Build the Runtime Never Calls — Diagnosis and Fix Plan

**Mode**: A (inspect) — static diagnosis from fixture evidence; fixture untouched.
**Corridor card**: **DSH-0.1.3-A1-03** · breaking: "Windows install fails on the `fs-ext` native build (no MSVC); the runtime never calls `flock` on Windows — pnpm-patch recipe" (references/v0.1.3-alpha.1.md, edge 0.1.2-rc.1 → 0.1.3-alpha.1).

## 1. What exactly fails, and why

- **Failing package**: `fs-ext@2.1.1`, pinned as a runtime dependency (`"fs-ext": "2.1.1"`) of `@deepseek-ai/dsh-session-persistence-jsonl` `0.1.3-alpha.1` (fixture `manifest-excerpt.json`).
- **Install step**: the package's `install` lifecycle script runs `node-gyp configure build` to compile a native C++ addon.
- **Missing toolchain**: the machine has no Visual Studio / Build Tools (no `vswhere.exe`, no VS directory; owner refuses to install — fixture `README.md`). node-gyp's VS locator fails on every probe (`install-error.log`):
  - `gyp ERR! find VS msvs_version not set from command line or npm config`
  - `gyp ERR! find VS VCINSTALLDIR not set, not running in VS Command Prompt`
  - `gyp ERR! find VS could not use PowerShell to find Visual Studio 2017 or newer`
  - `gyp ERR! configure error — Could not find any Visual Studio installation to use`
- **Result**: `pnpm install` exits 1 (`dsh 退出码: 1`), so the upgrade never reaches dependency resolution completion or profile boot. Node and corepack/pnpm themselves are healthy; every earlier dsh upgrade on this machine installed fine — the regression is the newly pinned `fs-ext` in the 0.1.3-alpha.1 cohort.

## 2. Why `pnpm install --ignore-scripts` cannot fix this

`fs-ext` is **statically imported at module top** in `src/lease.ts` (`lease-excerpt.md`):

```ts
import { flock } from 'fs-ext'
import { acquireLockHandleWin32, releaseLockHandleWin32 } from './win32.ts'
```

The fixture note states it explicitly: "the package loader must resolve and load `fs-ext` even on Windows, where the `flock` branch is never taken." `--ignore-scripts` skips the `node-gyp` build, but then the package's entry file `require`s a `fs-ext.node` binary that was never compiled — the module throws on load at runtime when the persistence plugin mounts, and the session-persistence service fails to activate. Skipping the build is not a substitute for a loadable module; the DSH host would boot with a dead required service instead of completing `pnpm install` cleanly. (The A1-03 card names the same trap: "`--ignore-scripts` cannot skip it — the module must exist and load.")

## 3. Which lock path Windows actually takes at runtime, and what that implies

- `lease-excerpt.md` (the write-ownership arbiter contract): POSIX takes a non-blocking `flock(2)` **through `fs-ext`** on `session.lock`; **"Windows holds a named kernel semaphore derived from that path — never a file lock or handle"** and "**Windows has no lock file at all.** Readers never touch the lock."
- `win32-excerpt.ts` implements that Windows branch with pure Win32 API bindings — `CreateSemaphoreW`, `WaitForSingleObject`, `ReleaseSemaphore`, `CloseHandle`, `MoveFileExW` — with the comment "no `flock(2)` is involved on Windows."

**Implication**: the `fs-ext` native addon is **dead code on Windows** — the only symbol consumed from it (`flock`) belongs exclusively to the POSIX branch. The compile failure blocks installation for a binary that would never be executed on this machine. That makes it safe to stub the module on Windows without changing any locking semantics: the real Windows lock path goes through `src/win32.ts` named semaphores, entirely outside `fs-ext`.

## 4. Least-invasive fix plan (no Visual Studio, no upstream changes)

Follow the repository's existing pnpm `patchedDependencies` precedent for native packages (`patches/node-pty@*.patch`, registered in `pnpm-workspace.yaml` — fixture `README.md`). The patch lives in this repository only; upstream sources and the npm registry are untouched. Per DSH-0.1.3-A1-03's migration recipe:

1. **Confirm the platform path** (done, §3): on Windows `lease.ts` routes through `acquireLockHandleWin32` (named kernel semaphore); `flock` is POSIX-only. The native module is dead code on Windows.
2. **Create a pnpm patch for `fs-ext@2.1.1`**:
   - `pnpm patch fs-ext@2.1.1` to obtain an editable copy;
   - **Rewrite the install script** to run `node-gyp configure build` only on non-Windows (e.g. a small guard in the `install` script that no-ops when `process.platform === 'win32'`), so Linux/macOS keep the native build unchanged;
   - **Give the entry a pure-JS `flock` fallback**: on Windows, export a `flock` that warns once and calls back successfully (no-op) instead of loading `fs-ext.node`. This satisfies the static `import { flock } from 'fs-ext'` — the module exists, resolves, and loads — while never reaching the uncompiled binary. Since the Windows branch never calls `flock`, the fallback is unreachable in practice; the warn-once keeps any unexpected call observable rather than silently ignored.
   - `pnpm patch-commit` the edit directory to produce `patches/fs-ext@2.1.1.patch`.
3. **Register the patch** in `pnpm-workspace.yaml`: add `fs-ext@2.1.1: patches/fs-ext@2.1.1.patch` under `patchedDependencies` and ensure `fs-ext` is allowed under the build-scripts policy (`allowBuilds`/onlyBuiltDependencies equivalent), mirroring the `node-pty` rows.
4. **Re-run `pnpm install`** on the Windows machine. pnpm applies the patch to the fetched tarball; no MSVC is ever invoked because the patched install script skips node-gyp on win32.

**Rollback baseline** (recorded before applying): current `pnpm-workspace.yaml`, `patches/` directory listing, and lockfile hash. Recovery = remove the `fs-ext` patch row and patch file and re-run `pnpm install` (only the paths this plan owns).

**Verification** (per the card and skill validation layers):

- Dependency resolution: `pnpm install` completes with exit 0; lockfile diff shows only the patched-dependency entry; full-lockfile scan shows no unexpected cohort changes.
- Static: build/typecheck of the workspace still pass (types come from `@types/fs-ext@2.0.3`, unaffected).
- Runtime: `require('fs-ext')` / `import('fs-ext')` loads without throwing; the `flock` callback path warns once rather than throwing; `dsh web --no-open` cold-boots the profile and answers HTTP 200 with session-persistence services active (no pending required/provided Cordis services).
- Behavior: open/create one session and confirm write-ownership locking works via the Windows named-semaphore path (concurrent access to the same session artifact directory is still serialized).

## 5. Corridor card citation

**`DSH-0.1.3-A1-03`** (full id) in `skills/plugin-upgrade/references/v0.1.3-alpha.1.md`, corridor edge 0.1.2-rc.1 → 0.1.3-alpha.1 — "Windows install fails on the `fs-ext` native build (no MSVC); the runtime never calls `flock` on Windows — pnpm-patch recipe". Type: breaking; applies to profile wrappers/packaging on Windows machines without VS Build Tools; action level: required-if-hit. Its source anchors to git tag `dsh-v0.1.3-alpha.1` (`d347e70`): `packages/session/session-persistence-jsonl/package.json` pins `fs-ext@2.1.1`, `src/lease.ts` statically imports `flock` and routes Windows through `acquireLockHandleWin32`, `src/win32.ts` carries the named-semaphore bindings — exactly matching this fixture.

## Report structure per skill

- **pre-existing**: not collected (Mode A static diagnosis; no baseline suite run — fixture is read-only evidence).
- **Completed**: diagnosis (§1–§3), fix plan (§4), card citation (§5) — all backed by fixture files.
- **Skipped**: no MSVC installation, no upstream modification, no `--ignore-scripts` reliance (rejected with evidence, §2); no runtime execution — the task is static and the fixture must remain unchanged.
- **Pending/residual risk**: the patch must be re-derived if `fs-ext` is ever bumped above 2.1.1; the warn-once `flock` fallback would surface loudly if a future change ever called `flock` on Windows (that would be a behavior change to route through `src/win32.ts` instead); untested on macOS/Linux here (the patch leaves their native build intact by construction).
- **Rollback**: recorded baseline (pnpm-workspace.yaml, patches/, lockfile); recoverable by removing the patch row + file and reinstalling.
- **Recommendations**: upstream, the durable fix is making the `fs-ext` import lazy/dynamic inside the POSIX branch of `lease.ts` (or replacing `flock` with a JS-reachable POSIX lock seam), which would remove the Windows-native-module requirement entirely; note `v0.1.5-alpha.1` later replaced `fs-ext` with `node-addon-system` packaging, so this blocker is specific to the 0.1.3 cohort.
