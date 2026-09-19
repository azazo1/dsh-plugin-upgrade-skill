# Study artifact integrity and privacy manifests

`paper/scripts/manifest-study-artifacts.py` produces deterministic, privacy-aware manifests for
study artifacts. It is **read-only over the artifact tree**: it opens files for reading and never
writes inside the tree. The only file it writes is an explicit `--out` target, and that target is
excluded from its own manifest.

It is generic tooling shared by the development pilot, the future formal experiment, and judge
calibration. It does not depend on `paper/study-v1` and makes no model calls and no network calls.

## Data boundary

- **Raw artifacts stay local and persistent.** Trial logs, patches, solver outputs, grader packets,
  review metadata, and raw trajectories are working data; they remain on the machine or private
  storage that produced them.
- **Only sanitized summaries and manifests are committed where appropriate.** A committed manifest
  contains relative paths, sizes, and SHA-256 digests — never file bodies and never environment
  metadata. Summaries committed to this repository must be reviewed under the same privacy rules.
- **Never credentials, and never raw private trajectories by default.** API keys, tokens, cookies,
  authorization headers, user-home paths, and unredacted private trajectories must not enter git,
  a manifest, or a distributed candidate archive.
- **The manifest is read-only over the artifact tree.** No command in this tool creates, edits,
  normalizes, or deletes an artifact. `--check` re-reads and reports; it does not repair.

A privacy pass over the existing local `paper/study-v1` working tree already reports username-bearing
paths inside `paper/study-v1/qc/pilot.json` (`/Users/<name>` and `/home/<name>`). Those files are
local QC evidence, not publishable data; do not copy them into committed summaries without
sanitizing them first. This tool reports such findings; it never rewrites them.

## CLI

```bash
# default command
python3 paper/scripts/manifest-study-artifacts.py paper/study-v1 --out /tmp/study-v1.manifest.json

# explicit command, stable alternate root id
python3 paper/scripts/manifest-study-artifacts.py manifest /tmp/candidate --root-id study-v1-candidate

# re-hash a directory and compare against a trusted manifest (non-zero on drift)
python3 paper/scripts/manifest-study-artifacts.py manifest /tmp/candidate --check /tmp/study-v1.manifest.json

# scan content and filenames for secret-like material (non-zero on findings)
python3 paper/scripts/manifest-study-artifacts.py --privacy-check /tmp/candidate

# opt in to recording symlink target text; without it, any symlink is rejected
python3 paper/scripts/manifest-study-artifacts.py manifest /tmp/candidate --allow-symlink
```

Exit codes:

| Code | Meaning |
|---|---|
| 0 | success (for `--check`: no drift; for `--privacy-check`: no findings) |
| 1 | policy violation, unreadable input, or invalid manifest |
| 2 | `--check` drift: `changed`, `missing`, or `extra` entries |
| 3 | `--privacy-check` findings |

## Manifest schema

```json
{
  "schemaVersion": 1,
  "rootId": "study-v1",
  "hashAlgorithm": "sha256",
  "pathOrder": "relative-posix-lexical",
  "symlinkPolicy": {"mode": "reject", "followSymlinks": false, "note": "..."},
  "files": [{"path": "sub/file.md", "type": "file", "size": 1234, "sha256": "..."}],
  "aggregateSha256": "..."
}
```

- **Paths** are relative POSIX paths, lexically sorted, with no leading `./` and no `..`.
- **No environment metadata.** The output contains no timestamp, hostname, username, or working
  directory. `rootId` defaults to a sanitized form of the artifact directory name; it is never a
  timestamp, hostname, or username, and `--root-id` accepts only `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`.
- **Content hashing is streamed** in fixed-size chunks. A whole artifact is never loaded into memory.
- **`aggregateSha256`** is SHA-256 over the canonical sorted entry tuples
  `(path, type, size, sha256, linkTarget?)`, one JSON array per line. It depends only on content and
  relative paths, so an identical tree under a different parent directory yields the same aggregate.
- **Case policy.** Normalized paths are case-preserving and comparisons are exact/case-sensitive:
  `A.txt` and `a.txt` are distinct, and only an exact duplicate is rejected.
- **Self-inclusion rule.** A manifest never includes itself. An `--out` target inside the artifact
  tree, or a `--check` manifest inside the tree, is excluded from the walk; producing a manifest into
  the tree it describes is therefore idempotent.
