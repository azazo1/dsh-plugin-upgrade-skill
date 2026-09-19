#!/usr/bin/env python3
"""Model-free isolation preflight for the study-v1 A/B/C/D material packages.

The tool builds a *material mount plan* either from the study authority
(``paper/study-v1/config.json`` plus the existing material builder
``paper/scripts/prepare-study-v1.py``) or from a synthetic ``--material-root``
tree, then runs explicit, individually-testable boundary checks over that plan.

It never calls a solver model, never touches the network, and never mutates the
benchmark tasks, the skills tree or the material packages.  ``--docker-canary`` is
opt-in: when the Docker daemon or a local image is unavailable the report says
``runtimeCanaryStatus = "not-run"`` with the reason instead of guessing.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / 'paper/study-v1'
SCHEMA_PATH = STUDY / 'qc/isolation-preflight.schema.json'
REPORT_SCHEMA_VERSION = 'study-v1-isolation-preflight/1'

PILOT_TASKS = (
    'H4-tsbuildinfo-trap',
    'H6-remote-error-trap',
    'H12-remote-result-boundary-trap',
    'H25-session-seed-boundary-trap',
)
ARMS = ('A', 'B', 'C', 'D')

# Container-side targets that are expected and therefore not redacted.
CONTAINER_PATHS = (
    '/app',
    '/app/materials',
    '/app/fixture',
    '/app/instruction.md',
    '/app/agent-output',
    '/probe.mjs',
    '/probe.sh',
    '/home/study',
    '/tmp',
)

# Segment/name tokens that must never be reachable from a solver cell.
SOLUTION_TOKENS = ('solution', 'solutions', 'solve.sh', 'solution.md', 'oracle')
JUDGE_TOKENS = ('tests', 'judge.mjs', 'judge.mts', 'judge.js', 'test.sh', 'judge-utils')
RESULT_TOKENS = ('results',)
HOST_CONFIG_TOKENS = ('.codex', '.config', '.claude', '.ssh', '.aws', '.kube', '.gitconfig', '.npmrc')
SKILL_TOKENS = ('skills', '.agents')

SECRET_ENV_RE = re.compile(r'(API_?KEY|_TOKEN|^TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)', re.I)
DEFAULT_SECRET_ENV_NAMES = (
    'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY',
    'DEEPSEEK_API_KEY',
    'GITHUB_TOKEN',
    'GH_TOKEN',
    'AWS_SECRET_ACCESS_KEY',
    'AWS_ACCESS_KEY_ID',
    'AZURE_OPENAI_API_KEY',
    'CODEX_API_KEY',
    'REPORT_JUDGE_TOKEN',
)


class UsageError(Exception):
    """Invalid CLI usage or configuration (exit code 2)."""


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = _load_module('prepare_study_v1', Path(__file__).with_name('prepare-study-v1.py'))


# --------------------------------------------------------------------------- #
# Deterministic output helpers
# --------------------------------------------------------------------------- #

def sha(data):
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def norm(path):
    return str(path).replace('\\', '/')


def _host_absolute(value):
    text = norm(value)
    if text.startswith('/') or text.startswith('//'):
        return True
    return bool(re.match(r'^[A-Za-z]:/', text))


def redact_path(value):
    """Return a deterministic, host-path-free rendering of one path value."""
    if not isinstance(value, str) or not value:
        return value
    text = norm(value)
    if _host_absolute(text):
        if any(text == p or text.startswith(p + '/') for p in CONTAINER_PATHS):
            return value
        return '<redacted>'
    return value


_HOST_PATH_RE = re.compile(
    r'(?<![A-Za-z0-9_.])(?:[A-Za-z]:[\\/]|//|'
    r'/(?!(?:app|probe\.mjs|probe\.sh|home/study|tmp)(?:/|$)))')


def redact_text(value):
    """Replace tokens that embed a host absolute path; keep container paths."""
    if not isinstance(value, str) or not value:
        return value
    out = []
    for token in value.split(' '):
        out.append('<redacted>' if token and _HOST_PATH_RE.search(token) else token)
    return redact_path(' '.join(out)) if len(out) == 1 else ' '.join(out)


def sanitize(value):
    """Recursively redact host absolute paths from a report structure."""
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def serialize_report(report):
    """Byte-stable report serialization: sorted keys, fixed indent, trailing newline."""
    return json.dumps(sanitize(report), ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def _segments(value):
    return [s for s in PurePosixPath(norm(value)).parts if s not in ('', '.', '/')]


def _token_hit(path, tokens):
    parts = [p.lower() for p in _segments(path)]
    base = parts[-1] if parts else ''
    for token in tokens:
        if token in parts or token == base:
            return True
        if '/' in token and token in norm(path).lower():
            return True
    return False


def _finding(task, arm, detail):
    return {'task': task, 'arm': arm, 'detail': redact_text(str(detail))}


def _tasks(plan):
    tasks = plan.get('tasks') if isinstance(plan, dict) else None
    return tasks if isinstance(tasks, list) else []


def _arms(task):
    arms = task.get('arms') if isinstance(task, dict) else None
    return arms if isinstance(arms, dict) else {}


def _entries(arm):
    material = arm.get('material') if isinstance(arm, dict) else None
    entries = material.get('entries') if isinstance(material, dict) else None
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def _mounts(arm):
    mounts = arm.get('mounts') if isinstance(arm, dict) else None
    return [m for m in mounts if isinstance(m, dict)] if isinstance(mounts, list) else []


def _entry_map(arm):
    return {norm(e.get('path', '')): e for e in _entries(arm)}


def _material_entries(arm):
    return {e['path']: e for e in _entries(arm) if e.get('path')}


def _iter_paths(plan):
    """Yield (task, arm, kind, path) for every path-bearing plan field."""
    env = plan.get('environment') or {}
    for mount in env.get('hostMounts') or []:
        if isinstance(mount, dict):
            for key in ('source', 'target', 'id'):
                if mount.get(key):
                    yield ('<environment>', '-', 'hostMount', norm(mount[key]))
    for mount in ((env.get('nativeSkills') or {}).get('mounts') or []):
        if isinstance(mount, dict):
            for key in ('source', 'target', 'id'):
                if mount.get(key):
                    yield ('<environment>', '-', 'nativeSkill', norm(mount[key]))
    for task in _tasks(plan):
        tid = task.get('task', '<missing>') if isinstance(task, dict) else '<missing>'
        for arm, data in sorted(_arms(task).items()):
            if not isinstance(data, dict):
                continue
            for key in ('source', 'target', 'id'):
                value = (data.get('material') or {}).get(key)
                if value:
                    yield (tid, arm, 'material', norm(value))
            for entry in _entries(data):
                yield (tid, arm, 'entry', norm(entry.get('path', '')))
            for mount in _mounts(data):
                for key in ('source', 'target', 'id'):
                    if mount.get(key):
                        yield (tid, arm, mount.get('kind', 'mount'), norm(mount[key]))
            for key in ('source', 'target'):
                value = (data.get('output') or {}).get(key)
                if value:
                    yield (tid, arm, 'output', norm(value))
            for writable in data.get('workspaceWritable') or []:
                yield (tid, arm, 'workspace', norm(writable))


def _link_escapes(entry):
    if entry.get('escapesRoot') is True:
        return True
    resolved = entry.get('linkResolved')
    if isinstance(resolved, str) and (resolved == '..' or resolved.startswith('../') or _host_absolute(resolved)):
        return True
    link = entry.get('link')
    if not isinstance(link, str) or not link:
        return False
    if _host_absolute(link):
        return True
    parent = list(PurePosixPath(norm(entry.get('path', ''))).parent.parts)
    for part in PurePosixPath(norm(link)).parts:
        if part == '..':
            if not parent:
                return True
            parent.pop()
        elif part not in ('', '.'):
            parent.append(part)
    return False


def validate_plan_shape(plan):
    """Return structural errors that make a plan unusable (CLI exit code 2)."""
    errors = []
    if not isinstance(plan, dict):
        return ['plan is not an object']
    if not isinstance(plan.get('tasks'), list) or not plan['tasks']:
        errors.append('plan has no task list')
    if not isinstance(plan.get('environment'), dict):
        errors.append('plan has no environment block')
    return errors


# --------------------------------------------------------------------------- #
# Plan construction
# --------------------------------------------------------------------------- #

def _arm_env():
    return {'HOME': '/home/study', 'STUDY_NATIVE_SKILLS': 'disabled'}


def _standard_mounts(tid, arm, material_source, *, fixture_source, fixture_readonly,
                     output_source, output_target, extra=None):
    mounts = [
        {'id': 'materials', 'kind': 'material', 'source': material_source,
         'target': '/app/materials', 'readOnly': True},
        {'id': 'fixture', 'kind': 'fixture', 'source': fixture_source,
         'target': '/app/fixture', 'readOnly': fixture_readonly},
        {'id': 'instruction', 'kind': 'instruction', 'source': f'instruction/{tid}.md',
         'target': '/app/instruction.md', 'readOnly': True},
        {'id': 'output', 'kind': 'output', 'source': output_source,
         'target': output_target, 'readOnly': False},
        {'id': 'probe', 'kind': 'probe', 'source': 'probe.mjs', 'target': '/probe.mjs',
         'readOnly': True},
    ]
    if extra:
        mounts.extend(extra)
    return mounts


def _task_record(tid, variant, interaction_mode, material_source, entries, *, fixture_source,
                 fixture_readonly=True, output_source=None, output_target=None,
                 extra_mounts=None, workspace_writable=None, env=None):
    """Assemble one task's four arms around an already-collected material set."""
    output_source = output_source or f'output/{tid}'
    output_target = output_target or f'/app/agent-output/{tid}'
    extra_mounts = list(extra_mounts or [])
    workspace_writable = list(workspace_writable or [])
    arms = {}
    for arm in ARMS:
        arms[arm] = {
            'material': {'id': 'materials', 'source': material_source(arm),
                         'target': '/app/materials', 'readOnly': True,
                         'entries': sorted(entries(arm), key=lambda e: e.get('path', ''))},
            'mounts': _standard_mounts(
                tid, arm, material_source(arm), fixture_source=fixture_source,
                fixture_readonly=fixture_readonly, output_source=f'{output_source}/{arm}',
                output_target=output_target, extra=extra_mounts),
            'output': {'source': f'{output_source}/{arm}', 'target': output_target,
                       'readOnly': False},
            'workspaceWritable': workspace_writable,
            'env': dict(env or _arm_env()),
        }
    return {'task': tid, 'materialVariant': variant, 'interactionMode': interaction_mode,
            'sharedFactSupplement': any(
                str(e.get('path', '')).endswith('fact-supplement.md')
                for arm in arms for e in arms[arm]['material']['entries']),
            'arms': arms}


