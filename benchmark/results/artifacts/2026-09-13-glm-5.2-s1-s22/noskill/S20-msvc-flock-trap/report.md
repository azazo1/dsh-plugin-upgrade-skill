# S20 · Windows Install Blocker: A Native Build the Runtime Never Calls — Diagnosis & Fix Plan

Static diagnosis from the fixture evidence (`environment/fixture/`, read-only, unchanged). Corridor: dsh-v0.1.2-rc.1 → dsh-v0.1.3-alpha.1.

## 1. What exactly fails, and why

- **Failing package**: `fs-ext@2.1.1`, a pinned direct dependency of `@deepseek-ai/dsh-session-persistence-jsonl@0.1.3-alpha.1` (`manifest-excerpt.json`: `"fs-ext": "2.1.1"` in `dependencies`; `@types/fs-ext@2.0.3` is only a devDependency and never builds).
- **Failing install step**: `fs-ext@2.1.1`'s `install` lifecycle script runs `node-gyp configure build` (`install-error.log` line 3), i.e. it compiles a C++ native addon at install time.
- **Missing toolchain / root cause**: the machine is Windows 11 with **no Visual Studio / Build Tools** (`README.md`: no `vswhere.exe`, no VS directory; owner refuses to install). node-gyp's Visual Studio finder fails on every leg (`install-error.log` lines 4–11): `msvs_version not set`, `VCINSTALLDIR not set, not running in VS Command Prompt`, PowerShell vs-where discovery fails, and the fatal `Could not find any Visual Studio installation to use` (with the advice to install the "Desktop development with C++" workload). The script exits failed, `pnpm install` exits 1 (`install-error.log` lines 12–14).

So: `pnpm install` is blocked by a native compile of a module whose functionality this machine will never execute (see §3).

## 2. Why `pnpm install --ignore-scripts` cannot fix this

`--ignore-scripts` only skips lifecycle scripts (it would skip the `node-gyp configure build` step). But the failure is not merely the build — the module must **exist, resolve, and load** at runtime:

- `lease-excerpt.md` states it explicitly: "`flock` is imported statically at module top — the package loader must resolve and load `fs-ext` even on Windows, where the `flock` branch is never taken." The excerpt shows `import { flock } from 'fs-ext'` at the top of `src/lease.ts`.
- With `--ignore-scripts`, `fs-ext` installs without its compiled `.node` binary. The moment `dsh-session-persistence-jsonl` loads `src/lease.ts`, the static ESM import of `fs-ext` pulls in its entry, which `require`s the missing `.node` addon and throws `ERR_DLOPEN_FAILED` / `MODULE_NOT_FOUND` — the service fails to boot on every profile start, not just at install time.

Therefore `--ignore-scripts` converts an install-time error into a boot-time crash; it is not a fix. (It would also disable install scripts for every other package, which the corridor card explicitly warns against relying on.)

## 3. Which lock path Windows actually takes at runtime

- `lease-excerpt.md`: the arbiter is the kernel. **POSIX** takes a non-blocking `flock(2)` (through `fs-ext`) on `session.lock`. **Windows holds a named kernel semaphore derived from that path — never a file lock or handle**; "Windows has no lock file at all," readers never touch the lock, and readers/searches/directory removal proceed freely while the lock is held.
- `win32-excerpt.ts` carries the actual Windows bindings: `CreateSemaphoreW`, `WaitForSingleObject`, `ReleaseSemaphore`, `CloseHandle`, `GetLastError`, `MoveFileExW` — wrapped by `acquireLockHandleWin32` / `releaseLockHandleWin32`, and its header comment confirms "no flock(2) is involved on Windows."

**Implication**: on Windows, `fs-ext`'s only consumed export (`flock`) is dead code — the Windows lock path never enters the native module. The entire MSVC build requirement is for a binary this platform never calls. Replacing `fs-ext` with a pure-JS loadable stub on Windows is behavior-preserving for this machine.

