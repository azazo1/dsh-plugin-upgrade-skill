# S20 · Windows Install Blocker: `fs-ext` Native Build the Runtime Never Calls — Diagnosis & Fix Plan

## 1. What exactly fails, and why

- **Failing package**: `fs-ext@2.1.1`, a runtime dependency of `@deepseek-ai/dsh-session-persistence-jsonl@0.1.3-alpha.1` (see `manifest-excerpt.json`: `"dependencies": { "fs-ext": "2.1.1" }`, with `@types/fs-ext@2.0.3` as the matching devDependency).
- **Failing install step**: the package's `install` lifecycle script runs `node-gyp configure build`. The transcript in `install-error.log` shows:
  - `gyp ERR! find VS msvs_version not set from command line or npm config`
  - `gyp ERR! find VS VCINSTALLDIR not set, not running in VS Command Prompt`
  - `gyp ERR! find VS could not use PowerShell to find Visual Studio 2017 or newer`
  - `gyp ERR! configure error … Could not find any Visual Studio installation to use`
  - `pnpm: Command failed with exit code 1` → `dsh 退出码: 1`.
- **Missing toolchain**: the MSVC C++ compiler toolchain. `fs-ext` is a C++ native addon with no prebuilt Windows binary, so node-gyp must compile it, and node-gyp unconditionally requires a Visual Studio installation with the "Desktop development with C++" workload. Per `README.md`, the machine has no VS / Build Tools (no `vswhere.exe`, no VS directory) and the owner refuses to install them. Every previous dsh upgrade installed fine because `fs-ext` is newly introduced as a dependency of the 0.1.3-alpha.1 session-persistence package.

## 2. Why `pnpm install --ignore-scripts` cannot fix this

Skipping lifecycle scripts only avoids the node-gyp build step; it does not make the package loadable. `lease-excerpt.md` states explicitly:

> `flock` is imported statically at module top — the package loader must resolve and load `fs-ext` even on Windows, where the `flock` branch is never taken.

`src/lease.ts` does `import { flock } from 'fs-ext'` as a top-level static import. With `--ignore-scripts`, installation "succeeds" but `fs-ext` ships no built `.node` binary — loading the module throws (`ERR_DLOPEN_FAILED` / missing binding) at boot when the persistence plugin's `lease.ts` is imported. The service would fail at startup instead of the install failing: the failure just moves from install time to module-load time. (It is also not a viable team-wide workaround, since the machine's install must work as a normal `pnpm install` for future upgrades.)

## 3. Which lock path Windows actually takes at runtime — implication for `fs-ext`

- **Windows path**: `lease-excerpt.md`: *"Windows holds a named kernel semaphore derived from that path — never a file lock or handle"* and *"Windows has no lock file at all."* `win32-excerpt.ts` confirms: the Windows lock is implemented via `acquireLockHandleWin32` / `releaseLockHandleWin32` wrapping `CreateSemaphoreW` / `WaitForSingleObject` / `ReleaseSemaphore` / `CloseHandle` bindings, with the comment *"no flock(2) is involved on Windows."*
- **POSIX path**: the non-blocking `flock(2)` on `session.lock`, obtained through `fs-ext`.
- **Implication**: the `flock` export of `fs-ext` is **dead code on Windows** — the branch that calls it is never taken. The native module is required to *load* only because of the static top-level import, not because any Windows code path executes it. Therefore a Windows-targeted, pure-JS substitute for `fs-ext` that merely satisfies the import surface (e.g. a `flock` stub that throws or is never invoked) is behaviorally safe: nothing on Windows ever calls it.

## 4. Least-invasive fix plan (no Visual Studio, no upstream changes)

Follow the repository's existing patch precedent — `README.md` notes the repo already patches native dependencies via pnpm `patchedDependencies` (the `patches/node-pty@*.patch` precedent shows a patch may rewrite a package's install script and entry file, registered in `pnpm-workspace.yaml`).

1. **Create the patch** (one-time, on any machine with the toolchain or by hand):
   `pnpm patch fs-ext@2.1.1` → edit the extracted package:
   - Replace the `install` script in `package.json` so that on `process.platform === 'win32'` it is a no-op (skip node-gyp entirely); keep the native build for non-Windows so POSIX `flock(2)` keeps working.
   - Replace the package entry file with a conditional loader: on Windows, export a pure-JS fallback module (a `flock` export that is never called and therefore may throw `flock is POSIX-only` if invoked); on other platforms, `require`/import the built native binding as before.
   `pnpm patch-commit` produces `patches/fs-ext@2.1.1.patch`.
2. **Register it**: add to `pnpm-workspace.yaml`:
   ```yaml
   patchedDependencies:
     fs-ext@2.1.1: patches/fs-ext@2.1.1.patch
   ``` (mirroring the existing `node-pty` registration).
3. **Re-run `pnpm install` on the Windows machine**: the install script is skipped on win32, no MSVC is needed, and the module loads from the pure-JS fallback.
4. **Runtime safety**: the service boots because the only Windows-relevant native path — the named kernel semaphore lock and `MoveFileExW` durable rename — lives in `src/win32.ts`, independent of `fs-ext`; the stubbed `flock` is unreachable on Windows (§3).
5. **No upstream modification**: the patch lives in this repository's `patches/` directory only; `fs-ext` on npm is untouched, and POSIX/macOS/Linux installs keep the real native build.
6. **Optional belt-and-braces alternative/complement** (still repo-local): make `lease.ts` import `fs-ext` lazily/dynamically only inside the POSIX `flock` branch, so Windows never loads it. The pnpm patch alone suffices and is the smaller change; note this as a follow-up.

**Acceptance**: `pnpm install` exits 0 on the no-MSVC Windows 11 machine; the dsh service boots and acquires/releases the session write lock through the named kernel semaphore (verify two processes contend correctly on one artifact directory).

## 5. Corridor card

**`DSH-0.1.3-A1-03`** — *"breaking: Windows install fails on the `fs-ext` native build (no MSVC); the runtime never calls `flock` on Windows — pnpm-patch recipe"* (corridor `DSH-0.1.3-A1`, v0.1.3-alpha.1 reference). The corridor's troubleshooting table matches this exact symptom (`gyp ERR! find VS` / `fs-ext` build failure, no Visual Studio) and prescribes the same remedy: the repo's pnpm-patch precedent with a win32 node-gyp skip + pure-JS fallback, native kept on non-Windows, and explicitly *not* installing Visual Studio or modifying upstream.

---
*Sources: fixture `install-error.log`, `manifest-excerpt.json`, `lease-excerpt.md`, `win32-excerpt.ts`, `README.md` (read-only; fixture unchanged).*