def _environment_block():
    return {
        'network': 'none',
        'hostMounts': [],
        'nativeSkills': {'autoDiscovery': False, 'mounts': [],
                         'note': 'native skill catalog and auto-discovery disabled in every arm'},
        'env': _arm_env(),
        'credentialEnvNames': sorted(DEFAULT_SECRET_ENV_NAMES),
        'secretsInjected': [],
    }


def build_plan_from_authority(task_ids=None, arms=ARMS):
    """Derive the mount plan from the pinned study authority and the pilot policy.

    Returns ``(plan, cells)`` where ``cells[task][arm]`` maps relative material
    paths to bytes (used only by the optional container canary).
    """
    config = json.loads((STUDY / 'config.json').read_text())
    manifest, packages, prompts, _ = prepare.build_materials(config)
    by_id = {t['task']: t for t in manifest['tasks']}
    requested = sorted(task_ids or PILOT_TASKS)
    for tid in requested:
        if tid not in by_id:
            raise UsageError(f'task not in the pinned candidate inventory: {tid}')
    cells, task_records = {}, []
    for tid in requested:
        record = by_id[tid]
        variant = record['materialVariant']
        package = packages[variant]
        cells[tid] = {arm: dict(package[arm]) for arm in ARMS}
        # Pilot write policy mirrors paper/scripts/pilot-study-v1.py: static
        # fixtures stay read-only except the H4 lib exception; H25 is hands-on.
        if tid.startswith('H25-'):
            fixture_readonly, extra, writable = False, [], ['src', 'package.json']
        elif tid.startswith('H4-'):
            fixture_readonly, writable = True, ['lib']
            extra = [{'id': 'workspace-lib', 'kind': 'workspace',
                      'source': f'benchmark/tasks/{tid}/environment/fixture/lib',
                      'target': '/app/fixture/lib', 'readOnly': False}]
        else:
            fixture_readonly, extra, writable = True, [], []
        task_records.append(_task_record(
            tid, variant, record['interactionMode'],
            lambda arm, v=variant: f'materials/{v}/{arm}',
            lambda arm, c=cells[tid]: [
                {'path': p, 'type': 'file', 'sha256': sha(b), 'bytes': len(b),
                 'link': None, 'linkResolved': None, 'escapesRoot': False,
                 'hardlinkShared': False}
                for p, b in sorted(c[arm].items())],
            fixture_source=f'benchmark/tasks/{tid}/environment/fixture',
            fixture_readonly=fixture_readonly, extra_mounts=extra,
            workspace_writable=writable))
    inventory = json.loads(prepare.blob(config['sourceCommit'], config['candidateInventory']))
    pinned = sorted(t['id'] for t in inventory['tasks'])
    live = sorted(p.name for p in (ROOT / 'benchmark/tasks').iterdir() if p.is_dir()) \
        if (ROOT / 'benchmark/tasks').is_dir() else []
    plan = {
        'schemaVersion': REPORT_SCHEMA_VERSION,
        'study': config['id'],
        'materialRevision': config.get('materialRevision'),
        'materialSource': 'authority',
        'materialRootLabel': None,
        'runtimeCanary': {'status': 'not-run', 'requested': False,
                          'reason': 'offline plan only; --docker-canary not requested'},
        'environment': _environment_block(),
        'inventory': {
            'inventoryId': inventory.get('id', 'task-annotation-v1'),
            'pinnedTaskCount': len(pinned),
            'pinnedTasks': pinned,
            'liveBenchmarkTaskCount': len(live),
            'unpinnedLiveTasks': sorted(set(live) - set(pinned)),
            'requestedTasks': requested,
        },
        'tasks': task_records,
    }
    return plan, cells


