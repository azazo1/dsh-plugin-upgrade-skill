# S20 · Windows Install Blocker: A Native Build the Runtime Never Calls — Diagnosis & Fix Plan

Task: S20-msvc-flock-trap · Mode A (inspect, read-only) per the plugin-upgrade skill · Corridor card: **DSH-0.1.3-A1-03**

Machine: Windows 11, no Visual Studio / Build Tools (no `vswhere.exe`), owner refuses to install them; Node + corepack/pnpm working; previous dsh upgrades installed fine (fixture `README.md`).

## 1. What exactly fails, and why

**Failing package:** `fs-ext@2.1.1`, a pinned dependency of `@deepseek-ai/dsh-session-persistence-jsonl` `0.1.3-alpha.1` (fixture `manifest-excerpt.json`:
`"dependencies": { "fs-ext": "2.1.1" }`).

**Failing install step:** the package's `install` lifecycle script runs `node-gyp configure build`, which compiles a C++ native addon.

**Missing toolchain:** node-gyp cannot locate any Visual Studio installation. Fixture `install-error.log`:

```
fs-ext@2.1.1 install: node-gyp configure build
fs-ext@2.1.1 install: gyp ERR! find VS msvs_version not set from command line or npm config
fs-ext@2.1.1 install: gyp ERR! find VS VCINSTALLDIR not set, not running in VS Command Prompt
fs-ext@2.1.1 install: gyp ERR! find VS could not use PowerShell to find Visual Studio 2017 or newer
fs-ext@2.1.1 install: gyp ERR! find VS You need to install the latest version of Visual Studio
fs-ext@2.1.1 install: gyp ERR! find VS including the "Desktop development with C++" workload.
fs-ext@2.1.1 install: gyp ERR! configure error
gyp ERR! stack Error: Could not find any Visual Studio installation to use
pnpm: Command failed with exit code 1: ... pnpm install
```

The whole `pnpm install` exits 1, so the 0.1.3-alpha.1 upgrade cannot complete on this machine. This matches the symptom statement of **DSH-0.1.3-A1-03** verbatim ("`pnpm install` exits 1. `fs-ext@2.1.1` runs its `node-gyp configure build` install script and fails with `gyp ERR! find VS …`").

## 2. Why `pnpm install --ignore-scripts` cannot fix this

`src/lease.ts` imports `flock` from `fs-ext` **statically at module top level** (fixture `lease-excerpt.md`):

```ts
import { flock } from 'fs-ext'
import { acquireLockHandleWin32, releaseLockHandleWin32 } from './win32.ts'
```

The excerpt states it explicitly: "the package loader must resolve and load `fs-ext` even on Windows, where the `flock` branch is never taken."

`--ignore-scripts` would skip the `node-gyp` build (avoiding the MSVC error), but then `fs-ext` has **no built binary at all**. The first time the persistence module is loaded, Node's ESM/CJS loader fails to resolve/load the package and the service dies at boot with a module-not-found / missing-binary error. Skipping the script does not produce a loadable module — the import is static, not lazy or conditional, so there is no runtime path that avoids loading `fs-ext`. (Same conclusion as card DSH-0.1.3-A1-03: "`pnpm install --ignore-scripts` cannot skip it — the module must exist and load.")

## 3. Which lock path Windows actually takes at runtime

Windows **never calls `flock`**. Evidence:

- `lease-excerpt.md`: "Windows holds a named kernel semaphore derived from that path — **never a file lock or handle** … **Windows has no lock file at all.** Readers never touch the lock."
- `win32-excerpt.ts`: the Windows bindings are `CreateSemaphoreW` / `WaitForSingleObject` / `ReleaseSemaphore` / `CloseHandle` (plus `MoveFileExW` for durable publish); "acquireLockHandleWin32 / releaseLockHandleWin32 wrap these named-semaphore primitives; no flock(2) is involved on Windows."

**Implication:** the native `fs-ext` binary is dead code on Windows — `flock` is the POSIX branch only. The module merely has to *resolve and load*; its compiled functionality is never exercised on this platform. Therefore a pure-JS stub that satisfies the static import is functionally equivalent on Windows, which is exactly what the sanctioned patch recipe exploits. (Note: `win32.ts`'s own bindings come from `ffi`-style declarations against `kernel32` primitives listed in the excerpt, not from `fs-ext` — `fs-ext`'s only consumer surface here is the POSIX `flock` branch.)

## 4. Least-invasive fix plan (no Visual Studio, no upstream changes)

