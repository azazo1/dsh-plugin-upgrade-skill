"""Focused tests for the read-only study artifact manifest and privacy tool.

Standard library unittest only (pytest is not a project dependency). The hyphenated
script is loaded with importlib, matching paper/scripts/test_study_materials.py.
No model calls, no network.
"""
import getpass
import hashlib
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'manifest_study_artifacts', Path(__file__).with_name('manifest-study-artifacts.py'))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

SCRIPT = str(Path(__file__).with_name('manifest-study-artifacts.py'))
POSIX = os.name == 'posix'
BIG_BYTES = 5 * 1024 * 1024


def write(root, relative, data):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode('utf-8') if isinstance(data, str) else data)
    return path


def manifest_of(root, **kwargs):
    return M.build_manifest(root, **kwargs)


def manifest_path(root, target, **kwargs):
    payload = M.build_manifest(root, **kwargs)
    Path(target).write_bytes(M._render(payload).encode('utf-8'))
    return payload


def run_cli(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)


class ArtifactTestCase(unittest.TestCase):
    def scan_text(self, text, filename='notes.md'):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, filename, text)
            return M.privacy_scan(directory)

    def rules_for(self, text, filename='notes.md'):
        return {finding['rule'] for finding in self.scan_text(text, filename)['findings']}

    def kinds_for(self, text, filename='notes.md'):
        return {finding['kind'] for finding in self.scan_text(text, filename)['findings']}