def _walk_material_entries(base):
    """Collect entries under ``base`` without following symlinks."""
    entries = []
    base_real = Path(os.path.realpath(base))
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        for name in sorted(list(dirnames)):
            path = Path(dirpath) / name
            if path.is_symlink():
                dirnames.remove(name)
                entries.append(_symlink_entry(path, base, base_real))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = path.relative_to(base).as_posix()
            if path.is_symlink():
                entries.append(_symlink_entry(path, base, base_real))
                continue
            stat = path.stat()
            entries.append({
                'path': rel, 'type': 'file', 'sha256': sha(path.read_bytes()),
                'bytes': stat.st_size, 'link': None, 'linkResolved': None,
                'escapesRoot': False, 'hardlinkShared': stat.st_nlink > 1,
            })
    return sorted(entries, key=lambda e: e['path'])


def _symlink_entry(path, base, base_real):
    link = os.readlink(path)
    target = Path(os.path.realpath(path))
    try:
        resolved = target.relative_to(base_real).as_posix()
        escapes = False
    except ValueError:
        resolved = os.path.relpath(target, base_real).replace(os.sep, '/')
        escapes = True
    return {
        'path': path.relative_to(base).as_posix(),
        'type': 'symlink', 'sha256': None, 'bytes': 0, 'link': link,
        'linkResolved': resolved, 'escapesRoot': escapes, 'hardlinkShared': False,
    }


def build_plan_from_material_root(root, task_ids=None, arms=ARMS):
    """Build a plan from a synthetic ``<root>/<task>/<arm>/...`` fixture tree."""
    root = Path(root)
    if not root.is_dir():
        raise UsageError(f'--material-root is not a directory: {redact_path(str(root))}')
    discovered = sorted(p.name for p in root.iterdir() if p.is_dir())
    requested = sorted(task_ids) if task_ids else discovered
    cells, task_records = {}, []
    for tid in requested:
        task_dir = root / tid
        if not task_dir.is_dir():
            raise UsageError(f'task directory missing under --material-root: {tid}')
        cells[tid] = {}
        entries_by_arm = {}
        for arm in ARMS:
            arm_dir = task_dir / arm
            entries = _walk_material_entries(arm_dir) if arm_dir.is_dir() else []
            entries_by_arm[arm] = entries
            cells[tid][arm] = {
                e['path']: (arm_dir / e['path']).read_bytes()
                for e in entries if e['type'] == 'file'
            }
        label = 'material-root'
        task_records.append(_task_record(
            tid, 'synthetic', 'static',
            lambda arm: f'{label}/{tid}/{arm}',
            lambda arm, e=entries_by_arm: e[arm],
            fixture_source=f'fixture/{tid}',
            fixture_readonly=True))
    plan = {
        'schemaVersion': REPORT_SCHEMA_VERSION,
        'study': 'budgeted-small-model-migration-v1',
        'materialRevision': 'synthetic',
        'materialSource': 'material-root',
        'materialRootLabel': '<material-root>',
        'runtimeCanary': {'status': 'not-run', 'requested': False,
                          'reason': 'offline plan only; --docker-canary not requested'},
        'environment': _environment_block(),
        'inventory': None,
        'tasks': task_records,
    }
    return plan, cells


# --------------------------------------------------------------------------- #
# Checks (each returns a list of findings; empty means passing)
# --------------------------------------------------------------------------- #

ALLOWED_TARGETS = {'/app/materials', '/app/fixture', '/app/instruction.md', '/probe.mjs'}
REQUIRED_KINDS = ('material', 'fixture', 'instruction', 'output', 'probe')


def _arm_allowed_targets(tid):
    return set(ALLOWED_TARGETS) | {
        f'/app/agent-output/{tid}', '/app/fixture/lib', '/app/fixture/src',
        '/app/fixture/package.json',
    }


def check_mount_manifest(plan):
    out = []
    tasks = _tasks(plan)
    if not tasks:
        out.append(_finding('<plan>', '-', 'mount plan has no tasks'))
    seen = set()
    for task in tasks:
        if not isinstance(task, dict):
            out.append(_finding('<plan>', '-', 'task entry is not an object'))
            continue
        tid = task.get('task') or '<missing>'
        if tid in seen:
            out.append(_finding(tid, '-', 'duplicate task entry in mount plan'))
        seen.add(tid)
        arm_map = _arms(task)
        missing = [a for a in ARMS if a not in arm_map]
        unknown = sorted(a for a in arm_map if a not in ARMS)
        if missing:
            out.append(_finding(tid, '-', 'missing condition arms: ' + ','.join(missing)))
        if unknown:
            out.append(_finding(tid, '-', 'unknown condition arms: ' + ','.join(unknown)))
        for arm, data in sorted(arm_map.items()):
            if not isinstance(data, dict):
                out.append(_finding(tid, arm, 'arm entry is not an object'))
                continue
            material = data.get('material')
            if not isinstance(material, dict):
                out.append(_finding(tid, arm, 'arm has no material mount'))
                continue
            if not material.get('target'):
                out.append(_finding(tid, arm, 'material mount has no target'))
            if not isinstance(material.get('readOnly'), bool):
                out.append(_finding(tid, arm, 'material mount readOnly is not boolean'))
            entries = _entries(data)
            if not entries:
                out.append(_finding(tid, arm, 'material manifest has no files'))
            paths = [norm(e.get('path', '')) for e in entries]
            if 'ENTRY.md' not in paths:
                out.append(_finding(tid, arm, 'material manifest is missing ENTRY.md'))
            if len(paths) != len(set(paths)):
                out.append(_finding(tid, arm, 'material manifest has duplicate paths'))
            for entry in entries:
                path = entry.get('path')
                if not isinstance(path, str) or not path:
                    out.append(_finding(tid, arm, 'material entry without a path'))
                    continue
                kind = entry.get('type', 'file')
                if kind == 'symlink':
                    if not entry.get('link'):
                        out.append(_finding(tid, arm, f'symlink entry without link: {path}'))
                else:
                    if not re.fullmatch(r'[0-9a-f]{64}', str(entry.get('sha256', ''))):
                        out.append(_finding(tid, arm, f'entry has no valid sha256: {path}'))
                    if not isinstance(entry.get('bytes'), int) or entry['bytes'] < 0:
                        out.append(_finding(tid, arm, f'entry has invalid byte size: {path}'))
            mounts = _mounts(data)
            ids = [m.get('id') for m in mounts]
            if len(ids) != len(set(ids)):
                out.append(_finding(tid, arm, 'duplicate mount ids'))
            kinds = {m.get('kind') for m in mounts}
            for required in REQUIRED_KINDS:
                if required not in kinds:
                    out.append(_finding(tid, arm, f'missing {required} mount'))
            allowed = _arm_allowed_targets(tid)
            for mount in mounts:
                if mount.get('target') not in allowed:
                    out.append(_finding(tid, arm, f'unexpected mount target: {mount.get("target")}'))
                if not isinstance(mount.get('readOnly'), bool):
                    out.append(_finding(tid, arm, f'mount readOnly is not boolean: {mount.get("id")}'))
            output = data.get('output')
            if not isinstance(output, dict):
                out.append(_finding(tid, arm, 'arm has no artifact output block'))
            elif output.get('readOnly') is not False:
                out.append(_finding(tid, arm, 'artifact output is not writable'))
    return out