Follow the repository's existing **pnpm `patchedDependencies`** precedent (`patches/node-pty@*.patch` is already registered in `pnpm-workspace.yaml` per fixture `README.md`):

1. **Create the patch file** `patches/fs-ext@2.1.1.patch` that:
   - **Rewrites the install script** in `fs-ext`'s `package.json` to run `node-gyp configure build` only on non-Windows platforms (e.g. `node -e "if (process.platform !== 'win32') { /* spawn node-gyp */ }"  || a small install.js guard`). On Windows the script exits 0 without compiling. Linux/macOS keep the full native build unchanged.
   - **Adds a pure-JS entry fallback** so the package loads on Windows without a compiled binary: export `flock` (and whatever else `lease.ts`'s static import surface needs) as a JavaScript function that **warns once and no-ops** instead of throwing. Since Windows never takes the `flock` branch, the stub is never invoked in practice; it only has to exist so the static import resolves.
   Generate it with `pnpm patch fs-ext@2.1.1` → edit → `pnpm patch-commit`, or hand-craft the diff alongside the existing `patches/` directory.

2. **Register it** in `pnpm-workspace.yaml`:
   ```yaml
   patchedDependencies:
     fs-ext@2.1.1: patches/fs-ext@2.1.1.patch
   ```
   and add `fs-ext` to `allowBuilds`/build-script allowlist handling as appropriate for the repo's pnpm version (the card's step 3 names both `patchedDependencies` and `allowBuilds`).

3. **Re-run `pnpm install`.** Windows skips the native build; other platforms are bit-identical to before.

4. **Verify** (per the card's verification recipe):
   - `pnpm install` completes with exit 0;
   - `require('fs-ext')` (or ESM import) loads and the `flock` callback path warns once instead of throwing;
   - `dsh web --no-open` boots and answers HTTP 200 — i.e. the session-persistence service starts, proving the per-session write lock (the Windows named semaphore) works without the native module.

**What this plan deliberately does NOT do** (per card and task constraints): does not install Visual Studio / Build Tools; does not modify the upstream `fs-ext` package or `@deepseek-ai/dsh-session-persistence-jsonl`'s manifest; does not rely on `--ignore-scripts` alone. The patch lives entirely in this repository's `patches/` + `pnpm-workspace.yaml`, matching the established native-dependency precedent.

**Rollback baseline:** remove the `fs-ext` entry from `patchedDependencies` and delete `patches/fs-ext@2.1.1.patch`; the tree returns to the pre-patch state. (Fixture is read-only; nothing in it was touched — static diagnosis only.)

## 5. Corridor card

**`DSH-0.1.3-A1-03`** — "Windows install fails on the `fs-ext` native build; the runtime never calls `flock` on Windows" (0.1.2-rc.1 → 0.1.3-alpha.1 corridor, `references/v0.1.3-alpha.1.md`; source-anchored to tag `dsh-v0.1.3-alpha.1` `d347e70`, single-host Windows field report 2026-09-07). Every element of this case — the pinned `fs-ext 2.1.1` dependency, the static `lease.ts` import, the dead-on-Windows `flock` branch, the named-semaphore lock, and the pnpm-patch remedy — is covered by that card's symptom statement and migration recipe.

## Report structure per skill

- **Pre-existing (baseline)**: not collected — static diagnosis task; fixture read-only, no builds run.
- **Completed**: full diagnosis (§1–§3) and concrete fix plan (§4) with card citation (§5), all backed by fixture evidence.
- **Skipped**: no runtime reproduction or patch execution — the fixture must remain unchanged and the task is a static diagnosis; no other corridor cards intersect (A1-01/02 session-log reading, A1-04 proxy, A1-05/06 session format, A1-07 npm availability, A1-08 client surfaces — none hit by an install-time MSVC failure).
- **Pending/residual risk**: the patch recipe is a single-host field report; verify on the actual machine that `flock`'s no-op stub signature matches everything `@types/fs-ext`-typed call sites expect, and that Linux/macOS CI still builds the native module. If a future dsh corridor replaces `fs-ext` (the 0.1.5-alpha.1 corridor moves to `node-addon-system`), the patch becomes obsolete and should be retired with the dependency.
- **Rollback**: recorded above (remove patch registration + file).
- **Recommendations**: upstream, the durable fix is making the `flock` import conditional/lazy (dynamic `import()` in the POSIX branch) so `fs-ext` need not load on Windows at all; or shipping prebuilt Windows binaries. Neither is in scope for this machine-local fix.
