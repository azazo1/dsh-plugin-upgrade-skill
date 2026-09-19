# S20 · Windows Install Blocker: A Native Build the Runtime Never Calls — Diagnostic Report

Skill: dsh-plugin-upgrade (Mode A · inspect — read-only diagnosis; fixture untouched).

## 1. What exactly fails, and why

- **Failing step**: `pnpm install` exits 1. The install lifecycle script `fs-ext@2.1.1 install: node-gyp configure build` fails during the configure phase (install-error.log).
- **Error**: `gyp ERR! find VS … Error: Could not find any Visual Studio installation to use`, including "You need to install the latest version of Visual Studio ... including the 'Desktop development with C++' workload", and `msvs_version not set` / `VCINSTALLDIR not set` (install-error.log).
- **Missing toolchain**: Visual Studio C++ build toolchain (MSVC) on the Windows 11 machine — confirmed by fixture README.md: "no `vswhere.exe`, no VS directory. The owner refuses to install them."
- **Package that pulls it**: `@deepseek-ai/dsh-session-persistence-jsonl@0.1.3-alpha.1` declares `"fs-ext": "2.1.1"` in `dependencies` (and `@types/fs-ext@2.0.3` in devDependencies) — manifest-excerpt.json. `fs-ext` is a native addon, so its install script invokes node-gyp, which requires MSVC on Windows.

## 2. Why `pnpm install --ignore-scripts` cannot fix this

- Skipping scripts would skip the node-gyp build, but it would also leave `fs-ext` without a compiled (or any loadable) native binary. `fs-ext` is **statically imported at module top** of `src/lease.ts` (`import { flock } from 'fs-ext'`) — lease-excerpt.md states: "the package loader must resolve and load `fs-ext` even on Windows, where the `flock` branch is never taken."
- The corridor card DSH-0.1.3-A1-03 states this explicitly: the static import "means `pnpm install --ignore-scripts` cannot skip it — the module must exist and load." So the service boot fails at module resolution regardless of the skipped build.

## 3. Which lock path Windows actually takes at runtime

- Per lease-excerpt.md, Windows takes a **named kernel semaphore derived from the lock-file path** via `CreateSemaphoreW` — "never a file lock or handle", and "Windows has no lock file at all". `win32-excerpt.ts` confirms `acquireLockHandleWin32`/`releaseLockHandleWin32` wrap the semaphore bindings (`createSemaphoreW`, `waitForSingleObject`, `releaseSemaphore`, `CloseHandle`); "no flock(2) is involved on Windows."
- `flock(2)` through fs-ext is **only the POSIX branch**. Implication: the `fs-ext` native module is **dead code on Windows at runtime** — it must merely exist and load (because of the static top-level import), but its native functionality is never exercised there. This justifies a pure-JS stub on Windows without any behavioral loss.

## 4. Concrete, least-invasive fix plan (no Visual Studio, no upstream changes)

Follows the repository's existing patch precedent — pnpm `patchedDependencies` (fixture README.md: existing `patches/node-pty@*.patch`; "a patch can rewrite a package's install script and entry file, and `pnpm-workspace.yaml` registers it") and card **DSH-0.1.3-A1-03**'s migration recipe:

1. Generate a patch: `pnpm patch fs-ext@2.1.1` → edit the temporary directory → `pnpm patch-commit <dir>`.
2. In the patched package:
   - Rewrite the `install` script so `node-gyp configure build` runs **only on non-Windows** (e.g. `node -e "process.platform!=='win32'&&…"` or an equivalent guard script); on Windows it is a no-op exit 0.
   - Replace the entry file's `flock` implementation with a **pure-JS fallback on Windows**: warn once and no-op the callback path. POSIX keeps the native implementation, so Linux/macOS behavior is unchanged.
3. Register in `pnpm-workspace.yaml`: add the patch under `patchedDependencies` (`fs-ext@2.1.1: patches/fs-ext@2.1.1.patch`) and list `fs-ext` under `allowBuilds` so the guarded build still runs on POSIX machines.
4. Re-run `pnpm install` on the affected machine.

This is repository-local (patches/ + pnpm-workspace.yaml), does not modify the upstream `fs-ext` package or the dsh package's dependency declaration, and never installs Visual Studio — matching the card's explicit directive: "Do not install Visual Studio just for this, do not patch upstream, and do not rely on `--ignore-scripts` alone."

**Verification** (per card DSH-0.1.3-A1-03): `pnpm install` completes with exit 0; `require('fs-ext')` loads and the flock callback path warns once instead of throwing; `dsh web --no-open` boots and answers HTTP 200 (session-persistence-jsonl entry activates, no pending services).

**Rollback**: remove the `patchedDependencies`/`allowBuilds` entries and the `patches/fs-ext@2.1.1.patch` file; `pnpm install` returns to the original graph.

## 5. Corridor card

**DSH-0.1.3-A1-03** · "Windows install fails on the `fs-ext` native build; the runtime never calls `flock` on Windows" — breaking card in corridor `dsh-v0.1.2-rc.1 → dsh-v0.1.3-alpha.1` (references/v0.1.3-alpha.1.md). All fixture evidence (error text, the pinned `fs-ext@2.1.1` dependency, the static `flock` import, and the win32 named-semaphore bindings) matches this card exactly. (For context only: a later corridor, DSH-0.1.5-A1-13, removes `fs-ext` entirely in favor of `@deepseek-ai/node-addon-system`, but the installed cohort here is 0.1.3-alpha.1.)