def _foreign_hashes(arm_map, exclude):
    foreign = {}
    for arm, data in sorted(arm_map.items()):
        if arm == exclude:
            continue
        for entry in _entries(data):
            if entry.get('sha256'):
                foreign.setdefault(entry['sha256'], f'{arm}:{entry["path"]}')
    return foreign


def check_arm_a_disclosure(plan):
    out = []
    for task in _tasks(plan):
        tid = task.get('task', '<missing>')
        arm_map = _arms(task)
        a_entries = _entries(arm_map.get('A', {}))
        foreign = _foreign_hashes(arm_map, 'A')
        for entry in a_entries:
            path = norm(entry.get('path', ''))
            if path != 'ENTRY.md':
                out.append(_finding(tid, 'A', f'arm A exposes non-entry material: {path}'))
            if path.startswith('references/') or path in ('guidance.md', 'fact-supplement.md'):
                out.append(_finding(tid, 'A', f'arm A exposes guidance/reference material: {path}'))
            if entry.get('sha256') and entry['sha256'] in foreign:
                out.append(_finding(
                    tid, 'A',
                    f'arm A file {path} is byte-identical to {foreign[entry["sha256"]]}'))
    return out


def check_arm_b_reference_isolation(plan):
    out = []
    for task in _tasks(plan):
        tid = task.get('task', '<missing>')
        arm_map = _arms(task)
        b_entries = _entries(arm_map.get('B', {}))
        allowed = {'ENTRY.md', 'guidance.md'}
        reference_hashes = {}
        for arm in ('C', 'D'):
            for entry in _entries(arm_map.get(arm, {})):
                path = norm(entry.get('path', ''))
                if path.startswith('references/') or path == 'fact-supplement.md':
                    if entry.get('sha256'):
                        reference_hashes.setdefault(entry['sha256'], f'{arm}:{path}')
        for entry in b_entries:
            path = norm(entry.get('path', ''))
            if path not in allowed:
                out.append(_finding(tid, 'B', f'arm B exposes unexpected material: {path}'))
            if path.startswith('references/') or path == 'fact-supplement.md':
                out.append(_finding(tid, 'B', f'arm B exposes a C/D reference set: {path}'))
            if entry.get('sha256') and entry['sha256'] in reference_hashes:
                out.append(_finding(
                    tid, 'B',
                    f'arm B file {path} is byte-identical to {reference_hashes[entry["sha256"]]}'))
    return out


def check_cd_shared_bytes(plan):
    out = []
    for task in _tasks(plan):
        tid = task.get('task', '<missing>')
        arm_map = _arms(task)
        c, d = _entry_map(arm_map.get('C', {})), _entry_map(arm_map.get('D', {}))
        excluded = {'ENTRY.md', 'guidance.md'}
        c_hashes = {p: e.get('sha256') for p, e in c.items() if p not in excluded}
        d_hashes = {p: e.get('sha256') for p, e in d.items() if p not in excluded}
        for path in sorted(set(c_hashes) - set(d_hashes)):
            out.append(_finding(tid, 'C', f'C has a fact/reference file missing from D: {path}'))
        for path in sorted(set(d_hashes) - set(c_hashes)):
            out.append(_finding(tid, 'D', f'D has a fact/reference file missing from C: {path}'))
        for path in sorted(set(c_hashes) & set(d_hashes)):
            if c_hashes[path] != d_hashes[path]:
                out.append(_finding(tid, '-', f'C/D bytes differ for shared file: {path}'))
        if task.get('sharedFactSupplement'):
            for arm, mapping in (('C', c), ('D', d)):
                if 'fact-supplement.md' not in mapping:
                    out.append(_finding(tid, arm, 'shared fact supplement is missing'))
    return out


def check_d_guidance_only_delta(plan):
    out = []
    for task in _tasks(plan):
        tid = task.get('task', '<missing>')
        arm_map = _arms(task)
        c_paths = {norm(e.get('path', '')) for e in _entries(arm_map.get('C', {}))}
        d_paths = {norm(e.get('path', '')) for e in _entries(arm_map.get('D', {}))}
        extra = sorted(d_paths - c_paths)
        if extra != ['guidance.md']:
            out.append(_finding(tid, 'D', 'D delta beyond C must be exactly guidance.md, got: '
                              + (','.join(extra) if extra else '<none>')))
        if 'guidance.md' in c_paths:
            out.append(_finding(tid, 'C', 'C must not contain guidance.md'))
        if 'guidance.md' not in d_paths:
            out.append(_finding(tid, 'D', 'D adapted procedure material is missing (guidance.md)'))
    return out


def _leak_check(plan, tokens, label):
    out = []
    for task, arm, kind, path in _iter_paths(plan):
        if _token_hit(path, tokens):
            out.append(_finding(task, arm, f'{label} reachable from {kind}: {path}'))
    return out


def check_solution_leak(plan):
    return _leak_check(plan, SOLUTION_TOKENS, 'solution material')


def check_judge_leak(plan):
    return _leak_check(plan, JUDGE_TOKENS, 'task tests/judge internals')


def check_results_leak(plan):
    return _leak_check(plan, RESULT_TOKENS, 'benchmark results')


def check_cross_arm_output(plan):
    out = []
    for task in _tasks(plan):
        tid = task.get('task', '<missing>')
        arm_map = _arms(task)
        for arm, data in sorted(arm_map.items()):
            if not isinstance(data, dict):
                continue
            tokens = set()
            for other, other_data in sorted(arm_map.items()):
                if other == arm or not isinstance(other_data, dict):
                    continue
                for source in ((other_data.get('material') or {}).get('source'),
                               (other_data.get('output') or {}).get('source')):
                    if source:
                        tokens.add(norm(source))
            if not tokens:
                continue
            candidates = []
            for key in ('source', 'target', 'id'):
                value = (data.get('material') or {}).get(key)
                if value:
                    candidates.append(norm(value))
            for entry in _entries(data):
                candidates.append(norm(entry.get('path', '')))
            for mount in _mounts(data):
                for key in ('source', 'target', 'id'):
                    if mount.get(key):
                        candidates.append(norm(mount[key]))
            for key in ('source', 'target'):
                value = (data.get('output') or {}).get(key)
                if value:
                    candidates.append(norm(value))
            for candidate in candidates:
                for token in sorted(tokens):
                    if token and token in candidate:
                        out.append(_finding(tid, arm, f'other-condition path visible: {candidate}'))
                        break
    return out


