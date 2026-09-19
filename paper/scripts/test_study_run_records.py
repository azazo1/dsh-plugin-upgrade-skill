"""Focused unittest coverage for the study-v1 pilot run-record validator.

No model calls, no network, no pilot run. All fixtures are synthetic in-memory
records marked as unit-test fixtures, never real measurements.
"""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'run_records', Path(__file__).with_name('validate-study-run-records.py')
)
run_records = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_records)

TREE_H4 = 'a3fc23c1021e67f58ab8625051b60adbdc6bd2ad'
TREE_H25 = '0d1e30b9a1f20e741bbe83053f9088ba51587b7a'


def base_record(**overrides):
    """A complete synthetic record. Overrides replace individual fields."""
    record = {
        'studyId': run_records.STUDY_ID,
        'taskId': 'H4-tsbuildinfo-trap',
        'condition': 'A',
        'modelRequested': 'example-model-high',
        'modelResolved': 'example-model-high',
        'modelIdentityStatus': 'verified',
        'reasoning': 'high',
        'runKind': 'development-pilot',
        'attemptKind': 'original',
        'startedAt': '2026-01-01T00:00:00+00:00',
        'endedAt': '2026-01-01T00:00:10+00:00',
        'wallDurationMs': 10000,
        'timeoutSeconds': 600,
        'status': 'success',
        'exitCode': 0,
        'artifactRootRelative': 'output/study-v1-pilot/H4-tsbuildinfo-trap/A',
        'materialManifestSha256': 'a' * 64,
        'taskTreeSha': TREE_H4,
        'runnerVersion': 'pilot-runner-0',
        'solverOutputPresent': True,
        'patchPresent': True,
        'judgeStatus': 'not-run',
        'tokenUsage': {'input': 1000, 'cachedInput': 400, 'output': 100, 'totalReported': 1100},
        'cost': {'amount': 0.25, 'currency': 'USD'},
        'exceptions': [],
        'retryOf': None,
        'notes': 'unit-test fixture; not a real run',
    }
    record.update(overrides)
    return record


class ValidatorTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config, cls.inventory, cls.plan, cls.trees = run_records.load_authority()
        cls.plan_material = {
            (trial['task'], trial['arm']): trial['materialSha256'] for trial in cls.plan['trials']
        }

    # -- helpers ----------------------------------------------------------- #
    def record_errors(self, record):
        errors, _ = run_records.validate_record(record, 0, self.trees)
        return errors

    def codes(self, record):
        return {error['code'] for error in self.record_errors(record)}

    def assertRejected(self, code, **overrides):
        found = self.codes(base_record(**overrides))
        self.assertIn(code, found, 'expected {} in {}'.format(code, sorted(found)))
        return found

    def assertAccepted(self, **overrides):
        found = self.codes(base_record(**overrides))
        self.assertEqual(found, set(), 'unexpected diagnostics: {}'.format(sorted(found)))

    def set_errors(self, records):
        errors, _, summary = run_records.validate_set(records)
        return {error['code'] for error in errors}, summary

    def pilot_records(self):
        records = []
        for task in run_records.PILOT_TASKS:
            for condition in run_records.CONDITIONS:
                record = base_record(
                    taskId=task,
                    condition=condition,
                    recordId='{}-{}'.format(task, condition),
                    taskTreeSha=self.trees[task],
                    materialManifestSha256=self.plan_material[(task, condition)],
                )
                records.append(record)
        return records

    def run_cli(self, argv):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = run_records.main(argv)
        text = stream.getvalue()
        return code, text, json.loads(text)

    def write_set(self, directory, records, name='set.json'):
        path = Path(directory) / name
        path.write_text(json.dumps({'records': records}))
        return path

    # -- plan and cell completeness --------------------------------------- #
    def test_expected_cells_are_exactly_sixteen(self):
        self.assertEqual(len(run_records.expected_cells(self.plan)), 16)
        self.assertEqual(run_records.EXPECTED_CELL_COUNT, 16)

    def test_expected_cells_are_four_tasks_by_four_conditions(self):
        cells = set(run_records.expected_cells(self.plan))
        self.assertEqual({cell[0] for cell in cells}, set(run_records.PILOT_TASKS))
        self.assertEqual({cell[1] for cell in cells}, set(run_records.CONDITIONS))
        self.assertEqual(len(cells), 16)

    def test_check_plan_accepts_not_started(self):
        code, _, report = self.run_cli(['--check-plan'])
        self.assertEqual(code, 0)
        self.assertTrue(report['valid'])
        self.assertEqual(report['state'], 'not-started')
        self.assertFalse(report['pilotComplete'])
        self.assertEqual(report['recordCount'], 0)
        self.assertEqual(report['expectedCellCount'], 16)

    def test_repository_has_zero_pilot_records(self):
        runs = run_records.DEFAULT_RECORDS_DIR
        self.assertFalse(runs.exists(), 'pilot record directory must remain absent until a real pilot runs')

    def test_check_plan_full_valid_set_completes(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_set(directory, self.pilot_records())
            code, _, report = self.run_cli(['--check-plan', '--records', directory])
            self.assertEqual(code, 0, report['errors'])
            self.assertTrue(report['pilotComplete'])
            self.assertEqual(report['state'], 'complete')
            self.assertEqual(report['presentCellCount'], 16)
            self.assertEqual(report['unresolvedRetries'], 0)

    def test_check_plan_rejects_missing_cell(self):
        records = self.pilot_records()[:-1]
        with tempfile.TemporaryDirectory() as directory:
            self.write_set(directory, records)
            code, _, report = self.run_cli(['--check-plan', '--records', directory])
            self.assertEqual(code, 1)
            self.assertEqual(len(report['missingCells']), 1)
            self.assertFalse(report['pilotComplete'])

    def test_check_plan_rejects_duplicate_cell(self):
        records = self.pilot_records()
        duplicate = dict(records[0])
        duplicate.pop('recordId')
        records[0].pop('recordId')
        records.append(duplicate)
        with tempfile.TemporaryDirectory() as directory:
            self.write_set(directory, records)
            code, _, report = self.run_cli(['--check-plan', '--records', directory])
            self.assertEqual(code, 1)
            self.assertTrue(report['duplicateCells'])
            self.assertIn('duplicate-cell', {error['code'] for error in report['errors']})

    def test_check_plan_rejects_extra_task_cell(self):
        records = self.pilot_records()
        extra = base_record(taskId='H1-plane-trap', recordId='H1-A', taskTreeSha=self.trees['H1-plane-trap'])
        records.append(extra)
        with tempfile.TemporaryDirectory() as directory:
            self.write_set(directory, records)
            code, _, report = self.run_cli(['--check-plan', '--records', directory])
            self.assertEqual(code, 1)
            self.assertEqual(len(report['extraCells']), 1)
            self.assertIn('task-replacement', {error['code'] for error in report['errors']})

    def test_check_plan_rejects_extra_condition_cell(self):
        records = self.pilot_records()
        records.append(base_record(condition='E', recordId='H4-E'))
        with tempfile.TemporaryDirectory() as directory:
            self.write_set(directory, records)
            code, _, report = self.run_cli(['--check-plan', '--records', directory])
            self.assertEqual(code, 1)
            self.assertEqual(len(report['extraCells']), 1)
            self.assertIn('condition-invalid', {error['code'] for error in report['errors']})

    def test_check_plan_rejects_wrong_task_tree(self):
        records = self.pilot_records()
        records[0]['taskTreeSha'] = TREE_H25
        with tempfile.TemporaryDirectory() as directory:
            self.write_set(directory, records)
            code, _, report = self.run_cli(['--check-plan', '--records', directory])
            self.assertEqual(code, 1)
            self.assertIn('task-tree-mismatch', {error['code'] for error in report['errors']})

    def test_check_plan_rejects_material_hash_mismatch(self):
        records = self.pilot_records()
        records[0]['materialManifestSha256'] = 'b' * 64
        with tempfile.TemporaryDirectory() as directory:
            self.write_set(directory, records)
            code, _, report = self.run_cli(['--check-plan', '--records', directory])
            self.assertEqual(code, 1)
            self.assertIn('material-hash-mismatch', {error['code'] for error in report['errors']})

    def test_synthetic_plan_rejects_extra_task(self):
        plan = json.loads(json.dumps(self.plan))
        plan['trials'].append({'task': 'H1-plane-trap', 'arm': 'A'})
        errors, _ = run_records.plan_diagnostics(plan, self.trees)
        self.assertIn('plan-extra-cell', {error['code'] for error in errors})

    def test_synthetic_plan_rejects_extra_condition(self):
        plan = json.loads(json.dumps(self.plan))
        plan['trials'][0]['arm'] = 'E'
        errors, _ = run_records.plan_diagnostics(plan, self.trees)
        self.assertIn('plan-condition-invalid', {error['code'] for error in errors})

    def test_synthetic_plan_rejects_missing_cell(self):
        plan = json.loads(json.dumps(self.plan))
        plan['trials'] = plan['trials'][:-1]
        errors, _ = run_records.plan_diagnostics(plan, self.trees)
        self.assertIn('plan-missing-cell', {error['code'] for error in errors})

    def test_synthetic_plan_rejects_duplicate_cell(self):
        plan = json.loads(json.dumps(self.plan))
        plan['trials'].append(dict(plan['trials'][0]))
        errors, _ = run_records.plan_diagnostics(plan, self.trees)
        self.assertIn('plan-duplicate-cell', {error['code'] for error in errors})

    # -- field presence and null-vs-zero ---------------------------------- #
    def test_omitted_field_is_rejected_never_defaulted(self):
        record = base_record()
        del record['wallDurationMs']
        self.assertIn('field-missing', self.codes(record))

    def test_explicit_null_is_accepted_for_unknown(self):
        self.assertAccepted(
            startedAt=None,
            endedAt=None,
            wallDurationMs=None,
            timeoutSeconds=None,
            exitCode=None,
            runnerVersion=None,
            tokenUsage=None,
            cost=None,
            exceptions=None,
            notes=None,
        )

    def test_zero_token_usage_is_accepted(self):
        self.assertAccepted(tokenUsage={'input': 0, 'cachedInput': 0, 'output': 0, 'totalReported': 0})

    def test_zero_is_distinguishable_from_null_duration(self):
        self.assertAccepted(wallDurationMs=0, startedAt='2026-01-01T00:00:00+00:00', endedAt='2026-01-01T00:00:00+00:00')
        self.assertAccepted(wallDurationMs=None)
        self.assertIn('field-missing', self.codes({k: v for k, v in base_record().items() if k != 'wallDurationMs'}))

    def test_unknown_field_rejected(self):
        self.assertRejected('unknown-field', mysteryMeasurement=1)

    def test_secret_looking_field_rejected(self):
        self.assertRejected('secret-field-rejected', apiKey='sk-should-never-be-stored')
        self.assertRejected('secret-field-rejected', accessToken='token-value')

    def test_best_run_selection_field_rejected(self):
        self.assertRejected('best-run-selection-rejected', bestOf=3)

    def test_task_replacement_field_rejected(self):
        self.assertRejected('replacement-rejected', replacementTask='H1-plane-trap')

    def test_score_field_rejected(self):
        self.assertRejected('score-only-record-rejected', score=95)

    def test_wrong_study_id_rejected(self):
        self.assertRejected('study-id-mismatch', studyId='some-other-study')

    def test_task_not_in_inventory_rejected(self):
        self.assertRejected('task-not-in-inventory', taskId='H99-not-a-pinned-task', taskTreeSha=None)

    def test_task_replacement_rejected(self):
        self.assertRejected('task-replacement', taskId='H1-plane-trap', taskTreeSha=self.trees['H1-plane-trap'])

    def test_condition_replacement_rejected(self):
        self.assertRejected('condition-invalid', condition='E')

    def test_unknown_status_rejected(self):
        self.assertRejected('status-unknown', status='looks-fine')

    def test_unknown_run_kind_rejected(self):
        self.assertRejected('run-kind-invalid', runKind='formal')

    def test_unknown_attempt_kind_rejected(self):
        self.assertRejected('attempt-kind-invalid', attemptKind='rerun')

    def test_schema_version_unsupported_rejected(self):
        self.assertRejected('schema-version-unsupported', schemaVersion=2)

    # -- model identity ---------------------------------------------------- #
    def test_missing_model_recorded_as_unverified(self):
        self.assertAccepted(
            modelRequested=None,
            modelResolved=None,
            modelIdentityStatus='unverified',
        )

    def test_unresolved_model_cannot_claim_verified(self):
        self.assertRejected('model-identity-fabricated', modelResolved=None, modelIdentityStatus='verified')

    def test_resolved_mismatch_with_both_strings_accepted(self):
        self.assertAccepted(
            modelRequested='example-model-high',
            modelResolved='example-model-other',
            modelIdentityStatus='mismatch',
        )

    def test_mismatch_without_resolved_rejected(self):
        self.assertRejected('model-identity-fabricated', modelResolved=None, modelIdentityStatus='mismatch')

    def test_model_identity_status_unknown_rejected(self):
        self.assertRejected('model-identity-unknown', modelIdentityStatus='probably')

    # -- token accounting -------------------------------------------------- #
    def test_cached_subset_accounting_accepted(self):
        self.assertAccepted(tokenUsage={'input': 1000, 'cachedInput': 400, 'output': 100, 'totalReported': 1100})

    def test_double_counted_cached_input_rejected(self):
        found = self.assertRejected(
            'token-double-counted-cached',
            tokenUsage={'input': 1000, 'cachedInput': 400, 'output': 100, 'totalReported': 1500},
        )
        self.assertIn('token-total-inconsistent', found)

    def test_total_inconsistent_rejected(self):
        self.assertRejected(
            'token-total-inconsistent',
            tokenUsage={'input': 1000, 'cachedInput': 400, 'output': 100, 'totalReported': 999},
        )

    def test_exclusive_accounting_convention_accepted(self):
        self.assertAccepted(
            tokenUsage={
                'input': 600,
                'cachedInput': 400,
                'output': 100,
                'totalReported': 1100,
                'accounting': 'input-excludes-cached',
            }
        )

    def test_unknown_accounting_rejected(self):
        self.assertRejected(
            'token-accounting-unknown',
            tokenUsage={'input': 1, 'cachedInput': 0, 'output': 1, 'totalReported': 2, 'accounting': 'vibes'},
        )

    def test_cached_exceeding_inclusive_input_rejected(self):
        self.assertRejected(
            'token-cached-exceeds-input',
            tokenUsage={'input': 100, 'cachedInput': 400, 'output': 100, 'totalReported': 200},
        )

    def test_negative_token_rejected(self):
        self.assertRejected(
            'token-negative',
            tokenUsage={'input': -1, 'cachedInput': 0, 'output': 1, 'totalReported': 0},
        )

    def test_missing_token_subfield_rejected(self):
        self.assertRejected('field-missing', tokenUsage={'input': 1, 'cachedInput': 0, 'output': 1})

    # -- durations --------------------------------------------------------- #
    def test_ended_before_started_rejected(self):
        self.assertRejected(
            'duration-ended-before-started',
            startedAt='2026-01-01T00:00:10+00:00',
            endedAt='2026-01-01T00:00:00+00:00',
            wallDurationMs=10000,
        )

    def test_inconsistent_wall_duration_rejected(self):
        self.assertRejected('duration-inconsistent', wallDurationMs=999999)

    def test_negative_duration_rejected(self):
        self.assertRejected('duration-negative', wallDurationMs=-5)

    def test_timestamp_malformed_rejected(self):
        self.assertRejected('timestamp-malformed', startedAt='yesterday')

    def test_duration_tolerance_accepted(self):
        self.assertAccepted(wallDurationMs=10500)

    # -- status taxonomy --------------------------------------------------- #
    def test_timeout_classification_accepted(self):
        self.assertAccepted(
            status='timeout',
            exitCode=124,
            solverOutputPresent=False,
            patchPresent=False,
            judgeStatus='not-run',
            artifactRootRelative=None,
            materialManifestSha256=None,
            taskTreeSha=None,
        )

    def test_timeout_must_not_be_scored(self):
        self.assertRejected('non-solver-outcome-cannot-be-scored', status='timeout', judgeStatus='scored')

    def test_judge_error_cannot_be_scored(self):
        found = self.assertRejected('judge-error-cannot-be-scored', status='judge-error', judgeStatus='scored')
        self.assertIn('non-solver-outcome-cannot-be-scored', found)

    def test_setup_error_accepted_and_not_scored(self):
        self.assertAccepted(
            status='setup-error',
            exitCode=1,
            solverOutputPresent=False,
            patchPresent=False,
            judgeStatus='not-run',
            artifactRootRelative=None,
            materialManifestSha256=None,
            taskTreeSha=None,
        )
        self.assertRejected('non-solver-outcome-cannot-be-scored', status='setup-error', judgeStatus='scored')

    def test_solver_error_accepted_and_not_scored(self):
        self.assertAccepted(
            status='solver-error',
            exitCode=1,
            solverOutputPresent=False,
            patchPresent=False,
            judgeStatus='not-run',
            artifactRootRelative=None,
            materialManifestSha256=None,
            taskTreeSha=None,
        )

    def test_success_without_output_rejected(self):
        self.assertRejected('success-without-output', solverOutputPresent=False, patchPresent=False)

    def test_task_failure_without_evidence_rejected(self):
        self.assertRejected(
            'task-failure-without-evidence',
            status='task-failure',
            solverOutputPresent=False,
            patchPresent=False,
            judgeStatus='not-run',
            artifactRootRelative=None,
            materialManifestSha256=None,
            taskTreeSha=None,
        )

    def test_incomplete_status_accepted(self):
        self.assertAccepted(
            status='incomplete',
            startedAt=None,
            endedAt=None,
            wallDurationMs=None,
            exitCode=None,
            solverOutputPresent=None,
            patchPresent=None,
            judgeStatus=None,
            artifactRootRelative=None,
            materialManifestSha256=None,
            taskTreeSha=None,
            tokenUsage=None,
            cost=None,
        )

    # -- cost -------------------------------------------------------------- #
    def test_cost_null_accepted(self):
        self.assertAccepted(cost=None)

    def test_cost_zero_is_measured(self):
        self.assertAccepted(cost={'amount': 0, 'currency': 'USD'})

    def test_cost_negative_rejected(self):
        self.assertRejected('cost-negative', cost={'amount': -1, 'currency': 'USD'})

    def test_cost_currency_policy(self):
        self.assertRejected('cost-currency-invalid', cost={'amount': 1, 'currency': 'usd'})
        self.assertRejected('cost-currency-missing', cost={'amount': 1})
        self.assertRejected('cost-amount-missing', cost={'amount': None, 'currency': 'USD'})

    # -- artifact paths and hashes ----------------------------------------- #
    def test_artifact_relative_path_accepted(self):
        self.assertAccepted(artifactRootRelative='output/study-v1-pilot/H4-tsbuildinfo-trap/A')

    def test_artifact_absolute_path_rejected(self):
        self.assertRejected('artifact-path-absolute', artifactRootRelative='/var/artifacts/H4/A')

    def test_artifact_tmp_path_rejected(self):
        self.assertRejected('artifact-path-tmp', artifactRootRelative='/tmp/study-pilot/H4/A')
        self.assertRejected('artifact-path-tmp', artifactRootRelative='tmp/study-pilot/H4/A')

    def test_artifact_username_path_rejected(self):
        self.assertRejected('artifact-path-username', artifactRootRelative='Users/alice/study/H4/A')
        self.assertRejected('artifact-path-username', artifactRootRelative='home/bob/study/H4/A')

    def test_artifact_traversal_rejected(self):
        self.assertRejected('artifact-path-traversal', artifactRootRelative='../outside/H4/A')

    def test_hash_format_accepted(self):
        self.assertAccepted(materialManifestSha256='0' * 64, taskTreeSha=TREE_H4)

    def test_malformed_material_sha_rejected(self):
        self.assertRejected('material-hash-malformed', materialManifestSha256='abc123')
        self.assertRejected('material-hash-malformed', materialManifestSha256='A' * 64)

    def test_malformed_task_tree_sha_rejected(self):
        self.assertRejected('task-tree-malformed', taskTreeSha='1234')

    def test_wrong_task_tree_rejected(self):
        self.assertRejected('task-tree-mismatch', taskTreeSha=TREE_H25)

    def test_missing_material_hash_rejected_for_success(self):
        self.assertRejected('missing-artifact-provenance', materialManifestSha256=None)

    def test_missing_artifact_root_rejected_for_patch(self):
        self.assertRejected('missing-artifact-provenance', artifactRootRelative=None)

    # -- retry integrity --------------------------------------------------- #
    def test_retry_chain_accepted(self):
        original = base_record(
            recordId='H4-A-1',
            status='timeout',
            exitCode=124,
            solverOutputPresent=False,
            patchPresent=False,
            artifactRootRelative=None,
            materialManifestSha256=None,
            taskTreeSha=None,
        )
        retry = base_record(recordId='H4-A-2', attemptKind='retry', retryOf='H4-A-1')
        codes, summary = self.set_errors([original, retry])
        self.assertEqual(codes, set())
        self.assertEqual(summary['unresolvedRetries'], 0)
        self.assertEqual(summary['cells'], [('H4-tsbuildinfo-trap', 'A')])

    def test_hidden_retry_rejected(self):
        retry = base_record(attemptKind='retry', retryOf=None)
        self.assertIn('hidden-retry', self.codes(retry))

    def test_unregistered_retry_rejected(self):
        retry = base_record(recordId='H4-A-2', attemptKind='retry', retryOf='does-not-exist')
        codes, _ = self.set_errors([retry])
        self.assertIn('retry-unregistered', codes)

    def test_missing_original_failed_attempt_rejected(self):
        retry = base_record(recordId='H4-A-2', attemptKind='retry', retryOf='H4-A-1')
        codes, _ = self.set_errors([retry])
        self.assertIn('retry-unregistered', codes)
        originals = [base_record(recordId='H4-A-1', attemptKind='original', condition='B')]
        linked = base_record(recordId='H4-A-2', attemptKind='retry', retryOf='H4-A-1')
        mismatch, _ = self.set_errors(originals + [linked])
        self.assertIn('retry-cell-mismatch', mismatch)

    def test_retry_cycle_rejected(self):
        first = base_record(recordId='one', attemptKind='retry', retryOf='two')
        second = base_record(recordId='two', attemptKind='retry', retryOf='one')
        codes, _ = self.set_errors([first, second])
        self.assertIn('retry-cycle', codes)

    def test_retry_chain_terminating_in_retry_rejected(self):
        first = base_record(recordId='one', attemptKind='original')
        second = base_record(recordId='two', attemptKind='retry', retryOf='one')
        third = base_record(recordId='three', attemptKind='retry', retryOf='one')
        codes, _ = self.set_errors([first, second, third])
        self.assertEqual(codes, set())

    def test_retry_preserves_original(self):
        original = base_record(recordId='H4-A-1', status='timeout', solverOutputPresent=False, patchPresent=False,
                               artifactRootRelative=None, materialManifestSha256=None, taskTreeSha=None, exitCode=124)
        retry = base_record(recordId='H4-A-2', attemptKind='retry', retryOf='H4-A-1', status='incomplete',
                            startedAt=None, endedAt=None, wallDurationMs=None, exitCode=None, solverOutputPresent=None,
                            patchPresent=None, judgeStatus=None, artifactRootRelative=None, materialManifestSha256=None,
                            taskTreeSha=None, tokenUsage=None, cost=None)
        kept, summary = self.set_errors([original, retry])
        self.assertEqual(kept, set())
        self.assertEqual(summary['unresolvedRetries'], 1)
        removed, _ = self.set_errors([retry])
        self.assertIn('retry-unregistered', removed)

    def test_duplicate_original_attempt_rejected(self):
        records = [base_record(recordId='a'), base_record(recordId='b')]
        codes, _ = self.set_errors(records)
        self.assertIn('duplicate-original-attempt', codes)

    def test_unresolved_retry_blocks_pilot_complete(self):
        records = self.pilot_records()
        records[0]['status'] = 'incomplete'
        records[0]['solverOutputPresent'] = None
        records[0]['patchPresent'] = None
        records[0]['artifactRootRelative'] = None
        records[0]['materialManifestSha256'] = None
        records[0]['taskTreeSha'] = None
        retry = base_record(
            recordId='H4-tsbuildinfo-trap-A-retry',
            taskId='H4-tsbuildinfo-trap',
            condition='A',
            attemptKind='retry',
            retryOf=records[0]['recordId'],
            status='incomplete',
            startedAt=None,
            endedAt=None,
            wallDurationMs=None,
            exitCode=None,
            solverOutputPresent=None,
            patchPresent=None,
            judgeStatus=None,
            artifactRootRelative=None,
            materialManifestSha256=None,
            taskTreeSha=None,
            tokenUsage=None,
            cost=None,
        )
        records.append(retry)
        with tempfile.TemporaryDirectory() as directory:
            self.write_set(directory, records)
            code, _, report = self.run_cli(['--check-plan', '--records', directory])
            # An in-progress cell is schema-valid but must never be reported as a
            # complete pilot while a retry is unresolved.
            self.assertEqual(code, 0, report['errors'])
            self.assertEqual(report['state'], 'in-progress')
            self.assertGreaterEqual(report['unresolvedRetries'], 1)
            self.assertFalse(report['pilotComplete'])

    # -- CLI behaviour ----------------------------------------------------- #
    def test_check_record_cli_valid_exit_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            record = base_record(materialManifestSha256=self.plan_material[('H4-tsbuildinfo-trap', 'A')])
            path = Path(directory) / 'one.json'
            path.write_text(json.dumps(record))
            code, _, report = self.run_cli(['--check-record', str(path)])
            self.assertEqual(code, 0, report['errors'])
            self.assertTrue(report['valid'])

    def test_check_record_cli_invalid_exit_one(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'one.json'
            path.write_text(json.dumps(base_record(status='nonsense')))
            code, _, report = self.run_cli(['--check-record', str(path)])
            self.assertEqual(code, 1)
            self.assertFalse(report['valid'])

    def test_check_directory_reports_deterministic_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_set(directory, self.pilot_records()[:1], name='a.json')
            self.write_set(directory, self.pilot_records()[1:2], name='b.json')
            code, first, report = self.run_cli(['--check-directory', directory])
            self.assertEqual(code, 0, report['errors'])
            self.assertEqual([entry['name'] for entry in report['files']], ['a.json', 'b.json'])
            _, second, _ = self.run_cli(['--check-directory', directory])
            self.assertEqual(first, second)

    def test_check_directory_empty_is_not_started(self):
        with tempfile.TemporaryDirectory() as directory:
            code, _, report = self.run_cli(['--check-directory', directory])
            self.assertEqual(code, 0)
            self.assertEqual(report['state'], 'not-started')
            self.assertFalse(report['pilotComplete'])

    def test_check_directory_missing_is_config_error(self):
        code, _, report = self.run_cli(['--check-directory', 'paper/study-v1/qc/does-not-exist'])
        self.assertEqual(code, 2)
        self.assertEqual(report['state'], 'config-error')

    def test_check_record_missing_file_is_config_error(self):
        code, _, report = self.run_cli(['--check-record', 'paper/study-v1/qc/nope.json'])
        self.assertEqual(code, 2)
        self.assertIn('config-error', {error['code'] for error in report['errors']})

    def test_usage_error_exits_two_with_json(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            with self.assertRaises(SystemExit) as raised:
                run_records.main([])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn('usage-error', stream.getvalue())

    def test_authority_reports_formal_run_not_allowed(self):
        _, _, report = self.run_cli(['--check-plan'])
        self.assertFalse(report['authority']['formalRunAllowed'])
        self.assertEqual(report['authority']['inventoryTaskCount'], 56)
        self.assertEqual(report['studyId'], run_records.STUDY_ID)


if __name__ == '__main__':
    unittest.main()
