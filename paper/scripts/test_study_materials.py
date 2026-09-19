"""Candidate-package isolation, provenance and reproducibility checks; no model calls."""
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location('prepare', Path(__file__).with_name('prepare-study-v1.py'))
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = json.loads((prepare.STUDY / 'config.json').read_text())
        cls.manifest, cls.packages, cls.prompts, cls.review = prepare.build_materials(config)

    def test_source_identity_and_arm_isolation(self):
        for variant in self.manifest['variants']:
            arms = self.packages[variant['id']]
            self.assertEqual(set(arms['A']), {'ENTRY.md'})
            self.assertEqual(set(arms['B']), {'ENTRY.md', 'guidance.md'})
            for ref in variant['referenceFiles']:
                path = ref['path']
                original = prepare.blob(variant['sourceCommit'], prepare.SKILL + '/' + path)
                self.assertEqual(prepare.sha(original), next(f['sha256'] for f in variant['sourceReferenceFiles'] if f['path'] == path))
                self.assertEqual(arms['C'][path], arms['D'][path])
                self.assertEqual(prepare.sha(arms['C'][path]), ref['sha256'])
            self.assertNotIn('guidance.md', arms['C'])
            self.assertEqual(arms['C']['fact-supplement.md'], arms['D']['fact-supplement.md'])
            self.assertEqual(prepare.sha(arms['C']['fact-supplement.md']), variant['sharedFactSupplement']['sha256'])
            self.assertEqual(arms['D']['guidance.md'], (prepare.STUDY / variant['adaptedGuidance']['path']).read_bytes())
            self.assertEqual(prepare.outlinks(arms['C']), [])
            self.assertEqual(prepare.outlinks(arms['D']), [])
            self.assertNotIn(b'scores zero', arms['C'].get('references/precision-checklist.md', b''))
            for arm in arms.values():
                for path in arm:
                    self.assertTrue(path in ('ENTRY.md', 'guidance.md', 'fact-supplement.md') or path.startswith('references/'))
                    self.assertFalse(set(Path(path).parts) & {'solutions', 'tests', 'scripts', 'examples'})
        self.assertFalse(self.manifest['formalRunAllowed'])
        self.assertTrue(all(u['reviewStatus'] == 'pending' for u in self.review['units']))

    def test_shared_policy_and_closed_book_replacement(self):
        access = (prepare.STUDY / 'material-access.md').read_text().rstrip()
        for prompt in self.prompts.values():
            self.assertTrue(prompt.decode().endswith(access + '\n'))
            self.assertNotIn(prepare.NO_REFS, prompt.decode())
        text, replaced = prepare.overlay_prompt('Before\n' + prepare.NO_REFS + '\nAfter', 'Policy')
        self.assertTrue(replaced)
        self.assertIn('Before\n' + prepare.ALLOWED_REFS + '\nAfter', text)
        with self.assertRaises(ValueError):
            prepare.overlay_prompt('Unknown no reference materials outside the fixture rule', 'Policy')

    def test_review_matches_pinned_units_without_claiming_certification(self):
        audit = json.loads((prepare.STUDY / 'review/entry-review.json').read_text())
        units = {u['id']: u for u in self.review['units']}
        self.assertEqual({r['unitId'] for r in audit['units']}, set(units))
        self.assertEqual(len(audit['units']), len(units))
        self.assertFalse(audit['factEquivalenceApproved'])
        for record in audit['units']:
            self.assertEqual(record['sourceTextSha256'], prepare.sha(units[record['unitId']]['text']))
            variant = record['unitId'].split('-L')[0]
            for evidence in record['referenceEvidence']:
                commit = next(v['sourceCommit'] for v in self.manifest['variants'] if v['id'] == variant)
                self.assertEqual(evidence['sha256'], prepare.sha(prepare.blob(commit, prepare.SKILL + '/' + evidence['path'])))

    def test_archive_matches_manifest_and_is_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            one, two = Path(directory) / 'one.zip', Path(directory) / 'two.zip'
            for path in (one, two):
                prepare.archive(path, self.manifest, self.packages, self.prompts)
            self.assertEqual(one.read_bytes(), two.read_bytes())
            with zipfile.ZipFile(one) as archive:
                self.assertIsNone(archive.testzip())
                expected = {'material-manifest.json', 'MATERIAL-ACCESS.txt'}
                for variant in self.manifest['variants']:
                    for arm, data in variant['arms'].items():
                        for record in data['files']:
                            name = f"materials/{variant['id']}/{arm}/{record['path']}"
                            expected.add(name)
                            self.assertEqual(prepare.sha(archive.read(name)), record['sha256'])
                for task, prompt in self.prompts.items():
                    name = f'prompts/{task}/instruction.md'
                    expected.add(name)
                    self.assertEqual(archive.read(name), prompt)
                self.assertEqual(set(archive.namelist()), expected)
            with self.assertRaises(ValueError):
                prepare.archive(one, self.manifest, self.packages, self.prompts)
            with self.assertRaises(ValueError):
                prepare.materialize(directory, self.manifest, self.packages, self.prompts)

    def test_unsafe_paths_rejected(self):
        for path in ('../answer.md', '/answer.md', 'references/../../answer.md'):
            with self.assertRaises(ValueError):
                prepare.normalized_files({path: b'content'})
        with self.assertRaises(ValueError):
            prepare.normalized_files({'answer.md': 'not bytes'})


if __name__ == '__main__':
    unittest.main()