def check_native_skill_leak(plan):
    out = []
    env = plan.get('environment') or {}
    skills = env.get('nativeSkills')
    if not isinstance(skills, dict):
        out.append(_finding('<environment>', '-', 'native skill policy block is missing'))
    else:
        if skills.get('autoDiscovery') is not False:
            out.append(_finding('<environment>', '-', 'native skill auto-discovery is not disabled'))
        if skills.get('mounts'):
            out.append(_finding('<environment>', '-', 'native skill catalog is mounted'))
    return out + _leak_check(plan, SKILL_TOKENS, 'native skill catalog')


def check_agents_skills_mount(plan):
    out = []
    for task, arm, kind, path in _iter_paths(plan):
        if '.agents' in _segments(path) or 'agents/skills' in path.lower():
            out.append(_finding(task, arm, f'~/.agents/skills reachable from {kind}: {path}'))
    return out


def check_host_config_mount(plan):
    return _leak_check(plan, HOST_CONFIG_TOKENS, 'private host config')


def check_credential_env(plan):
    out = []
    env = plan.get('environment') or {}
    declared = {str(n).upper() for n in env.get('credentialEnvNames') or []}
    scopes = [('<environment>', '-', env.get('env') or {})]
    for task in _tasks(plan):
        tid = task.get('task', '<missing>')
        for arm, data in sorted(_arms(task).items()):
            if isinstance(data, dict):
                scopes.append((tid, arm, data.get('env') or {}))
    for task, arm, values in scopes:
        if not isinstance(values, dict):
            out.append(_finding(task, arm, 'environment block is not an object'))
            continue
        for key, value in sorted(values.items()):
            if value is None or value == '' or value is False:
                continue
            if str(key).upper() in declared or SECRET_ENV_RE.search(str(key)):
                out.append(_finding(task, arm, f'credential environment variable present: {key}'))
    for key in env.get('secretsInjected') or []:
        out.append(_finding('<environment>', '-', f'credential was injected into the cell: {key}'))
    return out


def check_material_readonly(plan):
    out = []
    for task in _tasks(plan):
        tid = task.get('task', '<missing>')
        for arm, data in sorted(_arms(task).items()):
            if not isinstance(data, dict):
                continue
            material = data.get('material') or {}
            if material.get('readOnly') is not True:
                out.append(_finding(tid, arm, 'material mount is not read-only'))
            for mount in _mounts(data):
                if mount.get('kind') == 'material' and mount.get('readOnly') is not True:
                    out.append(_finding(tid, arm, 'material mount is not read-only'))
    return out


def check_workspace_writable(plan):
    out = []
    for task in _tasks(plan):
        tid = task.get('task', '<missing>')
        for arm, data in sorted(_arms(task).items()):
            if not isinstance(data, dict):
                continue
            output = data.get('output')
            if not isinstance(output, dict) or output.get('readOnly') is not False:
                out.append(_finding(tid, arm, 'artifact output is not writable'))
            writable = [norm(p) for p in data.get('workspaceWritable') or []]
            if not writable:
                continue
            mounts = _mounts(data)
            fixture = next((m for m in mounts if m.get('kind') == 'fixture'), None)
            fixture_source = norm(fixture.get('source', '')) if fixture else ''
            fixture_rw = bool(fixture) and fixture.get('readOnly') is False
            for path in writable:
                if fixture_rw:
                    continue
                covered = False
                for mount in mounts:
                    if mount.get('readOnly') is not False:
                        continue
                    source = norm(mount.get('source', ''))
                    if fixture_source and source.startswith(fixture_source + '/'):
                        rel = source[len(fixture_source) + 1:]
                        if path == rel or path.startswith(rel + '/'):
                            covered = True
                    elif source and (path == source or path.startswith(source + '/')):
                        covered = True
                if not covered:
                    out.append(_finding(tid, arm, f'workspace path is not writable: {path}'))
    return out


def check_output_independent(plan):
    out = []
    for task in _tasks(plan):
        tid = task.get('task', '<missing>')
        for arm, data in sorted(_arms(task).items()):
            if not isinstance(data, dict):
                continue
            output = data.get('output') or {}
            material_source = norm((data.get('material') or {}).get('source', ''))
            output_source = norm(output.get('source', ''))
            output_target = norm(output.get('target', ''))
            if output_source and material_source and (
                    output_source == material_source
                    or output_source.startswith(material_source + '/')
                    or material_source.startswith(output_source + '/')):
                out.append(_finding(tid, arm, 'artifact output overlaps the material mount'))
            if output_target.startswith('/app/materials') or output_target.startswith('/app/fixture'):
                out.append(_finding(tid, arm, f'artifact output target is inside a read-only mount: {output_target}'))
        # output must be its own mount
        for arm, data in sorted(_arms(task).items()):
            if not isinstance(data, dict):
                continue
            kinds = {m.get('kind') for m in _mounts(data)}
            if 'output' not in kinds:
                out.append(_finding(tid, arm, 'artifact output is not an independent mount'))
    return out


def check_symlink_escape(plan):
    out = []
    for task in _tasks(plan):
        tid = task.get('task', '<missing>')
        for arm, data in sorted(_arms(task).items()):
            for entry in _entries(data):
                if entry.get('link') and _link_escapes(entry):
                    out.append(_finding(
                        tid, arm,
                        f'symlink escapes the material root: {entry.get("path")} -> {entry.get("link")}'))
    return out


def check_relative_traversal(plan):
    out = []
    for task, arm, kind, path in _iter_paths(plan):
        if '..' in _segments(path):
            out.append(_finding(task, arm, f'relative traversal in {kind}: {path}'))
    return out


def check_absolute_escape(plan):
    out = []
    for task in _tasks(plan):
        tid = task.get('task', '<missing>')
        for arm, data in sorted(_arms(task).items()):
            if not isinstance(data, dict):
                continue
            for entry in _entries(data):
                path = norm(entry.get('path', ''))
                if path and _host_absolute(path):
                    out.append(_finding(tid, arm, f'absolute material path is not confined: {path}'))
            for mount in _mounts(data):
                source = norm(mount.get('source', ''))
                if source and _host_absolute(source):
                    out.append(_finding(tid, arm, f'absolute host path in mount source: {source}'))
                if '..' in _segments(norm(mount.get('target', ''))):
                    out.append(_finding(tid, arm, f'traversal in mount target: {mount.get("target")}'))
            for key in ('source',):
                value = norm((data.get('material') or {}).get(key, ''))
                if value and _host_absolute(value):
                    out.append(_finding(tid, arm, f'absolute host path in material source: {value}'))
    return out


