"""Focused, model-free tests for the study-v1 material isolation preflight.

Every test exercises one boundary check or one CLI/determinism contract over a
synthetic material mount plan. No solver model, network, Docker daemon or
third-party package is required.
"""
import copy
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'study_isolation', Path(__file__).with_name('check-study-v1-isolation.py'))
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

BASE_FILES = {
    'A': {'ENTRY.md': b'# A entry\nNo migration material is supplied.\n'},
    'B': {
        'ENTRY.md': b'# B entry\nGuidance: guidance.md\n',
        'guidance.md': b'# generic migration procedure\n\nstep 1\n',
    },
    'C': {
        'ENTRY.md': b'# C entry\nReference index.\n',
        'references/r1.md': b'# reference one\n\nfact one\n',
        'fact-supplement.md': b'# shared facts\n\nfact two\n',
    },
    'D': {
        'ENTRY.md': b'# D entry\nGuidance: guidance.md\nReference index.\n',
        'guidance.md': b'# adapted migration procedure\n\nstep 1\n',
        'references/r1.md': b'# reference one\n\nfact one\n',
        'fact-supplement.md': b'# shared facts\n\nfact two\n',
    },
}


def write_tree(root, files=None, task='T1'):
    """Materialize a synthetic ``<root>/<task>/<arm>/...`` tree."""
    for arm, entries in (files or BASE_FILES).items():
        for rel, data in entries.items():
            target = root / task / arm / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return root


def entry(path, data=b'x', entry_type='file', **extra):
    record = {
        'path': path, 'type': entry_type,
        'sha256': tool.sha(data) if entry_type == 'file' else None,
        'bytes': len(data), 'link': None, 'linkResolved': None,
        'escapesRoot': False, 'hardlinkShared': False,
    }
    record.update(extra)
    return record


class FakeResult:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeRunner:
    """Deterministic stand-in for subprocess.run; never touches Docker."""

    def __init__(self, info_rc=0, image_rc=0, run_rc=0, run_stdout=''):
        self.info_rc = info_rc
        self.image_rc = image_rc
        self.run_rc = run_rc
        self.run_stdout = run_stdout
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        if args[1] == 'info':
            return FakeResult(self.info_rc, '27.0', '')
        if args[1] == 'image':
            return FakeResult(self.image_rc, 'sha256:deadbeef', '')
        return FakeResult(self.run_rc, self.run_stdout, '')

    def command(self, verb):
        return next(call for call in self.calls if call[1] == verb)


CANARY_OK_STDOUT = (
    'HOME=/home/study\n'
    'NATIVE_SKILLS=disabled\n'
    'SECRET_ENV_BEGIN\nSECRET_ENV_END\n'
    'FIND_BEGIN\n/app\n/app/materials\n/app/agent-output\nFIND_END\n'
    'READLINK_MATERIALS=/app/materials\n'
    'MATERIAL_READONLY=1\n'
    'OUTPUT_WRITABLE=1\n'
    'STAT_MATERIALS=555\n'
    'ISOLATION_PROBE_DONE=1\n'
)


class StudyIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temporary = tempfile.TemporaryDirectory()
        cls.root = write_tree(Path(cls._temporary.name) / 'materials')
        cls.plan, cls.cells = tool.build_plan_from_material_root(cls.root, ['T1'])

    @classmethod
    def tearDownClass(cls):
        cls._temporary.cleanup()

    # -- helpers ----------------------------------------------------------- #
    def fresh_plan(self):
        return copy.deepcopy(self.plan)

    def fresh_tree(self, files=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = write_tree(Path(directory.name) / 'materials', files)
        plan, _ = tool.build_plan_from_material_root(root, ['T1'])
        return root, plan

    def findings(self, plan, check_id):
        for result in tool.run_checks(plan):
            if result['id'] == check_id:
                return result['findings']
        raise AssertionError(f'check not registered: {check_id}')

    def arm(self, plan, name='C'):
        return plan['tasks'][0]['arms'][name]

    # -- baseline / authority --------------------------------------------- #
    def test_synthetic_baseline_passes_every_check(self):
        results = tool.run_checks(self.plan)
        failed = [r['id'] for r in results if r['status'] != 'passed']
        self.assertEqual(failed, [], results)

    def test_authority_plan_for_pilot_tasks_passes_every_check(self):
        plan, cells = tool.build_plan_from_authority(tool.PILOT_TASKS)
        self.assertEqual(sorted(cells), sorted(tool.PILOT_TASKS))
        failed = [r['id'] for r in tool.run_checks(plan) if r['status'] != 'passed']
        self.assertEqual(failed, [])
        self.assertTrue(plan['tasks'])
        self.assertFalse(json.loads((tool.STUDY / 'config.json').read_text())['formalRunAllowed'])

    def test_check_registry_covers_required_boundaries(self):
        ids = {check_id for check_id, _, _ in tool.CHECKS}
        required = {
            'mount-manifest', 'arm-a-disclosure', 'arm-b-reference-isolation',
            'cd-shared-bytes', 'd-guidance-only-delta', 'solution-leak', 'judge-leak',
            'results-leak', 'cross-arm-output', 'native-skill-leak', 'agents-skills-mount',
            'host-config-mount', 'credential-env', 'material-readonly',
            'workspace-writable', 'output-independent', 'symlink-escape',
            'relative-traversal', 'absolute-escape', 'output-confinement',
        }
        self.assertTrue(required <= ids, required - ids)
        self.assertGreaterEqual(len(ids), 20)

    # -- 1 mount manifest -------------------------------------------------- #
    def test_missing_arm_is_reported_by_manifest_check(self):
        plan = self.fresh_plan()
        del plan['tasks'][0]['arms']['B']
        findings = self.findings(plan, 'mount-manifest')
        self.assertTrue(any('missing condition arms: B' in f['detail'] for f in findings))

    def test_missing_arm_directory_fails_manifest_and_guidance(self):
        files = {arm: value for arm, value in BASE_FILES.items() if arm != 'D'}
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = write_tree(Path(directory.name) / 'materials', files)
        plan, _ = tool.build_plan_from_material_root(root, ['T1'])
        manifest = self.findings(plan, 'mount-manifest')
        self.assertTrue(any('no files' in f['detail'] for f in manifest))
        self.assertTrue(self.findings(plan, 'd-guidance-only-delta'))

    def test_missing_mount_is_reported(self):
        plan = self.fresh_plan()
        self.arm(plan)['mounts'] = [m for m in self.arm(plan)['mounts'] if m['kind'] != 'probe']
        findings = self.findings(plan, 'mount-manifest')
        self.assertTrue(any('missing probe mount' in f['detail'] for f in findings))

    def test_extra_mount_is_reported(self):
        plan = self.fresh_plan()
        self.arm(plan)['mounts'].append(
            {'id': 'host', 'kind': 'host', 'source': 'etc', 'target': '/etc', 'readOnly': True})
        findings = self.findings(plan, 'mount-manifest')
        self.assertTrue(any('unexpected mount target' in f['detail'] for f in findings))

    def test_malformed_material_entry_is_reported(self):
        plan = self.fresh_plan()
        self.arm(plan)['material']['entries'].append({'path': 'broken.md'})
        findings = self.findings(plan, 'mount-manifest')
        self.assertTrue(any('sha256' in f['detail'] for f in findings))

    def test_plan_shape_validator_accepts_and_rejects(self):
        self.assertEqual(tool.validate_plan_shape(self.plan), [])
        self.assertTrue(tool.validate_plan_shape({'tasks': []}))
        self.assertTrue(tool.validate_plan_shape({'tasks': [{'task': 'T1'}]}))
        self.assertTrue(tool.validate_plan_shape('not-a-plan'))

    # -- 2 A disclosure ---------------------------------------------------- #
    def test_arm_a_exposes_no_guidance_or_reference(self):
        for plan in (self.plan,):
            self.assertEqual(self.findings(plan, 'arm-a-disclosure'), [])

    def test_arm_a_extra_guidance_file_fails(self):
        plan = self.fresh_plan()
        self.arm(plan, 'A')['material']['entries'].append(entry('guidance.md', b'leak'))
        self.assertTrue(self.findings(plan, 'arm-a-disclosure'))

    def test_arm_a_accidental_entry_guidance_fails(self):
        plan = self.fresh_plan()
        leaked = self.arm(plan, 'C')['material']['entries'][-1]
        a_entry = self.arm(plan, 'A')['material']['entries'][0]
        a_entry['sha256'] = leaked['sha256']
        findings = self.findings(plan, 'arm-a-disclosure')
        self.assertTrue(any('byte-identical' in f['detail'] for f in findings))

    # -- 3 B reference isolation ------------------------------------------ #
    def test_arm_b_has_no_reference_set(self):
        self.assertEqual(self.findings(self.plan, 'arm-b-reference-isolation'), [])

    def test_arm_b_reference_leak_fails(self):
        plan = self.fresh_plan()
        self.arm(plan, 'B')['material']['entries'].append(entry('references/r1.md', b'# reference one\n\nfact one\n'))
        findings = self.findings(plan, 'arm-b-reference-isolation')
        self.assertTrue(any('reference set' in f['detail'] for f in findings))

    def test_arm_b_content_bleed_fails(self):
        plan = self.fresh_plan()
        reference = next(e for e in self.arm(plan, 'C')['material']['entries']
                         if e['path'].startswith('references/'))
        guidance = next(e for e in self.arm(plan, 'B')['material']['entries']
                        if e['path'] == 'guidance.md')
        guidance['sha256'] = reference['sha256']
        findings = self.findings(plan, 'arm-b-reference-isolation')
        self.assertTrue(any('byte-identical' in f['detail'] for f in findings))

    # -- 4 C/D shared bytes ----------------------------------------------- #
    def test_cd_share_byte_identical_facts(self):
        self.assertEqual(self.findings(self.plan, 'cd-shared-bytes'), [])

    def test_cd_shared_byte_mismatch_fails(self):
        plan = self.fresh_plan()
        reference = next(e for e in self.arm(plan, 'D')['material']['entries']
                         if e['path'].startswith('references/'))
        reference['sha256'] = tool.sha(b'mutated')
        findings = self.findings(plan, 'cd-shared-bytes')
        self.assertTrue(any('bytes differ' in f['detail'] for f in findings))

    def test_cd_missing_shared_supplement_fails(self):
        plan = self.fresh_plan()
        self.arm(plan, 'D')['material']['entries'] = [
            e for e in self.arm(plan, 'D')['material']['entries']
            if e['path'] != 'fact-supplement.md']
        plan['tasks'][0]['sharedFactSupplement'] = True
        findings = self.findings(plan, 'cd-shared-bytes')
        self.assertTrue(any('supplement is missing' in f['detail'] for f in findings))

    def test_allowed_shared_file_passes(self):
        plan = self.fresh_plan()
        c_ref = next(e for e in self.arm(plan, 'C')['material']['entries']
                     if e['path'].startswith('references/'))
        d_ref = next(e for e in self.arm(plan, 'D')['material']['entries']
                     if e['path'].startswith('references/'))
        self.assertEqual(c_ref['sha256'], d_ref['sha256'])
        self.assertEqual(self.findings(plan, 'cd-shared-bytes'), [])

    def test_empty_material_set_is_handled(self):
        plan = self.fresh_plan()
        for name in ('C', 'D'):
            self.arm(plan, name)['material']['entries'] = [
                e for e in self.arm(plan, name)['material']['entries'] if e['path'] == 'ENTRY.md']
        plan['tasks'][0]['sharedFactSupplement'] = False
        self.assertEqual(self.findings(plan, 'cd-shared-bytes'), [])

    # -- 5 D procedure delta ---------------------------------------------- #
    def test_d_delta_is_exactly_guidance(self):
        self.assertEqual(self.findings(self.plan, 'd-guidance-only-delta'), [])

    def test_d_procedure_missing_fails(self):
        plan = self.fresh_plan()
        self.arm(plan, 'D')['material']['entries'] = [
            e for e in self.arm(plan, 'D')['material']['entries'] if e['path'] != 'guidance.md']
        findings = self.findings(plan, 'd-guidance-only-delta')
        self.assertTrue(any('procedure material is missing' in f['detail'] for f in findings))

    def test_c_containing_guidance_fails(self):
        plan = self.fresh_plan()
        self.arm(plan, 'C')['material']['entries'].append(entry('guidance.md', b'leak'))
        findings = self.findings(plan, 'd-guidance-only-delta')
        self.assertTrue(any('C must not contain guidance.md' in f['detail'] for f in findings))

    def test_d_extra_beyond_guidance_fails(self):
        plan = self.fresh_plan()
        self.arm(plan, 'D')['material']['entries'].append(entry('extra/notes.md', b'extra'))
        findings = self.findings(plan, 'd-guidance-only-delta')
        self.assertTrue(any('extra/notes.md' in f['detail'] for f in findings))

    # -- 6/7/8 leak checks ------------------------------------------------- #
    def test_solution_leak_is_detected(self):
        plan = self.fresh_plan()
        self.arm(plan)['mounts'].append(
            {'id': 'solutions', 'kind': 'mount', 'source': 'solutions/T1',
             'target': '/app/materials/solutions', 'readOnly': True})
        self.assertTrue(any('solution' in f['detail'] for f in self.findings(plan, 'solution-leak')))
        plan2 = self.fresh_plan()
        self.arm(plan2, 'A')['material']['entries'].append(entry('SOLUTION.md', b'answer'))
        self.assertTrue(self.findings(plan2, 'solution-leak'))

    def test_judge_leak_is_detected(self):
        plan = self.fresh_plan()
        self.arm(plan)['mounts'].append(
            {'id': 'tests', 'kind': 'mount', 'source': 'benchmark/tasks/T1/tests',
             'target': '/app/tests', 'readOnly': True})
        self.assertTrue(self.findings(plan, 'judge-leak'))
        plan2 = self.fresh_plan()
        self.arm(plan2)['mounts'].append(
            {'id': 'judge', 'kind': 'mount', 'source': 'fixture/judge-utils.mjs',
             'target': '/app/judge.mjs', 'readOnly': True})
        self.assertTrue(self.findings(plan2, 'judge-leak'))

    def test_results_leak_is_detected(self):
        plan = self.fresh_plan()
        self.arm(plan)['mounts'].append(
            {'id': 'results', 'kind': 'mount', 'source': 'benchmark/results/run.json',
             'target': '/app/results.json', 'readOnly': True})
        self.assertTrue(self.findings(plan, 'results-leak'))

    # -- 9 cross-arm ------------------------------------------------------- #
    def test_cross_arm_material_bleed_is_detected(self):
        plan = self.fresh_plan()
        foreign = plan['tasks'][0]['arms']['D']['material']['source']
        plan['tasks'][0]['arms']['C']['mounts'].append(
            {'id': 'foreign', 'kind': 'mount', 'source': foreign,
             'target': '/app/other', 'readOnly': True})
        self.assertTrue(self.findings(plan, 'cross-arm-output'))

    def test_cross_arm_output_bleed_is_detected(self):
        plan = self.fresh_plan()
        foreign = plan['tasks'][0]['arms']['A']['output']['source']
        plan['tasks'][0]['arms']['B']['mounts'].append(
            {'id': 'foreign', 'kind': 'mount', 'source': foreign,
             'target': '/app/other', 'readOnly': False})
        self.assertTrue(self.findings(plan, 'cross-arm-output'))

    def test_baseline_has_no_cross_arm_visibility(self):
        self.assertEqual(self.findings(self.plan, 'cross-arm-output'), [])

    # -- 10/11 native skills ---------------------------------------------- #
    def test_native_skill_mount_bleed_is_detected(self):
        plan = self.fresh_plan()
        plan['environment']['hostMounts'].append(
            {'id': 'catalog', 'source': 'skills/plugin-upgrade', 'target': '/opt/skills',
             'readOnly': True})
        self.assertTrue(self.findings(plan, 'native-skill-leak'))

    def test_native_skill_autodiscovery_must_be_disabled(self):
        plan = self.fresh_plan()
        plan['environment']['nativeSkills']['autoDiscovery'] = True
        self.assertTrue(self.findings(plan, 'native-skill-leak'))

    def test_agents_skills_directory_is_detected(self):
        plan = self.fresh_plan()
        plan['environment']['hostMounts'].append(
            {'id': 'agents', 'source': '~/.agents/skills', 'target': '/home/study/.agents/skills',
             'readOnly': True})
        self.assertTrue(self.findings(plan, 'agents-skills-mount'))

    def test_agents_skills_target_is_detected(self):
        plan = self.fresh_plan()
        plan['tasks'][0]['arms']['A']['mounts'].append(
            {'id': 'agents', 'kind': 'mount', 'source': 'agents-skills',
             'target': '/home/study/.agents/skills', 'readOnly': True})
        self.assertTrue(self.findings(plan, 'agents-skills-mount'))

    # -- 12 host config ---------------------------------------------------- #
    def test_host_config_mounts_are_detected(self):
        for source in ('~/.codex/config.toml', '~/.ssh/id_rsa', '~/.aws/credentials', '~/.claude/settings.json'):
            plan = self.fresh_plan()
            plan['environment']['hostMounts'].append(
                {'id': 'host', 'source': source, 'target': '/host', 'readOnly': True})
            self.assertTrue(self.findings(plan, 'host-config-mount'), source)

    # -- 13 credentials ---------------------------------------------------- #
    def test_credential_env_is_detected(self):
        plan = self.fresh_plan()
        self.arm(plan, 'A')['env']['OPENAI_API_KEY'] = 'sk-live-secret'
        findings = self.findings(plan, 'credential-env')
        self.assertTrue(any('OPENAI_API_KEY' in f['detail'] for f in findings))

    def test_generic_token_env_is_detected(self):
        plan = self.fresh_plan()
        self.arm(plan, 'C')['env']['CUSTOM_PASSWORD'] = 'hunter2'
        self.assertTrue(self.findings(plan, 'credential-env'))

    def test_null_secret_values_are_allowed(self):
        plan = self.fresh_plan()
        self.arm(plan, 'A')['env']['OPENAI_API_KEY'] = None
        self.assertEqual(self.findings(plan, 'credential-env'), [])

    def test_empty_secret_values_are_allowed(self):
        plan = self.fresh_plan()
        self.arm(plan, 'A')['env']['OPENAI_API_KEY'] = ''
        self.arm(plan, 'A')['env']['GITHUB_TOKEN'] = ''
        self.assertEqual(self.findings(plan, 'credential-env'), [])

    def test_injected_secret_marker_is_detected(self):
        plan = self.fresh_plan()
        plan['environment']['secretsInjected'] = ['OPENAI_API_KEY']
        self.assertTrue(self.findings(plan, 'credential-env'))

    # -- 14/15/16 read-only, writable, independent ------------------------ #
    def test_material_mount_not_read_only_is_detected(self):
        plan = self.fresh_plan()
        self.arm(plan)['material']['readOnly'] = False
        for mount in self.arm(plan)['mounts']:
            if mount['kind'] == 'material':
                mount['readOnly'] = False
        self.assertTrue(self.findings(plan, 'material-readonly'))

    def test_artifact_output_not_writable_is_detected(self):
        plan = self.fresh_plan()
        self.arm(plan)['output']['readOnly'] = True
        self.assertTrue(self.findings(plan, 'workspace-writable'))

    def test_uncovered_workspace_path_is_detected(self):
        plan = self.fresh_plan()
        self.arm(plan)['workspaceWritable'] = ['src']
        self.assertTrue(self.findings(plan, 'workspace-writable'))

    def test_workspace_covered_by_writable_fixture_passes(self):
        plan = self.fresh_plan()
        for arm in plan['tasks'][0]['arms'].values():
            arm['workspaceWritable'] = ['src', 'package.json']
            for mount in arm['mounts']:
                if mount['kind'] == 'fixture':
                    mount['readOnly'] = False
        self.assertEqual(self.findings(plan, 'workspace-writable'), [])

    def test_output_overlapping_material_is_detected(self):
        plan = self.fresh_plan()
        material = self.arm(plan)['material']['source']
        self.arm(plan)['output']['source'] = f'{material}/out'
        self.assertTrue(self.findings(plan, 'output-independent'))

    def test_output_not_a_separate_mount_is_detected(self):
        plan = self.fresh_plan()
        self.arm(plan)['mounts'] = [m for m in self.arm(plan)['mounts'] if m['kind'] != 'output']
        self.assertTrue(self.findings(plan, 'output-independent'))

    # -- 17/18/19 symlink and traversal ----------------------------------- #
    def test_symlink_escaping_material_root_is_rejected(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = write_tree(Path(directory.name) / 'materials')
        os.symlink('/etc/passwd', root / 'T1' / 'C' / 'leak.md')
        plan, _ = tool.build_plan_from_material_root(root, ['T1'])
        findings = self.findings(plan, 'symlink-escape')
        self.assertTrue(any('leak.md' in f['detail'] for f in findings))

    def test_nested_symlink_escape_is_rejected(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = write_tree(Path(directory.name) / 'materials')
        os.symlink('inner', root / 'T1' / 'C' / 'outer')
        os.symlink('/etc', root / 'T1' / 'C' / 'inner')
        plan, _ = tool.build_plan_from_material_root(root, ['T1'])
        findings = self.findings(plan, 'symlink-escape')
        self.assertTrue(any('outer' in f['detail'] for f in findings))

    def test_symlink_inside_material_root_is_allowed(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = write_tree(Path(directory.name) / 'materials')
        os.symlink('references/r1.md', root / 'T1' / 'C' / 'alias.md')
        plan, _ = tool.build_plan_from_material_root(root, ['T1'])
        self.assertEqual(self.findings(plan, 'symlink-escape'), [])

    def test_relative_symlink_traversal_is_rejected(self):
        plan = self.fresh_plan()
        self.arm(plan)['material']['entries'].append(
            entry('escape.md', b'', entry_type='symlink', link='../../../../etc/passwd',
                  linkResolved='../../../../etc/passwd'))
        self.assertTrue(self.findings(plan, 'symlink-escape'))

    def test_hardlink_alias_is_rejected(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        root = write_tree(base / 'materials')
        outside = base / 'outside-secret.md'
        outside.write_bytes(b'private host content')
        os.link(outside, root / 'T1' / 'C' / 'linked.md')
        plan, _ = tool.build_plan_from_material_root(root, ['T1'])
        findings = self.findings(plan, 'hardlink-alias')
        self.assertTrue(any('linked.md' in f['detail'] for f in findings))

    def test_relative_traversal_in_entry_is_rejected(self):
        plan = self.fresh_plan()
        self.arm(plan)['material']['entries'].append(entry('../escape.md', b'x'))
        findings = self.findings(plan, 'relative-traversal')
        self.assertTrue(any('../escape.md' in f['detail'] for f in findings))

    def test_relative_traversal_in_mount_source_is_rejected(self):
        plan = self.fresh_plan()
        self.arm(plan)['mounts'].append(
            {'id': 'escape', 'kind': 'mount', 'source': '../outside',
             'target': '/app/escape', 'readOnly': True})
        self.assertTrue(self.findings(plan, 'relative-traversal'))

    def test_absolute_path_escape_is_rejected(self):
        plan = self.fresh_plan()
        self.arm(plan)['material']['entries'].append(entry('/etc/passwd', b'x'))
        self.assertTrue(self.findings(plan, 'absolute-escape'))

    def test_absolute_mount_source_is_rejected(self):
        plan = self.fresh_plan()
        self.arm(plan)['mounts'].append(
            {'id': 'abs', 'kind': 'mount', 'source': '/etc',
             'target': '/app/abs', 'readOnly': True})
        self.assertTrue(self.findings(plan, 'absolute-escape'))

    def test_windows_path_is_parsed_and_rejected(self):
        plan = self.fresh_plan()
        self.arm(plan)['material']['entries'].append(entry('C:\\Users\\alice\\secret.md', b'x'))
        self.assertTrue(self.findings(plan, 'absolute-escape'))
        self.assertEqual(tool.norm('C:\\Users\\alice'), 'C:/Users/alice')
        self.assertTrue(tool._host_absolute('C:\\Users\\alice'))
        self.assertEqual(tool.redact_path('C:\\Users\\alice'), '<redacted>')

    def test_posix_path_parsing_helpers(self):
        self.assertEqual(tool._segments('a/b/../c'), ['a', 'b', '..', 'c'])
        self.assertEqual(tool._segments('/app/materials/'), ['app', 'materials'])
        self.assertEqual(tool.norm('a\\b\\c'), 'a/b/c')

    # -- 20 output confinement -------------------------------------------- #
    def test_output_target_outside_confinement_is_rejected(self):
        plan = self.fresh_plan()
        self.arm(plan)['output']['target'] = '/app/materials/output'
        self.assertTrue(self.findings(plan, 'output-confinement'))

    def test_output_source_traversal_is_rejected(self):
        plan = self.fresh_plan()
        self.arm(plan)['output']['source'] = '../output'
        self.assertTrue(self.findings(plan, 'output-confinement'))

    def test_baseline_output_is_confined(self):
        self.assertEqual(self.findings(self.plan, 'output-confinement'), [])
        self.assertEqual(self.findings(self.plan, 'output-independent'), [])

    # -- inventory / duplicates / unexpected ------------------------------ #
    def test_inventory_pin_check_rejects_unpinned_task(self):
        plan = self.fresh_plan()
        plan['inventory'] = {'pinnedTasks': ['T1'], 'unpinnedLiveTasks': ['H99-extra']}
        plan['tasks'][0]['task'] = 'H99-extra'
        self.assertTrue(self.findings(plan, 'inventory-pinned'))

    def test_inventory_pin_check_passes_for_pinned_tasks(self):
        plan = self.fresh_plan()
        plan['inventory'] = {'pinnedTasks': ['T1'], 'unpinnedLiveTasks': ['H99-extra']}
        self.assertEqual(self.findings(plan, 'inventory-pinned'), [])

    def test_living_benchmark_extras_are_rejected_by_cli(self):
        config = json.loads((tool.STUDY / 'config.json').read_text())
        inventory = json.loads(tool.prepare.blob(config['sourceCommit'], config['candidateInventory']))
        pinned = {t['id'] for t in inventory['tasks']}
        live = {p.name for p in (tool.ROOT / 'benchmark/tasks').iterdir() if p.is_dir()}
        extras = sorted(live - pinned)
        self.assertTrue(extras, 'living benchmark is expected to have unpinned tasks')
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(tool.main(['--task', extras[0], '--check']), 2)

    def test_duplicate_condition_material_is_rejected(self):
        plan = self.fresh_plan()
        self.arm(plan, 'B')['material']['source'] = self.arm(plan, 'A')['material']['source']
        self.assertTrue(self.findings(plan, 'duplicate-material'))

    def test_duplicate_bytes_within_arm_are_rejected(self):
        plan = self.fresh_plan()
        reference = next(e for e in self.arm(plan, 'C')['material']['entries']
                         if e['path'].startswith('references/'))
        self.arm(plan, 'C')['material']['entries'].append(
            entry('references/copy.md', b'', entry_type='file', sha256=reference['sha256'],
                  bytes=reference['bytes']))
        self.assertTrue(self.findings(plan, 'duplicate-material'))

    def test_unexpected_material_file_is_rejected(self):
        plan = self.fresh_plan()
        self.arm(plan, 'C')['material']['entries'].append(entry('notes.txt', b'x'))
        self.assertTrue(self.findings(plan, 'unexpected-material'))

    def test_baseline_material_files_are_all_allowed(self):
        self.assertEqual(self.findings(self.plan, 'unexpected-material'), [])

    # -- CLI, determinism, redaction -------------------------------------- #
    def test_determinism_is_byte_identical(self):
        first, _ = tool.run_preflight(task_ids=['T1'], material_root=self.root)
        second, _ = tool.run_preflight(task_ids=['T1'], material_root=self.root)
        self.assertEqual(tool.serialize_report(first), tool.serialize_report(second))

    def test_no_timestamp_in_deterministic_report(self):
        report, _ = tool.run_preflight(task_ids=['T1'], material_root=self.root)
        text = tool.serialize_report(report)
        self.assertIsNone(re.search(r'\d{4}-\d{2}-\d{2}', text))
        self.assertNotIn('T00:', text)

    def test_check_results_are_lexically_sorted(self):
        ids = [check['id'] for check in tool.run_checks(self.plan)]
        self.assertEqual(ids, sorted(ids))

    def test_host_paths_are_redacted_in_report(self):
        plan = self.fresh_plan()
        self.arm(plan)['mounts'].append(
            {'id': 'host', 'kind': 'mount', 'source': '/Users/example/private',
             'target': '/app/host', 'readOnly': True})
        results = tool.run_checks(plan)
        text = json.dumps(tool.sanitize({'checks': results}))
        self.assertNotIn('/Users/', text)
        self.assertIn('<redacted>', text)

    def test_redact_helpers(self):
        self.assertEqual(tool.redact_path('/Users/example/file'), '<redacted>')
        self.assertEqual(tool.redact_path('/app/materials'), '/app/materials')
        self.assertEqual(tool.redact_path('benchmark/tasks'), 'benchmark/tasks')
        self.assertIn('<redacted>', tool.redact_text('stderr at /Users/example/secret'))
        self.assertNotIn('/Users/', tool.redact_text('mounted /Users/example/secret'))

    def test_report_satisfies_declared_schema_requirements(self):
        report, _ = tool.run_preflight(task_ids=['T1'], material_root=self.root)
        schema = json.loads(tool.SCHEMA_PATH.read_text())
        self.assertEqual(schema['$schema'], 'https://json-schema.org/draft/2020-12/schema')
        serialized = json.loads(tool.serialize_report(report))
        for key in schema['required']:
            self.assertIn(key, serialized)
        self.assertEqual(serialized['schemaVersion'], schema['properties']['schemaVersion']['const'])
        self.assertGreaterEqual(len(serialized['checks']), 20)
        for check in serialized['checks']:
            for key in schema['properties']['checks']['items']['required']:
                self.assertIn(key, check)
        self.assertIn(serialized['runtimeCanaryStatus'],
                      schema['properties']['runtimeCanaryStatus']['enum'])
        self.assertIn(serialized['mode'], schema['properties']['mode']['enum'])

    def test_report_holds_boundary_and_limitations(self):
        report, _ = tool.run_preflight(task_ids=['T1'], material_root=self.root)
        self.assertEqual(report['arms'], ['A', 'B', 'C', 'D'])
        self.assertIn('network', report['boundary'])
        self.assertTrue(any('not container-verified' in text for text in report['limitations']))
        rendered = tool.render_text(report)
        self.assertIn('NOT container-verified isolation', rendered)
        self.assertNotIn('/Users/', rendered)

    def test_cli_json_plan_succeeds_on_clean_tree(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = tool.main(['--material-root', str(self.root), '--task', 'T1', '--json', '--check'])
        self.assertEqual(code, 0)
        report = json.loads(buffer.getvalue())
        self.assertTrue(report['ok'])
        self.assertEqual(report['runtimeCanaryStatus'], 'not-run')

    def test_cli_check_fails_on_symlink_violation(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = write_tree(Path(directory.name) / 'materials')
        os.symlink('/etc/passwd', root / 'T1' / 'C' / 'leak.md')
        with redirect_stdout(io.StringIO()):
            self.assertEqual(tool.main(['--material-root', str(root), '--task', 'T1', '--check']), 1)

    def test_cli_rejects_missing_material_root(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(tool.main(['--material-root', '/nonexistent/study-root', '--check']), 2)

    def test_cli_rejects_unknown_task(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(tool.main(['--task', 'H404-not-a-task', '--check']), 2)

    def test_cli_rejects_unknown_condition(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(tool.main(['--arm', 'X', '--check']), 2)

    def test_cli_rejects_conflicting_modes(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(tool.main(['--plan-only', '--docker-canary']), 2)

    def test_arm_selection_narrows_report_without_breaking_checks(self):
        report, _ = tool.run_preflight(task_ids=['T1'], arms=('A',), material_root=self.root)
        self.assertEqual(report['arms'], ['A'])
        self.assertTrue(report['ok'], report['summary']['violations'])

    def test_unknown_arm_is_rejected_by_preflight(self):
        with self.assertRaises(tool.UsageError):
            tool.run_preflight(task_ids=['T1'], arms=('X',), material_root=self.root)

    def test_exit_code_helper(self):
        report, _ = tool.run_preflight(task_ids=['T1'], material_root=self.root)
        self.assertEqual(tool.exit_code_for(report), 0)
        failing = {'summary': {'failed': 1}, 'runtimeCanary': {'requested': False}}
        self.assertEqual(tool.exit_code_for(failing), 1)
        unavailable = {'summary': {'failed': 0},
                       'runtimeCanary': {'requested': True, 'status': 'not-run'}}
        self.assertEqual(tool.exit_code_for(unavailable), 1)

    # -- container canary (no Docker required) ---------------------------- #
    def test_default_mode_reports_canary_not_run(self):
        report, _ = tool.run_preflight(task_ids=['T1'], material_root=self.root)
        self.assertEqual(report['runtimeCanaryStatus'], 'not-run')
        self.assertFalse(report['runtimeCanary']['requested'])
        self.assertIn('not requested', report['runtimeCanary']['reason'])

    def test_canary_reports_not_run_when_daemon_unavailable(self):
        report, _ = tool.run_preflight(
            task_ids=['T1'], material_root=self.root, canary_requested=True,
            runner=FakeRunner(info_rc=1))
        self.assertEqual(report['runtimeCanaryStatus'], 'not-run')
        self.assertFalse(report['runtimeCanary']['dockerAvailable'])
        self.assertIn('daemon unavailable', report['runtimeCanary']['reason'])
        self.assertEqual(tool.exit_code_for(report), 1)

    def test_canary_reports_not_run_without_local_image(self):
        report, _ = tool.run_preflight(
            task_ids=['T1'], material_root=self.root, canary_requested=True,
            runner=FakeRunner(info_rc=0, image_rc=1))
        self.assertEqual(report['runtimeCanaryStatus'], 'not-run')
        self.assertIn('no local canary image', report['runtimeCanary']['reason'])

    def test_canary_passes_with_readonly_material_and_writable_output(self):
        runner = FakeRunner(info_rc=0, image_rc=0, run_rc=0, run_stdout=CANARY_OK_STDOUT)
        report, _ = tool.run_preflight(
            task_ids=['T1'], material_root=self.root, canary_requested=True, runner=runner)
        self.assertEqual(report['runtimeCanaryStatus'], 'passed')
        self.assertTrue(report['ok'])
        self.assertEqual(report['runtimeCanary']['observations']['material_readonly'], '1')
        self.assertEqual(tool.exit_code_for(report), 0)

    def test_canary_fails_when_material_is_writable(self):
        stdout = CANARY_OK_STDOUT.replace('MATERIAL_READONLY=1', 'MATERIAL_READONLY=0')
        report, _ = tool.run_preflight(
            task_ids=['T1'], material_root=self.root, canary_requested=True,
            runner=FakeRunner(info_rc=0, image_rc=0, run_rc=0, run_stdout=stdout))
        self.assertEqual(report['runtimeCanaryStatus'], 'failed')
        self.assertFalse(report['ok'])
        self.assertEqual(tool.exit_code_for(report), 1)

    def test_canary_rejects_secret_env_and_host_config(self):
        stdout = CANARY_OK_STDOUT.replace(
            'SECRET_ENV_BEGIN\nSECRET_ENV_END', 'SECRET_ENV_BEGIN\nOPENAI_API_KEY=sk\nSECRET_ENV_END')
        stdout = stdout.replace('FIND_BEGIN\n/app\n', 'FIND_BEGIN\n/app\n/home/study/.ssh\n')
        violations, observations = tool.interpret_canary(stdout)
        self.assertTrue(any('credential' in v for v in violations))
        self.assertTrue(any('host config' in v for v in violations))
        self.assertEqual(observations['output_writable'], '1')

    def test_canary_probe_flags_secret_env(self):
        stdout = CANARY_OK_STDOUT.replace('SECRET_ENV_BEGIN\nSECRET_ENV_END',
                                          'SECRET_ENV_BEGIN\nAWS_SECRET_ACCESS_KEY=x\nSECRET_ENV_END')
        violations, _ = tool.interpret_canary(stdout)
        self.assertTrue(violations)

    def test_canary_command_is_hardened(self):
        command = tool.canary_command('/stage', 'alpine:latest')
        self.assertEqual(command[:3], ['docker', 'run', '--rm'])
        for flag in ('--network', '--read-only', '--cap-drop', 'ALL', 'no-new-privileges'):
            self.assertIn(flag, command)
        self.assertIn('HOME=/home/study', command)
        self.assertIn('STUDY_NATIVE_SKILLS=disabled', command)
        mounts = [command[i + 1] for i, token in enumerate(command) if token == '--mount']
        self.assertTrue(any('dst=/app/materials,readonly' in m for m in mounts))
        self.assertFalse(any('dst=/app/materials' in m and 'readonly' not in m for m in mounts))
        self.assertTrue(any('dst=/app/agent-output' in m and 'readonly' not in m for m in mounts))

    def test_image_probe_never_pulls(self):
        runner = FakeRunner(info_rc=0, image_rc=1)
        self.assertIsNone(tool.probe_local_image(runner))
        verbs = {call[1] for call in runner.calls}
        self.assertEqual(verbs, {'image'})
        self.assertNotIn('pull', verbs)

    def test_canary_stage_contains_single_cell(self):
        stage = tool.build_canary_stage(self.cells, 'T1', 'C')
        self.addCleanup(lambda: __import__('shutil').rmtree(stage, ignore_errors=True))
        materials = sorted(p.relative_to(stage / 'materials').as_posix()
                           for p in (stage / 'materials').rglob('*') if p.is_file())
        self.assertEqual(materials, sorted(self.cells['T1']['C']))
        self.assertTrue((stage / 'probe.sh').is_file())
        self.assertFalse((stage / 'D').exists())


if __name__ == '__main__':
    unittest.main()