- **Checking a manifest that recorded symlinks** requires `--allow-symlink` on the check as well;
  otherwise the re-hash refuses the tree and exits 1. A symlink-policy mismatch between manifest and
  check is itself reported as drift.

### Symlinks

The default policy rejects any symbolic link, wherever it appears. With `--allow-symlink` the tool
records **only the link target text** as `linkTarget` (plus `type: "symlink"` and the digest of that
text). It never opens, hashes, or traverses the target, so a link that escapes the root cannot pull
outside content into the manifest. A symlinked directory is recorded but never descended into.

### Rejected paths and files

The manifest command refuses, with exit code 1 and a list of offenders:

- hidden credential material: `.env`, `.env.*`, `.npmrc`, `.netrc`, `.git-credentials`, `id_rsa`,
  `*.pem`, `*.key`, `credentials.json`, `.aws/**`, `.ssh/**` (plus related `id_*`/`.p12`/`.pfx`/`.ppk`);
- credential-looking filenames: `*token*`, `*apikey*`, `*api_key*`, `*api-key*`, `*secret*`,
  `*password*`, `*passwd*` (this applies to filenames, not to ordinary prose in file content);
- path traversal (`..`), absolute paths, Windows drive paths, backslash separators, and empty or
  `.` components;
- duplicate normalized paths;
- non-regular files such as FIFOs, sockets, and devices.

## Privacy scanner

`--privacy-check` scans filenames and decoded text content and reports findings with the relative
path, line number, rule name, kind, and a **redacted** preview. Matched secret text is never echoed
into the report. Symlink targets are scanned as strings but not followed.

Detected at minimum:

| Kind | Examples |
|---|---|
| `api-key-env` | `OPENAI_API_KEY=...`, `DEEPSEEK_API_KEY=...`, `ANTHROPIC_API_KEY=...` |
| `api-key-value` | `sk-...`, `sk-ant-...` |
| `auth-header` | `Authorization:` / `Authorize:` header values |
| `bearer-token` | `Bearer <token>` |
| `token-query` | `?token=`, `&access_token=`, `&api_key=` and related query parameters |
| `dsh-web-token` | `DSH_WEB_TOKEN=...`, `DSH_TOKEN=...`, `dsh-web-token:` |
| `secret-env` | `AWS_SECRET_ACCESS_KEY=...`, `GITHUB_TOKEN=...`, `DB_PASSWORD=...` |
| `user-path` | `/home/<name>`, `/Users/<name>`, `C:\Users\<name>` |
| `credential-filename` / `secret-filename` | the filename rules above |
| `symlink` / `non-regular-file` | recorded links and special files |

Explicit non-findings, covered by tests:

- the ordinary English word **token** in prose (`token budget`, `token counts`);
- benign hex and SHA-looking strings, including `sha256: <64 hex>` and 40-character git commits;
- placeholder user paths written as templates (`/home/<user>`, `/Users/{user}`, `/home/$USER`).

The scanner reads at most 4 MiB per file for content rules and lists any truncated paths under
`truncated`; filenames are always checked. It is a tripwire, not a proof of absence: absence of
findings does not certify a tree as publishable.

## Reproducible commands

```bash
python3 paper/scripts/manifest-study-artifacts.py manifest paper/study-v1 --out /tmp/study-v1.manifest.json
python3 paper/scripts/manifest-study-artifacts.py manifest paper/study-v1 --check /tmp/study-v1.manifest.json
python3 paper/scripts/manifest-study-artifacts.py --privacy-check paper/study-v1
python3 -m unittest discover -s paper/scripts -p 'test_study_artifacts.py'
```

`npm run test:study-artifacts` runs the focused suite and is part of `npm run validate`.

## Non-goals and scientific boundary

- This tool produces **no formal study result**. It runs no solver, no judge, and no model.
- It makes **no paper effect claim**; it only hashes and scans files.
- It **does not mutate benchmark tasks or skills**. It never touches `benchmark/tasks/**`,
  `skills/**`, `benchmark/results/**`, `formalRunAllowed`, or any existed manifested artifact.
- It is not a secret store, a redactor, or a compliance certification. Sanitizing raw trajectories
  and deciding what may be published remain human review steps recorded elsewhere.