def check_output_confinement(plan):
    out = []
    for task in _tasks(plan):
        tid = task.get('task', '<missing>')
        for arm, data in sorted(_arms(task).items()):
            if not isinstance(data, dict):
                continue
            output = data.get('output') or {}
            target = norm(output.get('target', ''))
            expected = f'/app/agent-output/{tid}'
            if target != expected:
                out.append(_finding(tid, arm, f'output target is not confined to {expected}: {target}'))
            if target.startswith('/app/materials') or target.startswith('/app/fixture'):
                out.append(_finding(tid, arm, f'output target overlaps a read-only mount: {target}'))
            source = norm(output.get('source', ''))
            if '..' in _segments(source):
                out.append(_finding(tid, arm, f'output source traverses out of its root: {source}'))
    return out


def check_inventory_pinned(plan):
    out = []
    inventory = plan.get('inventory')
    if not isinstance(inventory, dict):
        return out
    pinned = set(inventory.get('pinnedTasks') or [])
    for task in _tasks(plan):
        tid = task.get('task') if isinstance(task, dict) else None
        if tid and pinned and tid not in pinned:
            out.append(_finding(tid, '-', 'task is not in the pinned candidate inventory'))
    for tid in inventory.get('unpinnedLiveTasks') or []:
        if tid in {t.get('task') for t in _tasks(plan) if isinstance(t, dict)}:
            out.append(_finding(tid, '-', 'unpinned living-benchmark task entered the plan'))
    return out


def check_duplicate_material(plan):
    out = []
    for task in _tasks(plan):
        tid = task.get('task', '<missing>')
        arm_map = _arms(task)
        sources = {}
        for arm, data in sorted(arm_map.items()):
            if not isinstance(data, dict):
                continue
            source = norm((data.get('material') or {}).get('source', ''))
            if source:
                if source in sources:
                    out.append(_finding(tid, arm, f'condition shares a material root with {sources[source]}: {source}'))
                sources[source] = arm
            hashes = {}
            for entry in _entries(data):
                digest = entry.get('sha256')
                if not digest:
                    continue
                if digest in hashes:
                    out.append(_finding(
                        tid, arm,
                        f'duplicate material bytes: {entry.get("path")} == {hashes[digest]}'))
                hashes[digest] = entry.get('path')
    return out


MATERIAL_ALLOWED = {
    'A': ('ENTRY.md',),
    'B': ('ENTRY.md', 'guidance.md'),
    'C': ('ENTRY.md', 'fact-supplement.md'),
    'D': ('ENTRY.md', 'guidance.md', 'fact-supplement.md'),
}


def check_unexpected_material(plan):
    out = []
    for task in _tasks(plan):
        tid = task.get('task', '<missing>')
        for arm, data in sorted(_arms(task).items()):
            allowed = MATERIAL_ALLOWED.get(arm)
            if not allowed:
                continue
            for entry in _entries(data):
                path = norm(entry.get('path', ''))
                if path in allowed or path.startswith('references/'):
                    continue
                out.append(_finding(tid, arm, f'unexpected material file: {path}'))
    return out


def check_hardlink_alias(plan):
    out = []
    for task in _tasks(plan):
        tid = task.get('task', '<missing>')
        for arm, data in sorted(_arms(task).items()):
            for entry in _entries(data):
                if entry.get('hardlinkShared') is True:
                    out.append(_finding(
                        tid, arm,
                        f'material file has extra hard links outside the mount: {entry.get("path")}'))
    return out


CHECKS = (
    ('mount-manifest', 'per-condition mount manifest exists and is well-formed', check_mount_manifest),
    ('arm-a-disclosure', 'A exposes no B/C/D guidance or reference material', check_arm_a_disclosure),
    ('arm-b-reference-isolation', 'B exposes no C/D reference set', check_arm_b_reference_isolation),
    ('cd-shared-bytes', 'C and D share byte-identical facts and reference bytes', check_cd_shared_bytes),
    ('d-guidance-only-delta', 'D adds only the adapted procedure material beyond C', check_d_guidance_only_delta),
    ('solution-leak', 'no solution material is visible in any arm', check_solution_leak),
    ('judge-leak', 'task tests and judge internals are not visible', check_judge_leak),
    ('results-leak', 'benchmark results are not visible', check_results_leak),
    ('cross-arm-output', 'no other-condition output is visible', check_cross_arm_output),
    ('native-skill-leak', 'native skill directories are not visible', check_native_skill_leak),
    ('agents-skills-mount', '~/.agents/skills is not mounted or readable', check_agents_skills_mount),
    ('host-config-mount', 'private host config is not mounted', check_host_config_mount),
    ('credential-env', 'credential environment variables do not enter the cell', check_credential_env),
    ('material-readonly', 'material mounts are read-only', check_material_readonly),
    ('workspace-writable', 'the task workspace and artifact output are writable', check_workspace_writable),
    ('output-independent', 'artifact output is a separate independent path', check_output_independent),
    ('symlink-escape', 'symlinks inside materials cannot escape the mount root', check_symlink_escape),
    ('relative-traversal', '../ traversal is rejected', check_relative_traversal),
    ('absolute-escape', 'absolute-path escape is rejected', check_absolute_escape),
    ('output-confinement', 'artifact output is confined to its own directory', check_output_confinement),
    ('inventory-pinned', 'only pinned candidate-inventory tasks are accepted', check_inventory_pinned),
    ('duplicate-material', 'each condition has its own distinct material set', check_duplicate_material),
    ('unexpected-material', 'each arm exposes only its allowed material files', check_unexpected_material),
    ('hardlink-alias', 'hard links do not alias files outside the material mount', check_hardlink_alias),
)


def run_checks(plan):
    results = []
    for check_id, title, fn in CHECKS:
        try:
            findings = fn(plan) or []
        except Exception as exc:  # pragma: no cover - defensive, surfaced as a failure
            findings = [_finding('<plan>', '-', f'{check_id} raised: {type(exc).__name__}')]
        findings = sorted(findings, key=lambda f: (f.get('task', ''), f.get('arm', ''), f.get('detail', '')))
        results.append({
            'id': check_id,
            'title': title,
            'status': 'passed' if not findings else 'failed',
            'findings': findings,
        })
    results.sort(key=lambda r: r['id'])
    return results


# --------------------------------------------------------------------------- #
# Optional container canary
# --------------------------------------------------------------------------- #

CANARY_IMAGE_CANDIDATES = (
    'node:24-bookworm',
    'node:22-bookworm',
    'debian:bookworm-slim',
    'alpine:latest',
    'busybox:latest',
)

