# S20 · Windows Install Blocker: A Native Build the Runtime Never Calls — Diagnosis & Fix Plan

Task type: static diagnosis (plugin-upgrade skill, Mode A inspect — read-only). The fixture was read only; nothing inside it was modified.

## Corridor card

**`DSH-0.1.3-A1-03`** — "Windows install fails on the `fs-ext` native build (no MSVC); the runtime never calls `flock` on Windows — pnpm-patch recipe" (references/v0.1.3-alpha.1.md, edge 0.1.2-rc.1 → 0.1.3-alpha.1, type: breaking, action level: required-if-hit, anchored to git tag `dsh-v0.1.3-alpha.1` / `d347e70`). Every finding below matches this card exactly.

## 1. What exactly fails, and why

- **Failing package**: `fs-ext@2.1.1`, a pinned runtime dependency of `@deepseek-ai/dsh-session-persistence-jsonl@0.1.3-alpha.1` (fixture `manifest-excerpt.json`: `"fs-ext": "2.1.1"`, plus `@types/fs-ext@2.0.3` as a devDependency).
- **Failing install step**: `fs-ext`'s `install` lifecycle script runs `node-gyp configure build`. Per `install-error.log`: `gyp ERR! find VS … could not use PowerShell to find Visual Studio 2017 or newer … You need to install the latest version of Visual Studio including the "Desktop development with C++" workload` → `configure error` → `pnpm install` exits 1.
- **Missing toolchain**: the MSVC C++ compiler toolchain (Visual Studio / Build Tools). Per `README.md`, the Windows 11 machine has no VS installation at all (no `vswhere.exe`, no VS directory) and the owner refuses to install one. `fs-ext` is a native C++ addon with no prebuilt binary for this platform, so its build must run node-gyp, which needs MSVC — hence the hard failure.

## 2. Why `pnpm install --ignore-scripts` cannot fix this

Two independent reasons from the fixture:

1. **Static import**: `lease-excerpt.md` shows `import { flock } from 'fs-ext'` at module top level and states explicitly: "the package loader must resolve and load `fs-ext` even on Windows, where the `flock` branch is never taken." `--ignore-scripts` skips the `node-gyp` build but still requires the package's entry to resolve and load at runtime. With the build skipped, `fs-ext` has no built `binding.node`; `require('fs-ext')` / the static ESM import throws when the session-persistence plugin mounts, so the service cannot boot. (Corridor card DSH-0.1.3-A1-03 states the same: "statically imported from `src/lease.ts`, so `--ignore-scripts` cannot skip it — the module must exist and load.")
2. **Blanket side effects**: `--ignore-scripts` also skips every other package's legitimate install scripts, changing behavior far beyond `fs-ext` — it is not a targeted fix in any case.

## 3. Which lock path Windows actually takes at runtime, and what that implies

- `lease-excerpt.md`: "Windows holds a named kernel semaphore derived from that path — never a file lock or handle"; "Windows has no lock file at all. Readers never touch the lock." Lock acquisition on Windows goes through `acquireLockHandleWin32` / `releaseLockHandleWin32` from `./win32.ts`.
- `win32-excerpt.ts`: those wrappers use FFI-style Win32 bindings — `CreateSemaphoreW`, `WaitForSingleObject`, `ReleaseSemaphore`, `CloseHandle` (plus `MoveFileExW` for durable rename) — with the comment "no flock(2) is involved on Windows."
- **Implication**: the native `fs-ext` addon's `flock` is **dead code on Windows**. The only reason `fs-ext` must load there is the static top-level import in `lease.ts`; the compiled `binding.node` is never exercised on the Windows code path. A pure-JS stand-in that satisfies the import surface is sufficient on Windows — exactly what the corridor card's recipe exploits.

## 4. Least-invasive fix plan (no Visual Studio, no upstream changes)

Follow the repository's existing patch precedent for native dependencies (`patches/node-pty@*.patch` registered in `pnpm-workspace.yaml`, per fixture `README.md`):

1. **Generate a local pnpm patch for `fs-ext@2.1.1`**:
   - `pnpm patch fs-ext@2.1.1` → edit the extracted directory → `pnpm patch-commit <dir>` (this writes `patches/fs-ext@2.1.1.patch`; nothing is published or sent upstream).
2. **Patch content** (two coordinated edits inside the patch):
   - **Install script**: rewrite `package.json`'s `install` script to run `node-gyp configure build` only on non-Windows (e.g. `node install-check.js` that skips the build when `process.platform === 'win32'`), so Windows never invokes node-gyp/MSVC. Linux/macOS keep the unchanged native build.
   - **Entry file**: add a pure-JS `flock` fallback so the module loads without a compiled binding: on Windows, `flock(fd, flags, cb)` emits a single one-time warning and is otherwise a no-op (dead-code branch — Windows locking goes through the named kernel semaphore in `win32.ts`), preserving the exported names/signature `lease.ts` statically imports.
3. **Register it** in `pnpm-workspace.yaml`:
   - add `fs-ext@2.1.1: patches/fs-ext@2.1.1.patch` under `patchedDependencies`;
   - ensure `allowBuilds`/build-script allowlist still admits `fs-ext` for non-Windows CI (the patched script itself gates on platform).
4. **Re-run `pnpm install`** on the target machine — no VS, no `--ignore-scripts`, upstream `fs-ext` on npm untouched.

**Why this is least-invasive**: it changes one vendored-patch file plus one registry line in the workspace manifest, mirrors an already-established mechanism in the repo, leaves every other dependency and all upstream packages byte-identical, and is trivially reversible (delete the patch file and its `patchedDependencies` row).

**Verification** (per the card):
- `pnpm install` completes with exit 0 on the no-MSVC Windows machine;
- `require('fs-ext')` loads and the `flock` callback path warns once instead of throwing;
- `dsh web --no-open` boots and answers HTTP 200 — i.e. the session-persistence service starts and the per-session lock path works via `acquireLockHandleWin32`;
- sanity on a POSIX machine/CI: `fs-ext` still builds natively there (patch keeps the Linux/macOS build).

## 5. Corridor citation

- Full card id: **`DSH-0.1.3-A1-03`** (references/v0.1.3-alpha.1.md, corridor 0.1.2-rc.1 → 0.1.3-alpha.1; source anchor: git tag `dsh-v0.1.3-alpha.1`, commit `d347e70`, `packages/session/session-persistence-jsonl`). The card's symptoms, root cause (Windows never calls `flock`), migration recipe (pnpm patch + skip build on Windows + pure-JS `flock` fallback), explicit "do not install Visual Studio, do not patch upstream, do not rely on `--ignore-scripts`" guidance, and verification steps all match the fixture evidence one-to-one.

## Notes per skill reporting format

- **pre-existing / baseline**: not collected (static diagnosis; no repository build run).
- **Completed**: full diagnosis from fixture evidence; corridor card identified; fix plan written. Fixture untouched.
- **Skipped**: no runtime reproduction (task is static; container is not the target Windows-no-MSVC machine).
- **Pending/residual risk**: the patched Windows `flock` is a no-op — acceptable only because `lease.ts` provably routes Windows through the named kernel semaphore; if any future code path calls `flock` on Windows, the warning is the detection signal. Patch must be dropped if upstream `fs-ext` ships a prebuilt Windows binary or the static import becomes dynamic.
- **Rollback**: remove `patches/fs-ext@2.1.1.patch` and its `patchedDependencies` row in `pnpm-workspace.yaml`; re-run `pnpm install`.
