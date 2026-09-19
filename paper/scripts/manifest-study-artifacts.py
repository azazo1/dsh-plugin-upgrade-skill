#!/usr/bin/env python3
"""Deterministic, read-only artifact integrity and privacy manifests for study artifacts.

Design contract
---------------
* The tool is read-only over the artifact tree. The only file it ever writes is
  the ``--out`` target, and that target is excluded from its own manifest
  (self-inclusion rule).
* Manifest paths are relative POSIX paths, lexically sorted, and carry no
  timestamp, hostname, username, or working directory.
* ``rootId`` is derived from the artifact directory name or an explicit
  ``--root-id``; it is never a timestamp, hostname, or username.
* File content is hashed with a streaming SHA-256 reader; no artifact is ever
  loaded into memory as a whole.
* Symlinks are rejected by default. With ``--allow-symlink`` only the link
  target *text* is recorded; targets are never opened, hashed, or traversed, so
  a link escaping the root cannot pull outside content into the manifest.

Standard library only. No model calls, no network.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

SCHEMA_VERSION = 1
CHUNK_SIZE = 1 << 20
PRIVACY_SCAN_MAX_BYTES = 4 << 20
AGGREGATE_FIELDS = ('path', 'type', 'size', 'sha256', 'linkTarget')

# Hidden credential material: refused even when it is an ordinary readable file.
CREDENTIAL_BASENAMES = frozenset({
    '.env', '.npmrc', '.netrc', '.git-credentials', 'credentials.json',
    'id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519',
})
CREDENTIAL_DIRS = frozenset({'.aws', '.ssh'})
CREDENTIAL_SUFFIXES = ('.pem', '.key', '.p12', '.pfx', '.ppk')
SECRET_NAME_MARKERS = ('token', 'apikey', 'api_key', 'api-key', 'secret', 'password', 'passwd')

_DRIVE = re.compile(r'^[A-Za-z]:')
_ROOT_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
_SHA256_HEX = re.compile(r'^[0-9a-f]{64}$')


class ArtifactError(ValueError):
    """Unsafe, unreadable, or policy-violating artifact tree."""


# --------------------------------------------------------------------------- paths

def normalize_path(path):
    """Validate and return a relative POSIX artifact path.

    Absolute paths, Windows drive paths, backslash separators, NUL bytes,
    ``.``/``..`` components, empty components, and padded names are rejected.
    Comparison stays case-sensitive and case-preserving: ``A.txt`` and ``a.txt``
    are distinct paths, and only an exact duplicate is a duplicate.
    """
    if not isinstance(path, str):
        raise ArtifactError(f'path must be a string: {path!r}')
    if path == '' or path != path.strip():
        raise ArtifactError(f'empty or whitespace-padded path rejected: {path!r}')
    if '\x00' in path:
        raise ArtifactError(f'NUL byte in path rejected: {path!r}')
    if '\\' in path:
        raise ArtifactError(f'backslash separators are not portable POSIX: {path!r}')
    if path.startswith('/') or _DRIVE.match(path):
        raise ArtifactError(f'absolute path rejected: {path!r}')
    for part in path.split('/'):
        if part in ('', '.', '..'):
            raise ArtifactError(f'unsafe path component {part!r} in {path!r}')
    return path


def assert_unique_paths(paths):
    """Reject duplicate NORMALIZED paths (exact, case-sensitive comparison)."""
    seen = set()
    for path in paths:
        normalized = normalize_path(path)
        if normalized in seen:
            raise ArtifactError(f'duplicate normalized path: {normalized!r}')
        seen.add(normalized)
    return sorted(seen)


def credential_reasons(relative_path):
    """Policy reasons a manifest must refuse this path; empty tuple when clean."""
    parts = relative_path.split('/')
    base = parts[-1].lower()
    reasons = []
    if base == '.env' or base.startswith('.env.'):
        reasons.append('dotenv-file')
    if base in CREDENTIAL_BASENAMES:
        reasons.append('credential-file')
    if base.endswith(CREDENTIAL_SUFFIXES):
        reasons.append('key-material')
    if any(part in CREDENTIAL_DIRS for part in parts):
        reasons.append('credential-directory')
    if any(marker in base for marker in SECRET_NAME_MARKERS):
        reasons.append('secret-like-name')
    return tuple(reasons)


def default_root_id(root):
    """Deterministic id from the artifact directory name; never time/host/user."""
    name = os.path.basename(os.path.normpath(str(root)))
    name = re.sub(r'[^A-Za-z0-9._-]+', '-', name).strip('.-')
    return name or 'root'


def validate_root_id(value):
    if not isinstance(value, str) or value in ('.', '..') or not _ROOT_ID.match(value):
        raise ArtifactError(
            'root id must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ '
            f'(no whitespace, separators, or absolute paths): {value!r}')
    return value


def _is_within(path, root):
    path, root = os.path.abspath(path), os.path.abspath(root)
    return path == root or path.startswith(root + os.sep)


# --------------------------------------------------------------------------- hashing

def file_digest(path, chunk_size=CHUNK_SIZE):
    """Stream a file through SHA-256; never load the whole file into memory."""
    digest = hashlib.sha256()
    size = 0
    try:
        with open(path, 'rb') as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                size += len(chunk)
                digest.update(chunk)
    except OSError as exc:
        raise ArtifactError(f'unreadable file {path}: {exc.strerror or exc}') from exc
    return digest.hexdigest(), size


def sha256_stream(path, chunk_size=CHUNK_SIZE):
    return file_digest(path, chunk_size=chunk_size)[0]


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def aggregate_sha256(entries):
    """Stable digest over the sorted entry tuples (content, no rootId/policy)."""
    digest = hashlib.sha256()
    for entry in sorted(entries, key=lambda item: item['path']):
        canonical = [entry.get(field, '') for field in AGGREGATE_FIELDS]
        digest.update((json.dumps(canonical, ensure_ascii=False) + '\n').encode('utf-8'))
    return digest.hexdigest()


# --------------------------------------------------------------------------- traversal

def _walk(root, relative, entries, allow_symlink, exclude, problems, enforce, hash_files):
    try:
        with os.scandir(root) as scan:
            children = sorted(scan, key=lambda item: item.name)
    except OSError as exc:
        raise ArtifactError(f'unreadable directory {relative or "."}: {exc.strerror or exc}') from exc
    for child in children:
        relpath = f'{relative}/{child.name}' if relative else child.name
        if os.path.abspath(child.path) in exclude:
            continue
        reasons = credential_reasons(relpath)
        if enforce and reasons:
            problems.append(f'{relpath} ({", ".join(reasons)})')
            continue
        if child.is_symlink():
            target = os.readlink(child.path)
            payload = target.encode('utf-8', 'surrogateescape')
            if not allow_symlink and enforce:
                problems.append(f'{relpath} -> {target} (symlink rejected; pass --allow-symlink to record targets)')
                continue
            entries.append({'path': relpath, 'type': 'symlink', 'size': len(payload),
                            'sha256': sha256_bytes(payload), 'linkTarget': target})
            continue
        if child.is_dir(follow_symlinks=False):
            _walk(child.path, relpath, entries, allow_symlink, exclude, problems, enforce, hash_files)
            continue
        try:
            mode = child.stat(follow_symlinks=False).st_mode
        except OSError as exc:
            raise ArtifactError(f'unreadable entry {relpath}: {exc.strerror or exc}') from exc
        if stat.S_ISREG(mode):
            if hash_files:
                digest, size = file_digest(child.path)
            else:
                digest, size = '', child.stat(follow_symlinks=False).st_size
            entries.append({'path': relpath, 'type': 'file', 'size': size, 'sha256': digest})
            continue
        kind = ('fifo' if stat.S_ISFIFO(mode) else 'socket' if stat.S_ISSOCK(mode)
                else 'device' if stat.S_ISBLK(mode) or stat.S_ISCHR(mode) else 'special')
        if enforce:
            problems.append(f'{relpath} ({kind}; only regular files may be manifested)')
        else:
            entries.append({'path': relpath, 'type': 'other', 'special': kind})


def iter_entries(root, allow_symlink=False, exclude=(), enforce=True, hash_files=True):
    """Deterministic, lexically sorted entries under ``root``.

    ``enforce=True`` raises on policy violations (credential/secret paths,
    symlinks without opt-in, non-regular files). ``enforce=False`` records them
    instead, which the privacy scanner needs in order to report them.
    """
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise ArtifactError(f'not a directory: {root}')
    exclude = {os.path.abspath(path) for path in exclude}
    entries = []
    problems = []
    _walk(root, '', entries, allow_symlink, exclude, problems, enforce, hash_files)
    if problems:
        raise ArtifactError('artifact tree violates manifest policy:\n- ' + '\n- '.join(problems))
    assert_unique_paths([entry['path'] for entry in entries])
    entries.sort(key=lambda entry: entry['path'])
    return entries


# --------------------------------------------------------------------------- manifest

def symlink_policy(allow_symlink):
    return {
        'mode': 'record-target-only' if allow_symlink else 'reject',
        'followSymlinks': False,
        'note': ('Symlinks are rejected by default. With --allow-symlink only the link target text is '
                 'recorded; targets are never opened, hashed, or traversed, so targets outside the root '
                 'cannot leak content into the manifest.'),
    }


def build_manifest(root, root_id=None, allow_symlink=False, exclude=()):
    """Build the deterministic manifest object for ``root``."""
    root_id = validate_root_id(root_id) if root_id else validate_root_id(default_root_id(root))
    entries = iter_entries(root, allow_symlink=allow_symlink, exclude=exclude)
    return {
        'schemaVersion': SCHEMA_VERSION,
        'rootId': root_id,
        'hashAlgorithm': 'sha256',
        'pathOrder': 'relative-posix-lexical',
        'symlinkPolicy': symlink_policy(allow_symlink),
        'files': entries,
        'aggregateSha256': aggregate_sha256(entries),
    }


def load_manifest(path):
    """Read and validate a manifest before trusting any of its fields."""
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError(f'unreadable manifest {path}: {exc}') from exc
    if not isinstance(data, dict) or data.get('schemaVersion') != SCHEMA_VERSION:
        raise ArtifactError(f'unsupported manifest schemaVersion: {data.get("schemaVersion")!r}')
    files = data.get('files')
    if not isinstance(files, list):
        raise ArtifactError('manifest files must be a list')
    paths = []
    for record in files:
        if not isinstance(record, dict):
            raise ArtifactError(f'manifest file record must be an object: {record!r}')
        paths.append(normalize_path(record.get('path')))
        if record.get('type', 'file') == 'file':
            size, digest = record.get('size'), record.get('sha256')
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise ArtifactError(f'invalid size for {record.get("path")!r}: {size!r}')
            if not isinstance(digest, str) or not _SHA256_HEX.match(digest):
                raise ArtifactError(f'invalid sha256 for {record.get("path")!r}: {digest!r}')
    assert_unique_paths(paths)
    return data


def _entry_summary(entry):
    keys = ('path', 'type', 'size', 'sha256', 'linkTarget')
    return {key: entry[key] for key in keys if key in entry}


def check_tree(root, manifest, allow_symlink=False, root_id=None, manifest_path=None):
    """Re-hash ``root`` and compare with ``manifest``; explicit drift report."""
    exclude = [manifest_path] if manifest_path and _is_within(manifest_path, root) else []
    entries = iter_entries(root, allow_symlink=allow_symlink, exclude=exclude)
    current = {entry['path']: entry for entry in entries}
    expected = {record['path']: record for record in manifest['files']}
    changed = []
    for path in sorted(set(current) & set(expected)):
        actual, wanted = current[path], expected[path]
        actual_type = actual.get('type', 'file')
        wanted_type = wanted.get('type', 'file')
        if (actual.get('sha256') != wanted.get('sha256') or actual.get('size') != wanted.get('size')
                or actual_type != wanted_type or actual.get('linkTarget') != wanted.get('linkTarget')):
            changed.append({'path': path, 'expected': _entry_summary(wanted), 'actual': _entry_summary(actual)})
    missing = sorted(set(expected) - set(current))
    extra = sorted(set(current) - set(expected))
    computed_aggregate = aggregate_sha256(entries)
    expected_aggregate = manifest.get('aggregateSha256')
    policy_mode = symlink_policy(allow_symlink)['mode']
    manifest_mode = (manifest.get('symlinkPolicy') or {}).get('mode')
    result = {
        'schemaVersion': SCHEMA_VERSION,
        'rootId': manifest.get('rootId'),
        'computedRootId': root_id or default_root_id(root),
        'symlinkPolicy': symlink_policy(allow_symlink),
        'expectedAggregateSha256': expected_aggregate,
        'computedAggregateSha256': computed_aggregate,
        'aggregateMatches': expected_aggregate == computed_aggregate,
        'symlinkPolicyMatches': manifest_mode in (None, policy_mode),
        'changed': changed,
        'missing': missing,
        'extra': extra,
    }
    result['rootIdChanged'] = result['rootId'] != result['computedRootId']
    result['ok'] = not (changed or missing or extra) and result['aggregateMatches'] and result['symlinkPolicyMatches']
    return result


# --------------------------------------------------------------------------- privacy

PRIVACY_RULES = (
    ('openai-api-key-env', re.compile(r'\bOPENAI_API_KEY\b\s*[:=]\s*\S+', re.IGNORECASE), 'api-key-env'),
    ('deepseek-api-key-env', re.compile(r'\bDEEPSEEK_API_KEY\b\s*[:=]\s*\S+', re.IGNORECASE), 'api-key-env'),
    ('anthropic-api-key-env', re.compile(r'\bANTHROPIC_API_KEY\b\s*[:=]\s*\S+', re.IGNORECASE), 'api-key-env'),
    ('openai-key-value', re.compile(r'\bsk-[A-Za-z0-9_\-]{20,}'), 'api-key-value'),
    ('anthropic-key-value', re.compile(r'\bsk-ant-[A-Za-z0-9_\-]{20,}'), 'api-key-value'),
    ('authorization-header', re.compile(r'\bAuthoriz(?:ation|e)\s*:\s*[^\r\n]+', re.IGNORECASE), 'auth-header'),
    ('bearer-token', re.compile(r'\bBearer\s+[A-Za-z0-9._~+/\-]{8,}=*', re.IGNORECASE), 'bearer-token'),
    ('token-query-parameter',
     re.compile(r'[?&](?:access_token|refresh_token|id_token|api_key|apikey|auth|token)=[A-Za-z0-9._~%+\-]{4,}',
                re.IGNORECASE), 'token-query'),
    ('secret-env-dump',
     re.compile(r'\b[A-Z][A-Z0-9_]{0,40}(?:SECRET|TOKEN|PASSWORD|PASSWD|API_KEY|ACCESS_KEY)[A-Z0-9_]{0,40}\s*[:=]\s*\S+'),
     'secret-env'),
    ('dsh-web-token', re.compile(r'\bDSH_(?:WEB_|LOCAL_|HOST_)?TOKEN\b\s*[:=]\s*\S+', re.IGNORECASE), 'dsh-web-token'),
    ('dsh-token-literal', re.compile(r'\bdsh[-_]?(?:web[-_]?|local[-_]?)?token\b\s*[:=]\s*\S+', re.IGNORECASE),
     'dsh-web-token'),
    ('linux-home-path', re.compile(r'(?<![\w.])/home/[A-Za-z0-9][A-Za-z0-9._-]*'), 'user-path'),
    ('macos-home-path', re.compile(r'(?<![\w.])/Users/[A-Za-z0-9][A-Za-z0-9._-]*'), 'user-path'),
    ('windows-home-path', re.compile(r'\b[A-Za-z]:\\Users\\[A-Za-z0-9][^\\\s"\']*'), 'user-path'),
)


def _preview(line, match):
    """Show the offending line with the match redacted; never echo the secret."""
    redacted = f'{line[:match.start()]}<redacted>{line[match.end():]}'
    return re.sub(r'\s+', ' ', redacted).strip()[:160]


def _scan_lines(text, path, findings, start_line=1):
    for offset, line in enumerate(text.splitlines()):
        for rule, pattern, kind in PRIVACY_RULES:
            for match in pattern.finditer(line):
                findings.append({'path': path, 'line': start_line + offset, 'rule': rule,
                                 'kind': kind, 'preview': _preview(line, match)})


def _read_text_capped(path):
    try:
        with open(path, 'rb') as handle:
            data = handle.read(PRIVACY_SCAN_MAX_BYTES + 1)
    except OSError as exc:
        raise ArtifactError(f'unreadable file {path}: {exc.strerror or exc}') from exc
    truncated = len(data) > PRIVACY_SCAN_MAX_BYTES
    return data[:PRIVACY_SCAN_MAX_BYTES].decode('utf-8', 'ignore'), truncated


def privacy_scan(root, exclude=()):
    """Scan filenames and text content for secret-like material.

    Symlinks are never followed here either; their target text is scanned as a
    string and reported, so an escaping link is visible without being read.
    """
    entries = iter_entries(root, allow_symlink=True, exclude=exclude, enforce=False, hash_files=False)
    findings = []
    truncated = []
    for entry in entries:
        path = entry['path']
        for reason in credential_reasons(path):
            findings.append({'path': path, 'line': 0, 'rule': reason,
                             'kind': 'secret-filename' if reason == 'secret-like-name' else 'credential-filename',
                             'preview': ''})
        if entry['type'] == 'symlink':
            findings.append({'path': path, 'line': 0, 'rule': 'symlink-recorded', 'kind': 'symlink',
                             'preview': entry['linkTarget'][:160]})
            _scan_lines(entry['linkTarget'], path, findings, start_line=0)
        elif entry['type'] == 'other':
            findings.append({'path': path, 'line': 0, 'rule': entry.get('special', 'special'),
                             'kind': 'non-regular-file', 'preview': ''})
        else:
            text, was_truncated = _read_text_capped(os.path.join(os.path.abspath(root), path))
            if was_truncated:
                truncated.append(path)
            _scan_lines(text, path, findings)
    findings.sort(key=lambda item: (item['path'], item['line'], item['rule']))
    return {
        'schemaVersion': SCHEMA_VERSION,
        'rootId': default_root_id(root),
        'policy': {'followSymlinks': False, 'scannedBytesPerFile': PRIVACY_SCAN_MAX_BYTES,
                   'note': 'Reports filenames and text; never emits matched secret text, only a redacted preview.'},
        'findings': findings,
        'truncated': sorted(truncated),
        'ok': not findings,
    }


# --------------------------------------------------------------------------- cli

def _render(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2) + '\n'


def _emit(payload, out):
    text = _render(payload)
    if out and out != '-':
        target = Path(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode('utf-8'))
    else:
        sys.stdout.write(text)


def parse_args(argv):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = 'manifest'
    if argv and argv[0] in ('manifest', 'privacy-check'):
        command = argv.pop(0)
    parser = argparse.ArgumentParser(
        prog='manifest-study-artifacts.py',
        description='Deterministic artifact integrity and privacy manifests (read-only over the artifact tree).')
    parser.add_argument('artifact_dir', help='artifact root directory (never modified)')
    parser.add_argument('--check', metavar='MANIFEST', help='re-hash artifact_dir and compare with MANIFEST')
    parser.add_argument('--privacy-check', action='store_true', help='scan content and filenames for secret-like material')
    parser.add_argument('--out', metavar='FILE', help="write JSON here instead of stdout ('-' means stdout)")
    parser.add_argument('--allow-symlink', action='store_true',
                        help='record symlink target text instead of rejecting symlinks')
    parser.add_argument('--root-id', metavar='ID', help='stable root identifier (default: directory name)')
    args = parser.parse_args(argv)
    if args.privacy_check:
        command = 'privacy-check'
    args.command = command
    return args


def main(argv=None):
    try:
        args = parse_args(argv)
        if args.command == 'privacy-check':
            if args.check:
                raise ArtifactError('--privacy-check cannot be combined with --check')
            result = privacy_scan(args.artifact_dir)
            _emit(result, args.out)
            return 0 if result['ok'] else 3
        if args.check:
            manifest = load_manifest(args.check)
            result = check_tree(args.artifact_dir, manifest, allow_symlink=args.allow_symlink,
                                root_id=args.root_id, manifest_path=args.check)
            _emit(result, args.out)
            return 0 if result['ok'] else 2
        exclude = [args.out] if args.out and args.out != '-' else []
        manifest = build_manifest(args.artifact_dir, root_id=args.root_id,
                                  allow_symlink=args.allow_symlink, exclude=exclude)
        _emit(manifest, args.out)
        return 0
    except ArtifactError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