PROBE_SH = r'''
echo "HOME=${HOME:-}"
echo "NATIVE_SKILLS=${STUDY_NATIVE_SKILLS:-unset}"
echo "NETWORK=none"
echo "SECRET_ENV_BEGIN"
env | sort | grep -Ei 'API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL' || true
echo "SECRET_ENV_END"
echo "FIND_BEGIN"
find / -xdev -maxdepth 4 2>/dev/null | sort
echo "FIND_END"
if command -v readlink >/dev/null 2>&1; then
  echo "READLINK_MATERIALS=$(readlink -f /app/materials 2>/dev/null || echo unknown)"
else
  echo "READLINK_MATERIALS=unavailable"
fi
if ( echo probe >> /app/materials/ENTRY.md ) 2>/dev/null; then
  echo "MATERIAL_READONLY=0"
else
  echo "MATERIAL_READONLY=1"
fi
if ( echo probe > /app/agent-output/probe.txt ) 2>/dev/null; then
  echo "OUTPUT_WRITABLE=1"
else
  echo "OUTPUT_WRITABLE=0"
fi
echo "STAT_MATERIALS=$(stat -c %a /app/materials 2>/dev/null || stat -f %Lp /app/materials 2>/dev/null || echo unknown)"
echo "ISOLATION_PROBE_DONE=1"
'''.lstrip()