class ManifestTests(ArtifactTestCase):
    def test_empty_directory_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = manifest_of(directory)
            self.assertEqual(payload['files'], [])
            self.assertEqual(payload['aggregateSha256'], hashlib.sha256(b'').hexdigest())
            self.assertEqual(payload['schemaVersion'], 1)

    def test_single_file_manifest_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', 'hello')
            payload = manifest_of(directory)
            self.assertEqual(len(payload['files']), 1)
            entry = payload['files'][0]
            self.assertEqual(entry, {'path': 'a.txt', 'type': 'file', 'size': 5,
                                     'sha256': hashlib.sha256(b'hello').hexdigest()})

    def test_nested_files_use_relative_posix_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', 'a')
            write(directory, 'sub/b.txt', 'b')
            write(directory, 'sub/deep/c.txt', 'c')
            paths = [entry['path'] for entry in manifest_of(directory)['files']]
            self.assertEqual(paths, ['a.txt', 'sub/b.txt', 'sub/deep/c.txt'])
            for path in paths:
                self.assertFalse(os.path.isabs(path))
                self.assertNotIn('..', path.split('/'))

    def test_manifest_is_deterministic_across_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'b.txt', 'b')
            write(directory, 'a/x.txt', 'x')
            first = M._render(manifest_of(directory))
            write(directory, 'a/y.txt', 'y')  # add then remove to prove content-driven stability
            os.unlink(Path(directory) / 'a/y.txt')
            second = M._render(manifest_of(directory))
            self.assertEqual(first, second)

    def test_manifest_excludes_environment_and_time_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', 'x')
            text = M._render(manifest_of(directory))
            self.assertNotIn(str(Path(directory).resolve()), text)
            self.assertNotIn(os.getcwd(), text)
            self.assertNotIn(socket.gethostname(), text)
            self.assertNotIn(getpass.getuser(), text)
            self.assertIsNone(re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', text))
            self.assertNotIn('generatedAt', text)
            self.assertNotIn('timestamp', text.lower())

    def test_default_root_id_from_directory_name(self):
        self.assertEqual(M.default_root_id('/var/artifacts/study-v1'), 'study-v1')
        self.assertEqual(M.default_root_id('/var/artifacts/study v1/'), 'study-v1')
        self.assertEqual(M.default_root_id('/'), 'root')
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(manifest_of(directory)['rootId'], M.default_root_id(directory))

    def test_explicit_root_id_is_stable_and_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', 'x')
            one = manifest_of(directory, root_id='study-v1-artifacts')
            two = manifest_of(directory, root_id='study-v1-artifacts')
            self.assertEqual(one['rootId'], 'study-v1-artifacts')
            self.assertEqual(one, two)
            self.assertEqual(M.validate_root_id('a.b-c_d0'), 'a.b-c_d0')

    def test_invalid_root_id_rejected(self):
        for value in ('../escape', '/abs', 'has space', 'a/b', '', '.', '..', 'x' * 65):
            with self.assertRaises(M.ArtifactError):
                M.validate_root_id(value)

    def test_paths_sorted_lexically(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('Zebra.txt', 'b.txt', 'a/z.txt', 'a.txt', 'apple.txt'):
                write(directory, name, name)
            paths = [entry['path'] for entry in manifest_of(directory)['files']]
            self.assertEqual(paths, ['Zebra.txt', 'a.txt', 'a/z.txt', 'apple.txt', 'b.txt'])
            self.assertEqual(paths, sorted(paths))

    def test_aggregate_hash_stable_across_different_roots(self):
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            for parent in (left, right):
                write(parent + '/same', 'n.txt', 'x')
                write(parent + '/same', 'sub/m.txt', 'y')
            one = manifest_of(os.path.join(left, 'same'))
            two = manifest_of(os.path.join(right, 'same'))
            self.assertEqual(one['aggregateSha256'], two['aggregateSha256'])
            self.assertEqual(one['rootId'], two['rootId'])
            self.assertEqual(one['files'], two['files'])

    def test_aggregate_hash_changes_with_content(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', 'x')
            before = manifest_of(directory)['aggregateSha256']
            write(directory, 'a.txt', 'y')
            self.assertNotEqual(manifest_of(directory)['aggregateSha256'], before)

    def test_large_file_is_streamed_in_chunks(self):
        payload = bytes(range(256)) * (BIG_BYTES // 256)
        with tempfile.TemporaryDirectory() as directory:
            path = write(directory, 'big.bin', payload)
            digest, size = M.file_digest(path, chunk_size=65536)
            self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
            self.assertEqual(size, len(payload))
            self.assertEqual(M.sha256_stream(path, chunk_size=4096), digest)
            entry = manifest_of(directory)['files'][0]
            self.assertEqual(entry['sha256'], digest)
            self.assertEqual(entry['size'], len(payload))

    def test_binary_file_hash_matches_reference(self):
        payload = bytes(range(256)) * 4
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'binary.dat', payload)
            entry = manifest_of(directory)['files'][0]
            self.assertEqual(entry['sha256'], hashlib.sha256(payload).hexdigest())
            self.assertEqual(entry['size'], len(payload))

    def test_unicode_filename_survives_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'résumé-证明.txt', 'x')
            payload = manifest_of(directory)
            self.assertEqual(payload['files'][0]['path'], 'résumé-证明.txt')
            text = M._render(payload)
            self.assertIn('résumé-证明.txt', text)
            reloaded = json.loads(text)
            self.assertEqual(reloaded['files'][0]['path'], 'résumé-证明.txt')
            self.assertEqual(M._render(manifest_of(directory)), text)

    def test_size_matches_written_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', b'1234567890')
            entry = manifest_of(directory)['files'][0]
            self.assertEqual(entry['size'], 10)

    def test_missing_directory_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(M.ArtifactError):
                manifest_of(os.path.join(directory, 'nope'))


class PolicyTests(ArtifactTestCase):
    def test_dotenv_files_rejected(self):
        for name in ('.env', '.env.local', '.env.production'):
            with tempfile.TemporaryDirectory() as directory:
                write(directory, name, 'A=1')
                with self.assertRaises(M.ArtifactError):
                    manifest_of(directory)

    def test_credential_key_files_rejected(self):
        for name in ('id_rsa', '.netrc', '.npmrc', '.git-credentials', 'credentials.json',
                     'server.pem', 'private.key'):
            with tempfile.TemporaryDirectory() as directory:
                write(directory, name, 'x')
                with self.assertRaises(M.ArtifactError):
                    manifest_of(directory)

    def test_credential_directories_rejected(self):
        for relative in ('.ssh/id_rsa', '.aws/credentials', 'nested/.ssh/config'):
            with tempfile.TemporaryDirectory() as directory:
                write(directory, relative, 'x')
                with self.assertRaises(M.ArtifactError):
                    manifest_of(directory)

    def test_secret_like_filenames_rejected(self):
        for name in ('token-budget.md', 'api_key.json', 'my-secret-plan.md', 'APIKEY.txt'):
            with tempfile.TemporaryDirectory() as directory:
                write(directory, name, 'ordinary prose only')
                with self.assertRaises(M.ArtifactError):
                    manifest_of(directory)

    def test_absolute_path_rejected_in_manifest_paths(self):
        for path in ('/etc/passwd', '/', 'C:/Windows/system32', 'C:\\Windows'):
            with self.assertRaises(M.ArtifactError):
                M.normalize_path(path)

    def test_parent_traversal_rejected(self):
        for path in ('../answer.md', 'a/../../b', '..', 'a/..'):
            with self.assertRaises(M.ArtifactError):
                M.normalize_path(path)

    def test_dot_and_empty_components_rejected(self):
        for path in ('', 'a//b', './a', 'a/.', 'a/', ' padded', 'a/ b '):
            with self.assertRaises(M.ArtifactError):
                M.normalize_path(path)

    def test_backslash_and_drive_paths_rejected(self):
        for path in ('a\\b.txt', 'sub\\c.txt', 'C:relative.txt'):
            with self.assertRaises(M.ArtifactError):
                M.normalize_path(path)

    def test_duplicate_normalized_paths_rejected(self):
        self.assertEqual(M.assert_unique_paths(['a.txt', 'sub/b.txt']), ['a.txt', 'sub/b.txt'])
        for duplicates in (['a.txt', 'a.txt'], ['a/b', 'sub/c', 'a/b']):
            with self.assertRaises(M.ArtifactError):
                M.assert_unique_paths(duplicates)

    def test_case_sensitivity_policy_is_preserved(self):
        self.assertEqual(M.normalize_path('A.txt'), 'A.txt')
        self.assertNotEqual(M.normalize_path('A.txt'), M.normalize_path('a.txt'))
        self.assertEqual(sorted([M.normalize_path('a.txt'), M.normalize_path('A.txt')]), ['A.txt', 'a.txt'])
        with self.assertRaises(M.ArtifactError):
            M.assert_unique_paths(['a.txt', 'a.txt'])

    def test_case_collision_on_case_sensitive_filesystem(self):
        with tempfile.TemporaryDirectory() as probe_dir:
            (Path(probe_dir) / 'CaseProbe').write_bytes(b'x')
            if (Path(probe_dir) / 'caseprobe').exists():
                self.skipTest('filesystem is case-insensitive; case-colliding names are not creatable')
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'A.txt', 'upper')
            write(directory, 'a.txt', 'lower')
            entries = manifest_of(directory)['files']
            self.assertEqual([entry['path'] for entry in entries], ['A.txt', 'a.txt'])
            self.assertNotEqual(entries[0]['sha256'], entries[1]['sha256'])

    def test_fifo_rejected(self):
        if not hasattr(os, 'mkfifo'):
            self.skipTest('os.mkfifo unavailable on this platform')
        with tempfile.TemporaryDirectory() as directory:
            fifo = os.path.join(directory, 'pipe')
            try:
                os.mkfifo(fifo)
            except OSError as exc:
                self.skipTest(f'cannot create FIFO: {exc}')
            with self.assertRaises(M.ArtifactError):
                manifest_of(directory)

    def test_socket_rejected(self):
        if not hasattr(socket, 'AF_UNIX'):
            self.skipTest('AF_UNIX sockets unavailable on this platform')
        directory = tempfile.mkdtemp()
        try:
            path = os.path.join(directory, 'sock')
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                server.bind(path)
            except OSError as exc:
                server.close()
                self.skipTest(f'cannot create unix socket: {exc}')
            try:
                with self.assertRaises(M.ArtifactError):
                    manifest_of(directory)
            finally:
                server.close()
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    @unittest.skipUnless(POSIX, 'requires a POSIX host')
    def test_read_only_directory_still_manifests(self):
        if not hasattr(os, 'geteuid') or os.geteuid() == 0:
            self.skipTest('running as root; read-only permissions are not enforced')
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', 'x')
            os.chmod(directory, 0o555)
            try:
                self.assertEqual(manifest_of(directory)['files'][0]['path'], 'a.txt')
            finally:
                os.chmod(directory, 0o755)

    @unittest.skipUnless(POSIX, 'requires a POSIX host')
    def test_unreadable_file_raises_clear_error(self):
        if not hasattr(os, 'geteuid') or os.geteuid() == 0:
            self.skipTest('running as root; unreadable permissions are not enforced')
        with tempfile.TemporaryDirectory() as directory:
            path = write(directory, 'a.txt', 'x')
            os.chmod(path, 0o000)
            try:
                with self.assertRaises(M.ArtifactError) as caught:
                    manifest_of(directory)
                self.assertIn('unreadable', str(caught.exception))
            finally:
                os.chmod(path, 0o644)


class SymlinkTests(ArtifactTestCase):
    def test_symlink_rejected_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', 'x')
            os.symlink('a.txt', os.path.join(directory, 'link'))
            with self.assertRaises(M.ArtifactError):
                manifest_of(directory)
            payload = manifest_of(directory, allow_symlink=True)
            self.assertEqual(payload['symlinkPolicy']['mode'], 'record-target-only')
            self.assertFalse(payload['symlinkPolicy']['followSymlinks'])

    def test_symlink_escape_records_target_text_only(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            secret = write(outside, 'secret.txt', 'top-secret-outside-content')
            os.symlink(str(secret), os.path.join(directory, 'escape'))
            payload = manifest_of(directory, allow_symlink=True)
            entries = payload['files']
            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertEqual(entry['type'], 'symlink')
            self.assertEqual(entry['linkTarget'], str(secret))
            self.assertEqual(entry['sha256'], hashlib.sha256(str(secret).encode()).hexdigest())
            self.assertNotEqual(entry['sha256'], hashlib.sha256(b'top-secret-outside-content').hexdigest())
            self.assertEqual(payload['symlinkPolicy']['mode'], 'record-target-only')

    def test_internal_symlink_records_target(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'target.txt', 'x')
            os.symlink('target.txt', os.path.join(directory, 'link'))
            entries = manifest_of(directory, allow_symlink=True)['files']
            self.assertEqual([entry['path'] for entry in entries], ['link', 'target.txt'])
            link = next(entry for entry in entries if entry['path'] == 'link')
            self.assertEqual(link['linkTarget'], 'target.txt')
            self.assertNotEqual(link['sha256'], hashlib.sha256(b'x').hexdigest())

    def test_symlinked_directory_not_traversed(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'real/f.txt', 'x')
            os.symlink('real', os.path.join(directory, 'linkdir'))
            paths = [entry['path'] for entry in manifest_of(directory, allow_symlink=True)['files']]
            self.assertEqual(paths, ['linkdir', 'real/f.txt'])
            self.assertNotIn('linkdir/f.txt', paths)


class CheckTests(ArtifactTestCase):
    def test_check_ok_on_identical_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', 'x')
            write(directory, 'sub/b.txt', 'y')
            payload = manifest_of(directory)
            result = M.check_tree(directory, payload)
            self.assertTrue(result['ok'])
            self.assertEqual(result['changed'], [])
            self.assertEqual(result['missing'], [])
            self.assertEqual(result['extra'], [])
            self.assertTrue(result['aggregateMatches'])

    def test_check_detects_changed_bytes_same_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write(directory, 'a.txt', 'x')
            payload = manifest_of(directory)
            path.write_bytes(b'y')
            result = M.check_tree(directory, payload)
            self.assertFalse(result['ok'])
            self.assertEqual([entry['path'] for entry in result['changed']], ['a.txt'])

    def test_check_detects_changed_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write(directory, 'a.txt', 'x')
            payload = manifest_of(directory)
            path.write_bytes(b'longer-content')
            result = M.check_tree(directory, payload)
            self.assertFalse(result['ok'])
            self.assertEqual(result['changed'][0]['expected']['size'], 1)
            self.assertEqual(result['changed'][0]['actual']['size'], 14)

    def test_check_reports_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write(directory, 'a.txt', 'x')
            write(directory, 'b.txt', 'y')
            payload = manifest_of(directory)
            os.unlink(path)
            result = M.check_tree(directory, payload)
            self.assertFalse(result['ok'])
            self.assertEqual(result['missing'], ['a.txt'])
            self.assertEqual(result['extra'], [])

    def test_check_reports_extra(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', 'x')
            payload = manifest_of(directory)
            write(directory, 'b.txt', 'y')
            result = M.check_tree(directory, payload)
            self.assertFalse(result['ok'])
            self.assertEqual(result['extra'], ['b.txt'])
            self.assertEqual(result['missing'], [])

    def test_check_reports_root_id_change_without_failing_content(self):
        with tempfile.TemporaryDirectory() as parent:
            write(parent + '/one', 'a.txt', 'x')
            write(parent + '/two', 'a.txt', 'x')
            payload = manifest_of(os.path.join(parent, 'one'))
            result = M.check_tree(os.path.join(parent, 'two'), payload)
            self.assertTrue(result['rootIdChanged'])
            self.assertTrue(result['ok'])

    def test_check_detects_manifest_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', 'x')
            payload = manifest_of(directory)
            payload['aggregateSha256'] = '0' * 64
            result = M.check_tree(directory, payload)
            self.assertFalse(result['ok'])
            self.assertFalse(result['aggregateMatches'])
            self.assertEqual(result['changed'], [])
            payload = manifest_of(directory)
            payload['files'][0]['sha256'] = '0' * 64
            result = M.check_tree(directory, payload)
            self.assertFalse(result['ok'])
            self.assertEqual([entry['path'] for entry in result['changed']], ['a.txt'])

    def test_check_rejects_malformed_manifest_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'bad.json'
            for bad_path in ('/etc/passwd', '../escape', 'a\\b'):
                target.write_text(json.dumps({'schemaVersion': 1, 'rootId': 'x', 'files': [
                    {'path': bad_path, 'type': 'file', 'size': 1, 'sha256': '0' * 64}]}))
                with self.assertRaises(M.ArtifactError):
                    M.load_manifest(target)

    def test_check_rejects_unsupported_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'bad.json'
            target.write_text(json.dumps({'schemaVersion': 99, 'files': []}))
            with self.assertRaises(M.ArtifactError):
                M.load_manifest(target)
            target.write_text('{"schemaVersion": 1, "files": [{"path": "a.txt", "size": -1, "sha256": "x"}]}')
            with self.assertRaises(M.ArtifactError):
                M.load_manifest(target)

    def test_check_self_inclusion_of_manifest_inside_root(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', 'x')
            target = Path(directory) / 'manifest.json'
            payload = manifest_path(directory, target)
            result = M.check_tree(directory, payload, manifest_path=str(target))
            self.assertTrue(result['ok'])
            self.assertEqual(result['extra'], [])

    def test_check_requires_allow_symlink_for_recorded_links(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'target.txt', 'x')
            os.symlink('target.txt', os.path.join(directory, 'link'))
            payload = manifest_of(directory, allow_symlink=True)
            with self.assertRaises(M.ArtifactError):
                M.check_tree(directory, payload)
            result = M.check_tree(directory, payload, allow_symlink=True)
            self.assertTrue(result['ok'])
            self.assertTrue(result['symlinkPolicyMatches'])

    def test_check_flags_symlink_policy_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', 'x')
            payload = manifest_of(directory, allow_symlink=True)
            result = M.check_tree(directory, payload)
            self.assertFalse(result['symlinkPolicyMatches'])
            self.assertFalse(result['ok'])

    def test_manifest_out_inside_root_is_not_self_included(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', 'x')
            target = Path(directory) / 'MANIFEST.json'
            self.assertEqual(M.main(['manifest', directory, '--out', str(target)]), 0)
            first = target.read_bytes()
            self.assertNotIn(b'MANIFEST.json', first)
            self.assertEqual(M.main(['manifest', directory, '--out', str(target)]), 0)
            self.assertEqual(first, target.read_bytes())


class CliTests(ArtifactTestCase):
    def test_cli_manifest_stdout_exit_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', 'x')
            completed = run_cli('manifest', directory)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload['files'][0]['path'], 'a.txt')

    def test_cli_default_command_without_manifest_keyword(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', 'x')
            completed = run_cli(directory)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)['files'][0]['path'], 'a.txt')

    def test_cli_privacy_exit_code_three_on_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'leak.md', 'OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz012345')
            completed = run_cli('--privacy-check', directory)
            self.assertEqual(completed.returncode, 3)
            self.assertFalse(json.loads(completed.stdout)['ok'])

    def test_cli_privacy_exit_code_zero_when_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'notes.md', 'A benign note about token budgets.\n')
            completed = run_cli('--privacy-check', directory)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertTrue(json.loads(completed.stdout)['ok'])

    def test_cli_check_exit_code_two_on_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write(directory, 'a.txt', 'x')
            target = Path(directory) / 'manifest.json'
            manifest_path(directory, target)
            path.write_bytes(b'changed')
            completed = run_cli('manifest', directory, '--check', str(target))
            self.assertEqual(completed.returncode, 2)
            payload = json.loads(completed.stdout)
            self.assertEqual([entry['path'] for entry in payload['changed']], ['a.txt'])

    def test_cli_check_exit_zero_when_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'a.txt', 'x')
            target = Path(directory) / 'manifest.json'
            manifest_path(directory, target)
            completed = run_cli('manifest', directory, '--check', str(target))
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_cli_policy_violation_exit_code_one(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, '.env', 'A=1')
            completed = run_cli('manifest', directory)
            self.assertEqual(completed.returncode, 1)
            self.assertIn('error:', completed.stderr)


