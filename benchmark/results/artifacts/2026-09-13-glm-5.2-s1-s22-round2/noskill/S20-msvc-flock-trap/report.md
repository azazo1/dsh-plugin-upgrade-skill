# S20 · Windows Install Blocker: `fs-ext` Native Build the Runtime Never Calls

## 1. What exactly fails, and why

- **Package**: `fs-ext@2.1.1`, a pinned runtime dependency of `@deepseek-ai/dsh-session-persistence-jsonl@0.1.3-alpha.1` (`manifest-excerpt.json`: `"dependencies": { "fs-ext": "2.1.1" }`).
- **Install step**: the package's `install` lifecycle script runs `node-gyp configure build`, which requires a native C++ toolchain.
- **Missing toolchain**: the machine has no Visual Studio / Build Tools. `install-error.log` shows `gyp ERR! find VS` — `msvs_version not set`, `VCINSTALLDIR not set`, PowerShell cannot locate VS 2017+, concluding *"You need to install the latest version of Visual Studio including the 'Desktop development with C++' workload"*. `node-gyp configure` errors out, `fs-ext@2.1.1 install: Failed`, and `pnpm install` exits 1.
- Per `README.md`, this machine previously upgraded fine; the breakage is new with the 0.1.3-alpha.1 line, which introduced the `fs-ext` dependency for the JSONL session persistence lease.

## 2. Why `pnpm install --ignore-scripts` cannot fix this

`--ignore-scripts` would skip the failing `node-gyp` build step, so `pnpm install` itself would complete. But `lease-excerpt.md` states:

> `flock` is imported statically at module top — the package loader must resolve and load `fs-ext` even on Windows, where the `flock` branch is never taken.

`src/lease.ts` has `import { flock } from 'fs-ext'` as a top-level static import. Without a build step, `fs-ext` has no loadable entry (its `flock` binding is provided by the compiled native addon). At runtime, importing the persistence package would throw `ERR_MODULE_NOT_FOUND` / "no native build found" and the service would fail to boot. `--ignore-scripts` converts an install-time failure into a boot-time failure; it does not satisfy the requirement that `pnpm install` completes **and** the service boots.

## 3. Which lock path Windows actually takes at runtime

Per `lease-excerpt.md` and `win32-excerpt.ts`:

- POSIX takes a non-blocking `flock(2)` through `fs-ext` on `session.lock`.
- **Windows takes `acquireLockHandleWin32` / `releaseLockHandleWin32** — a **named kernel semaphore derived from the session path** (`CreateSemaphoreW` / `WaitForSingleObject` / `ReleaseSemaphore` FFI-style bindings shown in `win32-excerpt.ts`). The doc is explicit: Windows "**never a file lock or handle**", and "**Windows has no lock file at all.** Readers never touch the lock."

**Implication**: `flock` — the only thing `fs-ext` is used for — is dead code on Windows. The native module must merely *exist and load* (static import resolution); its `flock` implementation is never invoked. A pure-JS stub that loads on Windows is functionally sufficient.

## 4. Least-invasive fix plan (no Visual Studio, no upstream changes)

Follow the repository's existing patch mechanism for native dependencies — `README.md` cites the `patches/node-pty@*.patch` precedent: "a patch can rewrite a package's install script and entry file, and `pnpm-workspace.yaml` registers it."

1. **Generate a pnpm patch for `fs-ext@2.1.1`** (e.g. `pnpm patch fs-ext@2.1.1`), producing `patches/fs-ext@2.1.1.patch` alongside the existing `node-pty` patch.
2. **In the patched package**:
   - **Install script**: rewrite `install` to run `node-gyp configure build` only on non-Windows platforms (e.g. `node -e "if (process.platform === 'win32') process.exit(0)" && node-gyp configure build`, or a small guard script). Linux/macOS keep the real native build unchanged.
   - **Entry file**: give it a pure-JS `flock` fallback so the static `import { flock } from 'fs-ext'` resolves on Windows — a function with the same signature that emits a one-time warning and no-ops (calls back without locking). Since Windows never takes the `flock` branch (§3), a no-op is behavior-preserving there.
3. **Register in `pnpm-workspace.yaml`**: add `fs-ext@2.1.1: patches/fs-ext@2.1.1.patch` under `patchedDependencies`, and list `fs-ext` in `allowBuilds` (per the node-pty precedent) so non-Windows builds still run.
4. **Re-run `pnpm install`** on the Windows machine; it should complete with no MSVC present.
5. **Verify**: `require('fs-ext')` / `import('fs-ext')` loads and the `flock` callback path warns once instead of throwing; `dsh web --no-open` (or the relevant service) boots and answers HTTP 200; on a POSIX machine confirm the native build still compiles and real `flock` locking still works.

Explicitly avoided: installing Visual Studio (owner refuses), forking/patching upstream `fs-ext` in the registry, and `--ignore-scripts` (boot-breaking, per §2).

## 5. Corridor card

**`DSH-0.1.3-A1-03`** — "Windows install fails on the `fs-ext` native build; the runtime never calls `flock` on Windows" (type: breaking; applies to profile wrappers/packaging on Windows machines without VS Build Tools upgrading to 0.1.3-alpha.1; action level: required-if-hit). Its migration recipe matches this plan: confirm the Windows named-semaphore path, add a pnpm patch that gates `node-gyp` to non-Windows and stubs `flock` in pure JS, register it in `pnpm-workspace.yaml`, and re-run `pnpm install`.