def _docker(runner, args, timeout=30):
    try:
        return runner(['docker', *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, exc
    except TypeError:
        return runner(['docker', *args])


def docker_available(runner=subprocess.run):
    result = _docker(runner, ['info', '--format', '{{.ServerVersion}}'], timeout=15)
    if isinstance(result, tuple):
        return False, 'docker daemon unavailable'
    return (result.returncode == 0), ('docker daemon unavailable' if result.returncode else '')


def probe_local_image(runner=subprocess.run, candidates=CANARY_IMAGE_CANDIDATES):
    for image in candidates:
        result = _docker(runner, ['image', 'inspect', '--format', '{{.Id}}', image], timeout=15)
        if not isinstance(result, tuple) and result.returncode == 0:
            return image
    return None


def build_canary_stage(cells, tid, arm, destination=None):
    """Write a single-cell fixture for the container probe; returns the stage path."""
    stage = Path(destination or tempfile.mkdtemp(prefix='study-iso-canary-'))
    materials = stage / 'materials'
    materials.mkdir(parents=True)
    for path, data in sorted(cells[tid][arm].items()):
        target = materials / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (stage / 'fixture').mkdir(parents=True, exist_ok=True)
    (stage / 'fixture' / 'README.md').write_text('study-v1 isolation canary fixture\n')
    (stage / 'instruction.md').write_text('canary cell: no solver model is invoked\n')
    (stage / 'output').mkdir(parents=True, exist_ok=True)
    (stage / 'probe.sh').write_text(PROBE_SH)
    return stage


def canary_command(stage, image):
    return [
        'docker', 'run', '--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges', '--user', '1000:1000', '--pids-limit', '128',
        '--memory', '512m', '--cpus', '1', '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m',
        '--tmpfs', '/home/study:rw,nosuid,nodev,uid=1000,gid=1000,mode=700',
        '-e', 'HOME=/home/study', '-e', 'STUDY_NATIVE_SKILLS=disabled',
        '--mount', f'type=bind,src={stage}/materials,dst=/app/materials,readonly',
        '--mount', f'type=bind,src={stage}/fixture,dst=/app/fixture,readonly',
        '--mount', f'type=bind,src={stage}/instruction.md,dst=/app/instruction.md,readonly',
        '--mount', f'type=bind,src={stage}/output,dst=/app/agent-output',
        '--mount', f'type=bind,src={stage}/probe.sh,dst=/probe.sh,readonly',
        '--entrypoint', 'sh', image, '/probe.sh',
    ]


def interpret_canary(stdout):
    """Return (violations, observations) from a probe transcript."""
    violations, observations = [], {}
    for key in ('MATERIAL_READONLY', 'OUTPUT_WRITABLE'):
        match = re.search(rf'^{key}=(\S+)$', stdout, re.M)
        observations[key.lower()] = match.group(1) if match else None
    if observations.get('material_readonly') != '1':
        violations.append('material mount was writable inside the container')
    if observations.get('output_writable') != '1':
        violations.append('artifact output was not writable inside the container')
    secret_block = re.search(r'SECRET_ENV_BEGIN\n(.*?)SECRET_ENV_END', stdout, re.S)
    if secret_block and secret_block.group(1).strip():
        violations.append('credential environment variable visible inside the container')
    find_block = re.search(r'FIND_BEGIN\n(.*?)FIND_END', stdout, re.S)
    if find_block:
        for line in find_block.group(1).splitlines():
            text = line.strip()
            if not text:
                continue
            if _token_hit(text, HOST_CONFIG_TOKENS):
                violations.append(f'host config visible inside the container: {text}')
                break
    observations['readlinkMaterials'] = _match_value(stdout, 'READLINK_MATERIALS')
    observations['statMaterials'] = _match_value(stdout, 'STAT_MATERIALS')
    if not re.search(r'^ISOLATION_PROBE_DONE=1$', stdout, re.M):
        violations.append('container probe did not complete')
    return violations, observations


def _match_value(stdout, key):
    match = re.search(rf'^{key}=(\S+)$', stdout, re.M)
    return match.group(1) if match else None


def docker_canary(cells, tid, arm, image=None, runner=subprocess.run, timeout=90):
    """Run the opt-in container canary; never pulls an image and never guesses."""
    available, reason = docker_available(runner)
    if not available:
        return {'status': 'not-run', 'requested': True, 'reason': reason,
                'dockerAvailable': False, 'image': None, 'violations': [], 'observations': {}}
    selected = image or probe_local_image(runner)
    if not selected:
        return {'status': 'not-run', 'requested': True,
                'reason': 'no local canary image present and network pulls are disabled',
                'dockerAvailable': True, 'image': None, 'violations': [], 'observations': {}}
    stage = build_canary_stage(cells, tid, arm)
    try:
        try:
            result = runner(canary_command(stage, selected), capture_output=True, text=True, timeout=timeout)
        except TypeError:
            result = runner(canary_command(stage, selected))
        except (OSError, subprocess.SubprocessError) as exc:
            return {'status': 'not-run', 'requested': True, 'dockerAvailable': True,
                    'reason': f'container canary could not start: {type(exc).__name__}',
                    'image': selected, 'violations': [], 'observations': {}}
        stdout = result.stdout or ''
        violations, observations = interpret_canary(stdout)
        status = 'passed' if result.returncode == 0 and not violations else 'failed'
        reason = 'boundary verified inside the container' if status == 'passed' else \
            'container probe reported: ' + '; '.join(violations or [f'exit {result.returncode}'])
        return {'status': status, 'requested': True, 'reason': reason,
                'dockerAvailable': True, 'image': selected, 'violations': violations,
                'observations': observations, 'exitCode': result.returncode}
    finally:
        shutil.rmtree(stage, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Report assembly and CLI
# --------------------------------------------------------------------------- #

BOUNDARY_MODEL = {
    'materialMount': '/app/materials (read-only, one arm only)',
    'fixtureMount': '/app/fixture (per-task write policy)',
    'instruction': '/app/instruction.md (read-only)',
    'artifactOutput': '/app/agent-output/<task> (writable, independent)',
    'home': '/home/study (empty tmpfs)',
    'network': 'none',
    'nativeSkills': 'catalog disabled; ~/.agents/skills not mounted',
    'notMounted': ['solutions', 'task tests/judge', 'benchmark results',
                   'other-condition material/output', 'host config', 'credentials'],
}


def run_preflight(task_ids=None, arms=ARMS, material_root=None, canary_requested=False,
                  image=None, runner=subprocess.run):
    """Build the mount plan, run every check, and return the deterministic report."""
    selected_arms = tuple(arms or ARMS)
    unknown = [a for a in selected_arms if a not in ARMS]
    if unknown:
        raise UsageError('unknown condition arm(s): ' + ','.join(unknown))
    if material_root is not None:
        plan, cells = build_plan_from_material_root(material_root, task_ids, selected_arms)
    else:
        plan, cells = build_plan_from_authority(task_ids, selected_arms)
    errors = validate_plan_shape(plan)
    if errors:
        raise UsageError('malformed material mount plan: ' + '; '.join(errors))
    # Cross-condition checks always need the full A/B/C/D plan; --arm only narrows
    # the reported condition list and selects the container canary cell.
    plan['selectedArms'] = list(selected_arms)
    canary = {'status': 'not-run', 'requested': bool(canary_requested),
              'reason': 'offline plan only; --docker-canary not requested',
              'dockerAvailable': False, 'image': None, 'violations': [], 'observations': {}}
    if canary_requested:
        task0 = plan['tasks'][0]['task'] if plan['tasks'] else PILOT_TASKS[0]
        arm0 = selected_arms[0] if selected_arms else 'A'
        if arm0 not in cells.get(task0, {}):
            raise UsageError(f'condition arm has no material cell for {task0}: {arm0}')
        canary = docker_canary(cells, task0, arm0, image=image, runner=runner)
    plan['runtimeCanary'] = canary
    checks = run_checks(plan)
    failed = [c for c in checks if c['status'] != 'passed']
    violations = [{'check': c['id'], **f} for c in failed for f in c['findings']]
    report = {
        'schemaVersion': REPORT_SCHEMA_VERSION,
        'study': plan.get('study'),
        'mode': 'docker-canary' if canary_requested else 'plan-only',
        'materialSource': plan.get('materialSource'),
        'materialRevision': plan.get('materialRevision'),
        'tasks': sorted(t.get('task') for t in plan['tasks']),
        'arms': list(selected_arms),
        'runtimeCanaryStatus': canary['status'],
        'runtimeCanary': canary,
        'boundary': BOUNDARY_MODEL,
        'inventory': plan.get('inventory'),
        'checks': checks,
        'summary': {
            'total': len(checks),
            'passed': len(checks) - len(failed),
            'failed': len(failed),
            'violations': violations,
        },
        'ok': not failed and canary['status'] != 'failed',
        'limitations': [
            'offline plan checks are not container-verified isolation',
            'no solver model is called and no token/cost is measured',
            f'runtimeCanaryStatus={canary["status"]}',
        ],
    }
    return report, plan


def exit_code_for(report):
    """0 = no violation; 1 = violation or an explicitly requested canary that did not run."""
    if report['summary']['failed']:
        return 1
    canary = report.get('runtimeCanary') or {}
    if canary.get('requested') and canary.get('status') in ('failed', 'not-run'):
        return 1
    return 0


def render_text(report):
    lines = [
        f"study-v1 isolation preflight ({report['mode']})",
        f"materialSource: {report['materialSource']}  revision: {report['materialRevision']}",
        f"runtimeCanaryStatus: {report['runtimeCanaryStatus']} ({report['runtimeCanary'].get('reason')})",
        f"tasks: {', '.join(report['tasks'])}",
        f"checks: {report['summary']['total']} total, {report['summary']['passed']} passed, "
        f"{report['summary']['failed']} failed",
    ]
    for check in report['checks']:
        lines.append(f"  [{'ok' if check['status'] == 'passed' else 'FAIL'}] {check['id']}")
        for finding in check['findings']:
            lines.append(f"        {finding['task']}/{finding['arm']}: {finding['detail']}")
    lines.append('RESULT: ' + ('ok' if report['ok'] else 'VIOLATIONS FOUND'))
    lines.append('note: a passing offline plan is NOT container-verified isolation')
    return '\n'.join(lines)


def _parse_tasks(value, pinned):
    if not value:
        return sorted(PILOT_TASKS)
    requested = [t.strip() for t in value.split(',') if t.strip()]
    for task in requested:
        if task not in pinned:
            raise UsageError(f'unknown task (not in the pinned 56-task inventory): {task}')
    return sorted(set(requested))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', help='comma-separated task id(s); default: the 4 pilot tasks')
    parser.add_argument('--arm', help='comma-separated condition arm(s) to report; default: A,B,C,D')
    parser.add_argument('--material-root', help='synthetic <root>/<task>/<arm>/ fixture tree')
    parser.add_argument('--json', action='store_true', help='emit the deterministic JSON report')
    parser.add_argument('--check', action='store_true',
                        help='assert the exit-code contract explicitly (failures always gate)')
    parser.add_argument('--plan-only', action='store_true', help='offline plan (default)')
    parser.add_argument('--docker-canary', action='store_true', help='opt-in real container canary')
    parser.add_argument('--image', help='local image for the container canary (no pulls)')
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        if args.plan_only and args.docker_canary:
            raise UsageError('--plan-only and --docker-canary are mutually exclusive')
        pinned = set()
        if args.material_root is None:
            config = json.loads((STUDY / 'config.json').read_text())
            inventory = json.loads(prepare.blob(config['sourceCommit'], config['candidateInventory']))
            pinned = {t['id'] for t in inventory['tasks']}
        tasks = _parse_tasks(args.task, pinned) if pinned else \
            ([t.strip() for t in args.task.split(',') if t.strip()] if args.task else None)
        arms = tuple(a.strip() for a in (args.arm or ','.join(ARMS)).split(',') if a.strip())
        unknown = [a for a in arms if a not in ARMS]
        if unknown:
            raise UsageError('unknown condition arm(s): ' + ','.join(unknown))
        if args.material_root is not None and not Path(args.material_root).is_dir():
            raise UsageError('--material-root is not a directory')
        report, _ = run_preflight(
            task_ids=tasks, arms=arms, material_root=args.material_root,
            canary_requested=args.docker_canary, image=args.image)
    except UsageError as exc:
        print(f'usage error: {redact_text(str(exc))}', file=sys.stderr)
        return 2
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f'config error: {redact_text(str(exc))}', file=sys.stderr)
        return 2
    if args.json:
        sys.stdout.write(serialize_report(report))
    else:
        print(render_text(report))
    # --check is the explicit CI form of this always-on contract.
    _ = args.check
    return exit_code_for(report)


if __name__ == '__main__':
    sys.exit(main())