class PrivacyTests(ArtifactTestCase):
    def test_api_key_env_names_detected(self):
        cases = {
            'OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz012345': 'openai-api-key-env',
            'DEEPSEEK_API_KEY=abcdef0123456789abcdef0123456789': 'deepseek-api-key-env',
            'ANTHROPIC_API_KEY=sk-ant-abcdefghijklmnopqrstuvwxyz': 'anthropic-api-key-env',
        }
        for text, rule in cases.items():
            with self.subTest(text=text):
                self.assertIn(rule, self.rules_for(text))

    def test_authorization_header_detected(self):
        rules = self.rules_for('Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def')
        self.assertIn('authorization-header', rules)

    def test_bearer_token_detected(self):
        self.assertIn('bearer-token', self.rules_for('curl -H "X-Trace: Bearer abcdefghijklmnop"'))

    def test_token_query_parameter_detected(self):
        for text in ('https://host/callback?token=abc123def456',
                     'https://host/callback?x=1&access_token=zzz999888777',
                     '?api_key=abcdef123456'):
            with self.subTest(text=text):
                self.assertIn('token-query-parameter', self.rules_for(text))

    def test_dsh_web_token_detected(self):
        for text in ('DSH_WEB_TOKEN=deadbeefcafe1234', 'dsh-web-token: 0123456789abcdef'):
            with self.subTest(text=text):
                self.assertIn('dsh-web-token', self.kinds_for(text))

    def test_secret_env_dump_detected(self):
        text = ('AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE\n'
                'GITHUB_TOKEN=ghp_0123456789abcdef\n'
                'DB_PASSWORD=hunter2hunter2')
        self.assertIn('secret-env', self.kinds_for(text))

    def test_linux_home_path_detected(self):
        self.assertIn('linux-home-path', self.rules_for('opened /home/alice/project/notes.md'))

    def test_macos_home_path_detected(self):
        self.assertIn('macos-home-path', self.rules_for('cached at /Users/alice/Library/Caches/x'))

    def test_windows_home_path_detected(self):
        self.assertIn('windows-home-path', self.rules_for('C:\\Users\\alice\\AppData\\Local\\Temp\\x'))

    def test_token_prose_not_flagged(self):
        text = ('Every arm gets the same token budget. We report token counts and the token limit.\n'
                'Token usage is logged per turn; the ordinary English word token is not a secret.')
        self.assertEqual(self.scan_text(text)['findings'], [])

    def test_benign_hex_and_sha_not_flagged(self):
        text = ('sha256: 3f786850e387550fdab836ed7e6dc881de23001b9c1f4a4b0d3f0e2b0b1e9c11\n'
                'commit 02e140468456846228caf1eaafebbf453b736d54\n'
                'id=deadbeefcafe1234')
        self.assertEqual(self.scan_text(text)['findings'], [])

    def test_placeholder_user_paths_not_flagged(self):
        text = ('/home/<user>/project /Users/<user>/project C:\\Users\\<user>\\project\n'
                '/home/$USER/x /home/{user}/x /Users/{user}/x')
        self.assertEqual(self.scan_text(text)['findings'], [])

    def test_credential_filename_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, '.env', 'A=1')
            write(directory, 'id_rsa', 'x')
            write(directory, 'server.pem', 'x')
            result = M.privacy_scan(directory)
            self.assertFalse(result['ok'])
            pairs = {(finding['path'], finding['kind']) for finding in result['findings']}
            self.assertIn(('.env', 'credential-filename'), pairs)
            self.assertIn(('id_rsa', 'credential-filename'), pairs)
            self.assertIn(('server.pem', 'credential-filename'), pairs)

    def test_secret_like_filename_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('token-budget.md', 'api_key-notes.md', 'my-secret-plan.md'):
                write(directory, name, 'ordinary prose only')
            result = M.privacy_scan(directory)
            pairs = {(finding['path'], finding['kind']) for finding in result['findings']}
            self.assertIn(('token-budget.md', 'secret-filename'), pairs)
            self.assertIn(('api_key-notes.md', 'secret-filename'), pairs)
            self.assertIn(('my-secret-plan.md', 'secret-filename'), pairs)

    def test_symlink_target_text_scanned(self):
        with tempfile.TemporaryDirectory() as directory:
            os.symlink('/Users/alice/private/notes.md', os.path.join(directory, 'escape'))
            result = M.privacy_scan(directory)
            self.assertIn('macos-home-path', {finding['rule'] for finding in result['findings']})
            self.assertIn('symlink', {finding['kind'] for finding in result['findings']})

    def test_privacy_scan_does_not_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            write(outside, 'leak.md', 'OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz012345')
            os.symlink(outside, os.path.join(directory, 'linkdir'))
            result = M.privacy_scan(directory)
            paths = {finding['path'] for finding in result['findings']}
            self.assertNotIn('linkdir/leak.md', paths)
            self.assertIn('linkdir', paths)

    def test_preview_redacts_secret_text(self):
        secret = 'sk-abcdefghijklmnopqrstuvwxyz012345'
        result = self.scan_text('OPENAI_API_KEY=' + secret)
        previews = ' '.join(finding['preview'] for finding in result['findings'])
        self.assertIn('<redacted>', previews)
        self.assertNotIn(secret, previews)
        self.assertNotIn('abcdefghijklmnop', previews)

    def test_clean_tree_is_ok(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'notes.md', 'A benign note about token budgets and version corridors.\n')
            write(directory, 'data.json', json.dumps({'sha256': 'a' * 64, 'bytes': 12}))
            result = M.privacy_scan(directory)
            self.assertTrue(result['ok'])
            self.assertEqual(result['findings'], [])

    def test_findings_are_sorted_and_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'b.md', 'Bearer abcdefghijklmnop')
            write(directory, 'a.md', '/home/alice/work')
            first = M._render(M.privacy_scan(directory))
            second = M._render(M.privacy_scan(directory))
            self.assertEqual(first, second)
            payload = json.loads(first)
            keys = [(finding['path'], finding['line'], finding['rule']) for finding in payload['findings']]
            self.assertEqual(keys, sorted(keys))

    def test_fifo_reported_by_privacy_scan(self):
        if not hasattr(os, 'mkfifo'):
            self.skipTest('os.mkfifo unavailable on this platform')
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.mkfifo(os.path.join(directory, 'pipe'))
            except OSError as exc:
                self.skipTest(f'cannot create FIFO: {exc}')
            result = M.privacy_scan(directory)
            self.assertIn('non-regular-file', {finding['kind'] for finding in result['findings']})

    def test_binary_content_does_not_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'blob.bin', bytes(range(256)) * 8)
            result = M.privacy_scan(directory)
            self.assertIn('findings', result)
            self.assertIsInstance(result['ok'], bool)

    def test_privacy_check_rejects_check_combination(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = run_cli('--privacy-check', directory, '--check', 'x.json')
            self.assertEqual(completed.returncode, 1)


if __name__ == '__main__':
    unittest.main()
