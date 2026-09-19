# S20 · Windows Install Blocker: fs-ext Native Build the Runtime Never Calls

Static diagnosis from `/app/fixture/` (fixture left completely unchanged). Machine: Windows 11, Node + corepack/pnpm working, **no Visual Studio / Build Tools** (no `vswhere.exe`, no VS directory), and the owner refuses to install them.

## 1. What exactly fails, and why

- **Failing package:** `fs-ext@2.1.1`, declared as a runtime `dependencies` entry of `@deepseek-ai/dsh-session-persistence-jsonl@0.1.3-alpha.1` (`manifest-excerpt.json`).
- **Failing install step:** the package's `install` lifecycle script runs `node-gyp configure build`. The transcript in `install-error.log` shows node-gyp's VS finder failing at every probe: `msvs_version not set`, `VCINSTALLDIR not set`, `could not use PowerShell to find Visual Studio 2017 or newer`, terminating with `Error: Could not find any Visual Studio installation to use`. `fs-ext@2.1.1 install: Failed`, `pnpm install` exits 1, and the dsh upgrade aborts.
- **Missing toolchain:** the MSVC C++ compiler toolchain ("Desktop development with C++" workload). `fs-ext` is a native addon with no prebuilt binary, so its install script compiles from source with node-gyp, which requires MSVC on Windows. The machine has none.

## 2. Why `pnpm install --ignore-scripts` cannot fix this

`--ignore-scripts` only skips lifecycle scripts (it would stop the node-gyp build from running), but it does not remove the package or its code from the module graph. Per `lease-excerpt.md`:

> `flock` is imported statically at module top — the package loader must resolve and load `fs-ext` even on Windows, where the `flock` branch is never taken.

`src/lease.ts` has `import { flock } from 'fs-ext'` at module top level. So even with scripts ignored, the first boot of the session-persistence service would try to `require`/`import` `fs-ext`, whose native `.node` binary was never built — the load fails with a missing-addon error and the service crashes. The dependency is structural (static import must load), not script-level: skipping scripts alone converts an install-time failure into a runtime boot failure.

## 3. Which lock path Windows actually takes at runtime

From `lease-excerpt.md` and `win32-excerpt.ts`:

- POSIX takes a non-blocking `flock(2)` (via `fs-ext`) on `session.lock`.
- **Windows never calls `flock` and never takes a file lock or file handle at all.** It holds a **named kernel semaphore derived from the session path** (`CreateSemaphoreW` / `WaitForSingleObject` / `ReleaseSemaphore` / `CloseHandle`, wrapped by `acquireLockHandleWin32` / `releaseLockHandleWin32` in `src/win32.ts`).

**Implication:** the entire `flock` capability of `fs-ext` is dead code on Windows. The native binary is only needed on POSIX; on Windows any module that merely satisfies the static `import { flock } from 'fs-ext'` — including a pure-JS stub — is functionally equivalent, because the flock branch is never executed and the arbiter is the kernel semaphore instead. This is what makes a no-MSVC fix safe: nothing on the Windows runtime path depends on the compiled addon.

## 4. Least-invasive fix plan (no Visual Studio, no upstream changes)

Follow the repository's existing precedent (per `README.md`): native dependencies are already patched through pnpm's `patchedDependencies` mechanism (see the existing `patches/node-pty@*.patch` registered in `pnpm-workspace.yaml`). A patch can rewrite a package's install script and entry file. Apply the same mechanism to `fs-ext`:

1. **Create the patch:** `pnpm patch fs-ext@2.1.1` → edit the extracted package:
   - **Entry-file fallback:** rewrite `fs-ext`'s main entry so that when the native binding (`binding.node`) is missing, it exports a pure-JS/no-op JavaScript implementation of the `flock` API (throwing or no-op `flock`/`funlock` stubs) instead of throwing on load. The static `import { flock } from 'fs-ext'` then always resolves, on any platform.
   - **Install-script skip on Windows:** make the `install` script (or add a wrapper) skip the `node-gyp configure build` step on `win32` — e.g. gate it on `process.platform !== 'win32'` — so no MSVC is ever required. On Linux/macOS the native build is kept, preserving real `flock(2)` behavior where it is actually used.
2. **Register it:** add `"fs-ext@2.1.1": "patches/fs-ext@2.1.1.patch"` to `patchedDependencies` in `pnpm-workspace.yaml` (or root `package.json` pnpm config), exactly like the node-pty precedent. Commit the patch file.
3. **Result:** `pnpm install` completes on the no-MSVC machine (nothing compiles on win32; the loader still gets a loadable `fs-ext`), and the service boots because the Windows lock path uses the named kernel semaphore from `src/win32.ts` — the stubbed `flock` is never called.
4. **Optional hardening (repo-side, still no upstream change):** if a future refactor is acceptable, changing `src/lease.ts` to a lazy/conditional `await import('fs-ext')` only on POSIX would remove the load-time dependency entirely — but that is not required for the minimal fix and the patch alone suffices.

**Explicitly excluded:** do not install Visual Studio / Build Tools (unnecessary, owner refuses), do not run only `--ignore-scripts` (breaks boot, see §2), do not fork or modify the upstream `fs-ext` package.

## 5. Corridor card

This finding is covered by corridor card **`DSH-0.1.3-A1-03`** (Windows native-dependency install channel: statically imported native module whose platform branch is dead code — fix via pnpm patchedDependencies install-script skip + pure-JS fallback, never via Visual Studio or upstream changes).
