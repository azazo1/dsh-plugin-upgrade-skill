# S20 · Diagnostic Report: Windows Install Blocker (fs-ext native build)

## 1. What exactly fails, and why

- **Failing package:** `fs-ext@2.1.1`, declared as a runtime dependency of `@deepseek-ai/dsh-session-persistence-jsonl` (`manifest-excerpt.json`: `"fs-ext": "2.1.1"` under `dependencies`).
- **Failing install step:** the package's `install` lifecycle script — `install-error.log` shows `fs-ext@2.1.1 install: node-gyp configure build`.
- **Missing toolchain:** node-gyp cannot find any MSVC toolchain. The log records `gyp ERR! find VS could not use PowerShell to find Visual Studio 2017 or newer` and `Error: Could not find any Visual Studio installation to use`. `README.md` confirms the machine constraint: "no Visual Studio / Build Tools installation (no `vswhere.exe`, no VS directory)", and the owner refuses to install them.
- Root cause class: **install-channel failure** — a source-built native addon with no prebuilt binary for this platform, failing during `pnpm install` before any dsh code runs.

## 2. Why `pnpm install --ignore-scripts` cannot fix this

Skipping lifecycle scripts would skip `node-gyp`, but `fs-ext` would then be present on disk with **no built native binding** (`fs-ext.node` never compiled). `lease-excerpt.md` states the blocker directly: `flock` is **imported statically at module top** — "the package loader must resolve and load `fs-ext` even on Windows, where the `flock` branch is never taken." `lease.ts` does `import { flock } from 'fs-ext'` unconditionally, so when the persistence service boots, Node resolves and loads `fs-ext`'s entry point; without a compiled binding the module load throws and the service cannot boot. `--ignore-scripts` therefore only moves the failure from install time to boot time — it does not remove the dependency on a native artifact.

## 3. Which lock path Windows actually takes at runtime

Windows never uses `flock` at all. Per `lease-excerpt.md`: on Windows the arbiter "holds a named kernel semaphore derived from that path — never a file lock or handle," and "**Windows has no lock file at all.** Readers never touch the lock." `win32-excerpt.ts` confirms the implementation: `acquireLockHandleWin32` / `releaseLockHandleWin32` wrap `CreateSemaphoreW` / `WaitForSingleObject` / `ReleaseSemaphore` / `CloseHandle`, and the excerpt states explicitly "no flock(2) is involved on Windows." (The same excerpt shows Windows also replaces the POSIX parent-directory `fsync` publish with a `MoveFileExW`-based durable namespace primitive — further evidence that the Windows path is fully native-API, not fs-ext-based.)

**Implication:** on Windows, `fs-ext`'s entire exported surface is dead code at runtime — the module is loaded only because of the top-level static import. The failing native build produces a binding whose lock function is never called on this platform. That makes the native build genuinely unnecessary on Windows and legitimizes patching the package rather than provisioning a compiler.

## 4. Least-invasive fix plan (no Visual Studio, no upstream changes)

The repository already has the mechanism: `README.md` documents that "the repository already patches native dependencies through pnpm's `patchedDependencies` mechanism (see the existing `patches/node-pty@*.patch` precedent): a patch can rewrite a package's install script and entry file, and `pnpm-workspace.yaml` registers it."

Plan — a single pnpm patch of `fs-ext@2.1.1`:

1. **Generate the patch:** `pnpm patch fs-ext@2.1.1`, edit the checkout, then `pnpm patch-commit <dir>` to produce `patches/fs-ext@2.1.1.patch` and register it under `patchedDependencies` in `pnpm-workspace.yaml` — exactly mirroring the `patches/node-pty@*.patch` precedent.
2. **Patch content — install script:** replace the `install: node-gyp configure build` script in `fs-ext`'s `package.json` with a Windows-safe script. Simplest correct option: make the install script a no-op on Windows (e.g. `node -e "process.exit(process.platform === 'win32' ? 0 : 1)"` guarded so POSIX builds still compile, or shell-condition the node-gyp invocation), since no binding is required on Windows (see §3).
3. **Patch content — entry file:** provide a pure-JS Windows fallback so the static `import { flock } from 'fs-ext'` in `lease.ts` resolves and loads without a compiled `fs-ext.node`. Concretely: patch the entry (`fs-ext.js`) so that when `process.platform === 'win32'` it exports a JS implementation where `flock`/`try-flock`/`funlock` throw a clear `"flock is not supported on Windows; the win32 semaphore lock path is used"` error (never silently succeed — a wrong lock would break cross-process write ownership if ever reached), while keeping the existing `require('./binding')` loading path untouched on POSIX. This keeps the change confined to the patched copy; upstream sources and other platforms are unaffected.
4. **Also patch-safe alternative considered and rejected:** vendoring or forking fs-ext — more invasive than a patch and contradicts the documented patch precedent; replacing `flock` with a pure-JS lock-file library would change lock semantics on POSIX, which is out of scope.
5. **Verification on the target machine:** `pnpm install` completes (install script skipped on Windows); `node -e "import('@deepseek-ai/dsh-session-persistence-jsonl')"` boots the service (static import of `fs-ext` resolves via the JS fallback); confirm POSIX is untouched by the patch (script and binding path unchanged there).

This satisfies the sole goal: `pnpm install` completes on the VS-less Windows machine and the persistence service boots — without Visual Studio and without modifying any upstream dependency.

## 5. Corridor card

The finding is covered by corridor card **`DSH-0.1.3-A1`** — the card line for the `@deepseek-ai/dsh-session-persistence-jsonl@0.1.3-alpha.1` session-persistence component whose `fs-ext` dependency triggers this install-channel blocker (the version pointer `0.1.3` / component `A1` matches the manifest excerpt; the fixture pack does not include the card's fuller suffix beyond the `DSH-0.1.3-A1` prefix given in the task brief).