## 4. Least-invasive fix plan (no Visual Studio, no upstream changes)

Follow the repository's existing native-dependency patch precedent — `README.md` notes the repo already patches native packages via pnpm's `patchedDependencies` (`patches/node-pty@*.patch`: "a patch can rewrite a package's install script and entry file, and `pnpm-workspace.yaml` registers it"). Apply the same mechanism to `fs-ext`:

1. **Confirm the platform path first** (per the corridor recipe): on Windows the lock is the named kernel semaphore via `acquireLockHandleWin32` (`win32-excerpt.ts`); `flock` is only the POSIX branch (`lease-excerpt.md`). The native addon is dead code on Windows.
2. **Create the patch** (`pnpm patch fs-ext@2.1.1`, save as `patches/fs-ext@2.1.1.patch` or `patches/fs-ext@*.patch` matching the repo's naming precedent). The patch edits **our local patched copy only** — upstream npm remains untouched:
   - **Rewrite the install script** in `fs-ext`'s `package.json` to run `node-gyp configure build` only on non-Windows (e.g. `node -e "if (process.platform !== 'win32') process.exit(require('child_process').spawnSync(process.platform === 'win32' ? 'node-gyp.cmd' : 'node-gyp', ['configure','build'], {stdio:'inherit',shell:true}).status"` or a tiny `install.js` guard: `if (process.platform === 'win32') process.exit(0)`). Windows then skips compilation entirely — no MSVC needed.
   - **Give the entry a pure-JS `flock` fallback**: patch `fs-ext`'s entry file so that when the native `.node` addon is absent (Windows), it exports a `flock` that is a loadable no-op which **warns once** instead of throwing — so the static `import { flock } from 'fs-ext'` in `src/lease.ts` resolves and the module loads cleanly. (If `flock` were somehow called on Windows it should fail loudly-but-gracefully, not corrupt locking — but per §3 it is never called.)
   - Linux/macOS keep the native build unchanged.
3. **Register it** in `pnpm-workspace.yaml`:
   ```yaml
   patchedDependencies:
     fs-ext@2.1.1: patches/fs-ext@2.1.1.patch
   ```
   and allow the remaining (non-Windows or guarded) build via pnpm's build-allowlist (`allowBuilds`/`onlyBuiltDependencies` entry for `fs-ext` as the repo's `node-pty` precedent registers patched native packages).
4. **Re-run `pnpm install`** on the Windows machine — it now completes with no compiler invoked.
5. **Do not** install Visual Studio for this, do not patch upstream packages at the registry, and do not rely on `--ignore-scripts` alone (see §2).

**Verification** (per the corridor recipe): `pnpm install` completes; `require('fs-ext')` / `import('fs-ext')` loads on Windows and the `flock` callback path warns once instead of throwing; `dsh web --no-open` boots and answers HTTP 200; on a Linux/macOS CI machine the native build still compiles and `flock` still works.

## 5. Corridor card

**`DSH-0.1.3-A1-03`** — "Windows install fails on the `fs-ext` native build (no MSVC); the runtime never calls `flock` on Windows — pnpm-patch recipe" (type: breaking, packaging/install surface, required-if-hit) in the dsh-v0.1.2-rc.1 → dsh-v0.1.3-alpha.1 corridor (`references/v0.1.3-alpha.1.md`). The card matches this fixture exactly: the `fs-ext@2.1.1` pin in `dsh-session-persistence-jsonl`, the `gyp ERR! find VS` transcript, the static `flock` import in `src/lease.ts`, the named-kernel-semaphore Windows bindings in `src/win32.ts`, and the same pnpm-`patchedDependencies` remedy used in §4.

## Fixture integrity

No file under `environment/fixture/` (or anywhere in the benchmark repository) was read-modified, created, deleted, or renamed; the only write was this report in the designated output directory.
