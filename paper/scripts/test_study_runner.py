"""Tests for the study-v1 controlled solver runner; no model calls, no network.

The runner is a hyphenated script, so it is loaded the same way the existing
``test_study_materials.py`` loads ``prepare-study-v1.py``.
"""
import copy
import importlib.util
import json
import os
import stat
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "run_study_v1_cell", Path(__file__).with_name("run-study-v1-cell.py")
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

FIXED_CLOCK = lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)  # noqa: E731

CONFIG = {
    "id": "budgeted-small-model-migration-v1",
    "status": "candidate-not-frozen",
    "conditions": {
        "A": "no migration material",
        "B": "generic migration procedure",
        "C": "adapted same-source reference cards plus shared factual supplement",
        "D": "document-only adapted migration procedure plus identical reference cards",
    },
    "formalRunAllowed": False,
}

INVENTORY = {
    "schemaVersion": 1,
    "tasks": [
        {"id": f"T{index:02d}-task", "interactionMode": "Static", "treeSha": "a" * 40}
        for index in range(56)
    ],
}

MATERIALS = {
    "tasks": {"T01-task": {"task": "T01-task", "materialVariant": "v1"}},
    "variants": {
        "v1": {
            "arms": {
                "A": {"ENTRY.md": b"A entry"},
                "B": {"ENTRY.md": b"B entry", "guidance.md": b"generic guidance"},
                "C": {
                    "ENTRY.md": b"C entry",
                    "fact-supplement.md": b"shared facts",
                    "references/card.md": b"card text",
                },
                "D": {
                    "ENTRY.md": b"D entry",
                    "guidance.md": b"adapted guidance",
                    "fact-supplement.md": b"shared facts",
                    "references/card.md": b"card text",
                },
            }
        }
    },
}

MATERIAL_MANIFEST = {
    "formalRunAllowed": False,
    "tasks": [{"task": "T01-task", "materialVariant": "v1"}],
    "variants": [{"id": "v1", "arms": {}}],
}


def make_plan(**overrides):
    kwargs = dict(
        config=CONFIG,
        inventory=INVENTORY,
        materials=MATERIALS,
        material_manifest=MATERIAL_MANIFEST,
        model="gpt-5.3-codex-spark",
        reasoning="high",
        timeout_seconds=1800.0,
        # unit tests run under the OS temporary directory; the production
        # default still rejects /tmp unless the flag is passed explicitly
        allow_tmp=True,
    )
    kwargs.update(overrides)
    artifact_root = kwargs.pop("artifact_root", Path(tempfile.mkdtemp()) / "artifacts")
    task = kwargs.pop("task_id", "T01-task")
    condition = kwargs.pop("condition", "A")
    return runner.plan_cell(task, condition, artifact_root=artifact_root, **kwargs)


class CellDirMixin(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def plan_and_files(self, condition="A", task="T01-task", **kwargs):
        plan = make_plan(task_id=task, condition=condition, artifact_root=self.root / "artifacts", **kwargs)
        files = runner.material_files_for(task, condition, MATERIALS)
        return plan, files


# ── configuration / inventory authority ───────────────────────────────────────


class AuthorityTests(CellDirMixin):
    def test_invalid_task_rejected(self):
        with self.assertRaises(runner.RunnerError) as ctx:
            make_plan(task_id="NOPE-not-a-task")
        self.assertEqual(ctx.exception.exit_class, "invalid-config")

    def test_living_benchmark_extra_task_rejected(self):
        # S22 exists in the living 63-task benchmark but not in the 56 inventory
        with self.assertRaises(runner.RunnerError):
            make_plan(task_id="S22-duplicate-insert-boot-crash-trap")

    def test_real_inventory_is_exactly_56(self):
        inventory = runner.load_inventory()
        self.assertEqual(len(inventory["tasks"]), 56)
        ids = {entry["id"] for entry in inventory["tasks"]}
        self.assertNotIn("S22-duplicate-insert-boot-crash-trap", ids)
        self.assertIn("H4-tsbuildinfo-trap", ids)

    def test_real_inventory_is_the_config_candidate_authority(self):
        config = runner.load_config()
        inventory = runner.load_inventory()
        self.assertEqual(config["candidateInventory"], "paper/audit/task-annotation-v1/inventory.json")
        self.assertEqual(len(inventory["tasks"]), 56)

    def test_real_config_forbids_formal_runs(self):
        config = runner.load_config()
        self.assertIs(config["formalRunAllowed"], False)

    def test_config_with_formal_run_allowed_true_rejected(self):
        path = self.root / "config.json"
        broken = dict(CONFIG, formalRunAllowed=True)
        path.write_text(json.dumps(broken))
        with self.assertRaises(runner.RunnerError) as ctx:
            runner.load_config(path)
        self.assertIn("formalRunAllowed", str(ctx.exception))

    def test_unknown_condition_rejected(self):
        with self.assertRaises(runner.RunnerError) as ctx:
            make_plan(condition="X")
        self.assertEqual(ctx.exception.exit_class, "invalid-config")

    def test_each_declared_condition_plans(self):
        for condition in runner.CONDITIONS:
            plan = make_plan(condition=condition)
            self.assertEqual(plan["condition"], condition)

    def test_condition_missing_from_config_rejected(self):
        config = copy.deepcopy(CONFIG)
        del config["conditions"]["D"]
        with self.assertRaises(runner.RunnerError):
            make_plan(condition="D", config=config)

    def test_missing_model_rejected(self):
        with self.assertRaises(runner.RunnerError) as ctx:
            make_plan(model="")
        self.assertIn("model is required", str(ctx.exception))

    def test_invalid_reasoning_rejected(self):
        with self.assertRaises(runner.RunnerError):
            make_plan(reasoning="extreme")

    def test_invalid_timeout_rejected(self):
        for bad in (0, -5, "soon"):
            with self.assertRaises(runner.RunnerError):
                make_plan(timeout_seconds=bad)

    def test_plan_records_inventory_and_task_pins(self):
        plan = make_plan()
        self.assertEqual(plan["taskTreeSha"], "a" * 40)
        self.assertEqual(plan["interactionMode"], "Static")
        self.assertEqual(plan["artifactRootRelative"], "budgeted-small-model-migration-v1/T01-task/A")
        self.assertEqual(plan["materialManifestSha256"], runner.material_hashes(MATERIALS["variants"]["v1"]["arms"]["A"])["aggregateSha256"])


# ── artifact root policy ──────────────────────────────────────────────────────


class ArtifactRootTests(CellDirMixin):
    def test_relative_artifact_root_rejected(self):
        with self.assertRaises(runner.RunnerError) as ctx:
            runner.plan_cell(
                "T01-task", "A", config=CONFIG, inventory=INVENTORY, materials=MATERIALS,
                material_manifest=MATERIAL_MANIFEST, model="m", reasoning="high",
                timeout_seconds=60, artifact_root=Path("relative/artifacts"),
            )
        self.assertIn("absolute", str(ctx.exception))

    def test_filesystem_root_rejected(self):
        with self.assertRaises(runner.RunnerError):
            runner.plan_cell(
                "T01-task", "A", config=CONFIG, inventory=INVENTORY, materials=MATERIALS,
                material_manifest=MATERIAL_MANIFEST, model="m", reasoning="high",
                timeout_seconds=60, artifact_root=Path("/"),
            )

    def test_tmp_root_rejected_without_flag(self):
        with self.assertRaises(runner.RunnerError) as ctx:
            runner.plan_cell(
                "T01-task", "A", config=CONFIG, inventory=INVENTORY, materials=MATERIALS,
                material_manifest=MATERIAL_MANIFEST, model="m", reasoning="high",
                timeout_seconds=60, artifact_root=Path(tempfile.gettempdir()) / "sv1",
            )
        self.assertIn("/tmp", str(ctx.exception))

    def test_tmp_root_allowed_only_with_explicit_flag(self):
        plan = runner.plan_cell(
            "T01-task", "A", config=CONFIG, inventory=INVENTORY, materials=MATERIALS,
            material_manifest=MATERIAL_MANIFEST, model="m", reasoning="high",
            timeout_seconds=60, artifact_root=Path(tempfile.gettempdir()) / "sv1-allowed",
            allow_tmp=True,
        )
        self.assertEqual(plan["condition"], "A")

    def test_output_path_confinement(self):
        with self.assertRaises(runner.RunnerError):
            runner.ensure_path_confined(self.root / "cell", self.root / "outside" / "x")

    def test_output_path_confinement_allows_nested(self):
        target = runner.ensure_path_confined(self.root / "cell", self.root / "cell" / "logs")
        self.assertTrue(str(target).startswith(str((self.root / "cell").resolve())))


# ── material sets / isolation ─────────────────────────────────────────────────


class MaterialSetTests(CellDirMixin):
    def test_condition_material_sets_exact(self):
        self.assertEqual(set(runner.material_files_for("T01-task", "A", MATERIALS)), {"ENTRY.md"})
        self.assertEqual(set(runner.material_files_for("T01-task", "B", MATERIALS)), {"ENTRY.md", "guidance.md"})
        self.assertIn("fact-supplement.md", runner.material_files_for("T01-task", "C", MATERIALS))
        self.assertIn("guidance.md", runner.material_files_for("T01-task", "D", MATERIALS))

    def test_a_has_no_guidance_or_reference_material(self):
        files = runner.material_files_for("T01-task", "A", MATERIALS)
        self.assertNotIn("guidance.md", files)
        self.assertFalse(any(path.startswith("references/") for path in files))

    def test_c_has_no_adapted_guidance_and_d_does(self):
        c_files = runner.material_files_for("T01-task", "C", MATERIALS)
        d_files = runner.material_files_for("T01-task", "D", MATERIALS)
        self.assertNotIn("guidance.md", c_files)
        self.assertIn("guidance.md", d_files)

    def test_c_and_d_share_identical_fact_and_reference_bytes(self):
        c_files = runner.material_files_for("T01-task", "C", MATERIALS)
        d_files = runner.material_files_for("T01-task", "D", MATERIALS)
        # ENTRY.md is the per-condition discovery document; every shared
        # fact/reference artifact must be byte-identical across C and D
        shared = {path for path in set(c_files) & set(d_files) if path not in ("ENTRY.md", "guidance.md")}
        self.assertIn("fact-supplement.md", shared)
        self.assertTrue(any(path.startswith("references/") for path in shared))
        for path in shared:
            self.assertEqual(c_files[path], d_files[path], path)

    def test_no_cross_condition_material(self):
        b_files = runner.material_files_for("T01-task", "B", MATERIALS)
        self.assertFalse(any(path.startswith("references/") for path in b_files))
        self.assertNotIn("fact-supplement.md", b_files)

    def test_forbidden_material_path_rejected(self):
        materials = copy.deepcopy(MATERIALS)
        materials["variants"]["v1"]["arms"]["A"]["solution/solve.sh"] = "#!/bin/sh\n"
        with self.assertRaises(runner.RunnerError) as ctx:
            runner.material_files_for("T01-task", "A", materials)
        self.assertIn("forbidden artifact", str(ctx.exception))

    def test_judge_and_results_material_rejected(self):
        for bad in ("tests/judge.mjs", "benchmark/results/report.md", "skills/plugin-upgrade/SKILL.md"):
            materials = copy.deepcopy(MATERIALS)
            materials["variants"]["v1"]["arms"]["C"][bad] = "x"
            with self.assertRaises(runner.RunnerError):
                runner.material_files_for("T01-task", "C", materials)

    def test_traversal_material_path_rejected(self):
        materials = copy.deepcopy(MATERIALS)
        materials["variants"]["v1"]["arms"]["A"]["../escape.md"] = "x"
        with self.assertRaises(runner.RunnerError):
            runner.material_files_for("T01-task", "A", materials)

    def test_unknown_variant_rejected(self):
        materials = {"tasks": {"T01-task": {"materialVariant": "missing"}}, "variants": {}}
        with self.assertRaises(runner.RunnerError) as ctx:
            runner.material_files_for("T01-task", "A", materials)
        self.assertEqual(ctx.exception.exit_class, "setup-error")

    def test_material_hash_mismatch_rejected(self):
        with self.assertRaises(runner.RunnerError) as ctx:
            make_plan(expected_material_sha256="0" * 64)
        self.assertIn("material hash mismatch", str(ctx.exception))

    def test_material_hash_matches_expected_when_supplied(self):
        expected = runner.material_hashes(MATERIALS["variants"]["v1"]["arms"]["A"])["aggregateSha256"]
        plan = make_plan(expected_material_sha256=expected)
        self.assertEqual(plan["materialManifestSha256"], expected)

    def test_real_material_hashes_match_study_manifest(self):
        materials, manifest = runner.load_materials_via_prepare()
        entry = next(t for t in manifest["tasks"] if t["task"] == "H4-tsbuildinfo-trap")
        variant = next(v for v in manifest["variants"] if v["id"] == entry["materialVariant"])
        for condition in runner.CONDITIONS:
            files = runner.material_files_for("H4-tsbuildinfo-trap", condition, materials)
            computed = runner.material_hashes(files)["aggregateSha256"]
            self.assertEqual(computed, variant["arms"][condition]["packageSha256"], condition)


# ── environment / secrets ─────────────────────────────────────────────────────


class EnvironmentTests(unittest.TestCase):
    def test_secret_environment_not_inherited(self):
        base = {
            "PATH": "/usr/bin",
            "OPENAI_API_KEY": "sk-live-abc",
            "DEEPSEEK_API_KEY": "dk-abc",
            "GITHUB_TOKEN": "ghp_abc",
            "AWS_SECRET_ACCESS_KEY": "aws",
            "DSH_WEB_TOKEN": "web",
        }
        env = runner.build_child_environment(base)
        self.assertEqual(env["PATH"], "/usr/bin")
        for leaked in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "DSH_WEB_TOKEN"):
            self.assertNotIn(leaked, env)

    def test_native_skill_paths_not_inherited(self):
        base = {
            "HOME": "/Users/someone",
            "AGENTS_SKILLS_DIR": "/Users/someone/.agents/skills",
            "CODEX_HOME": "/Users/someone/.codex",
            "CLAUDE_CONFIG_DIR": "/Users/someone/.claude",
            "PATH": "/usr/bin",
        }
        env = runner.build_child_environment(base)
        self.assertNotIn("AGENTS_SKILLS_DIR", env)
        self.assertNotIn("CODEX_HOME", env)
        self.assertNotIn("CLAUDE_CONFIG_DIR", env)
        self.assertEqual(env["HOME"], None) if "HOME" in env else None
        self.assertNotIn("HOME", env)

    def test_native_skill_discovery_explicitly_disabled(self):
        env = runner.build_child_environment({"PATH": "/usr/bin"})
        self.assertEqual(env["DSH_DISABLE_NATIVE_SKILLS"], "1")
        self.assertEqual(env["DSH_DISABLE_SKILL_AUTODISCOVERY"], "1")

    def test_denied_environment_reports_only_sensitive_names(self):
        base = {"PATH": "/usr/bin", "LANG": "C", "OPENAI_API_KEY": "x", "CODEX_HOME": "/home/u/.codex", "MY_NOTES": "n"}
        denied = runner.denied_environment(base)
        self.assertIn("OPENAI_API_KEY", denied)
        self.assertIn("CODEX_HOME", denied)
        self.assertNotIn("PATH", denied)
        self.assertNotIn("LANG", denied)

    def test_empty_secret_values_do_not_leak(self):
        env = runner.build_child_environment({"OPENAI_API_KEY": "", "PATH": "/usr/bin"})
        self.assertNotIn("OPENAI_API_KEY", env)

    def test_redact_text_redacts_secret_assignments(self):
        text = "OPENAI_API_KEY=sk-live-abc and token: abc123 and Bearer zzz.yyy"
        redacted = runner.redact_text(text)
        self.assertNotIn("sk-live-abc", redacted)
        self.assertNotIn("abc123", redacted)
        self.assertNotIn("zzz.yyy", redacted)
        self.assertIn("<redacted>", redacted)

    def test_redact_text_redacts_absolute_host_paths(self):
        for text in ("/Users/alice/project/x", "/home/bob/y", r"C:\Users\carol\z"):
            redacted = runner.redact_text(text)
            self.assertNotIn("alice", redacted)
            self.assertNotIn("bob", redacted)
            self.assertNotIn("carol", redacted)

    def test_redact_argv_redacts_secret_flag_values(self):
        argv = ["solver", "--api-key", "sk-abc", "--token=xyz", "--model", "m"]
        redacted = runner.redact_argv(argv)
        self.assertEqual(redacted[2], "<redacted>")
        self.assertNotIn("sk-abc", " ".join(redacted))
        self.assertIn("m", redacted)

    def test_redact_value_is_recursive(self):
        value = {"a": ["/Users/dave/x", {"k": "TOKEN=secret"}], "b": 1}
        redacted = runner.redact_value(value)
        self.assertNotIn("dave", json.dumps(redacted))
        self.assertNotIn("secret", json.dumps(redacted))

    def test_meaning_of_token_prose_not_mangled(self):
        prose = "the meaning of a token in this document"
        self.assertEqual(runner.redact_text(prose), prose)


# ── planning determinism / materialization ────────────────────────────────────


class PlanningTests(CellDirMixin):
    def test_plan_is_deterministic(self):
        first = make_plan(artifact_root=self.root / "a")
        second = make_plan(artifact_root=self.root / "a")
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_plan_has_no_timestamp(self):
        plan = make_plan()
        serialized = json.dumps(plan)
        self.assertNotIn("startedAt", serialized)
        self.assertNotIn("endedAt", serialized)

    def test_materialize_creates_fresh_layout(self):
        plan, files = self.plan_and_files()
        paths = runner.materialize_cell(plan, files, self.root / "cell")
        self.assertTrue(paths["materialDir"].is_dir())
        self.assertTrue(paths["workspaceDir"].is_dir())
        self.assertTrue(paths["logsDir"].is_dir())

    def test_materialize_rejects_non_fresh_directory(self):
        plan, files = self.plan_and_files()
        cell = self.root / "cell"
        cell.mkdir()
        (cell / "existing.txt").write_text("x")
        with self.assertRaises(runner.RunnerError) as ctx:
            runner.materialize_cell(plan, files, cell)
        self.assertIn("not fresh", str(ctx.exception))

    def test_materials_are_written_read_only(self):
        plan, files = self.plan_and_files()
        paths = runner.materialize_cell(plan, files, self.root / "cell")
        mode = (paths["materialDir"] / "ENTRY.md").stat().st_mode
        self.assertFalse(mode & stat.S_IWUSR)
        self.assertFalse(mode & stat.S_IWGRP)

    def test_workspace_is_writable(self):
        plan, files = self.plan_and_files()
        paths = runner.materialize_cell(plan, files, self.root / "cell")
        probe = paths["workspaceDir"] / "work.txt"
        probe.write_text("ok")
        self.assertEqual(probe.read_text(), "ok")

    def test_only_this_conditions_materials_materialized(self):
        plan, files = self.plan_and_files(condition="B")
        paths = runner.materialize_cell(plan, files, self.root / "cell")
        written = sorted(str(p.relative_to(paths["materialDir"])) for p in paths["materialDir"].rglob("*") if p.is_file())
        self.assertEqual(written, ["ENTRY.md", "MATERIALS.sha256", "guidance.md"])


# ── execution / classification ────────────────────────────────────────────────


class ExecutionTests(CellDirMixin):
    def test_dry_run_makes_zero_model_calls(self):
        plan, files = self.plan_and_files()
        adapter = runner.MockSolverAdapter()
        outcome = runner.execute_cell(plan, files, artifact_root=self.root / "artifacts", adapter=adapter, execute=False, clock=FIXED_CLOCK)
        self.assertEqual(adapter.calls, 0)
        self.assertTrue(outcome["record"]["dryRun"])
        self.assertEqual(outcome["record"]["status"], "incomplete")

    def test_execute_calls_adapter_once(self):
        plan, files = self.plan_and_files()
        adapter = runner.MockSolverAdapter()
        outcome = runner.execute_cell(plan, files, artifact_root=self.root / "artifacts", adapter=adapter, execute=True, clock=FIXED_CLOCK)
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(outcome["record"]["status"], "success")

    def test_dry_run_never_writes_stdout_log(self):
        plan, files = self.plan_and_files()
        outcome = runner.execute_cell(plan, files, artifact_root=self.root / "artifacts", adapter=runner.MockSolverAdapter(), execute=False, clock=FIXED_CLOCK)
        self.assertFalse((outcome["cellDir"] / "logs" / "stdout.txt").exists())

    def test_timeout_classification(self):
        plan, files = self.plan_and_files()
        adapter = runner.MockSolverAdapter({"timedOut": True})
        record = runner.execute_cell(plan, files, artifact_root=self.root / "artifacts", adapter=adapter, execute=True, clock=FIXED_CLOCK)["record"]
        self.assertEqual(record["exitClass"], "solver-timeout")
        self.assertEqual(record["status"], "timeout")
        self.assertIsNone(record["exitCode"])
        self.assertTrue(any("NOT a task failure" in note for note in record["notes"]))

    def test_nonzero_exit_classification(self):
        plan, files = self.plan_and_files()
        record = runner.execute_cell(plan, files, artifact_root=self.root / "artifacts", adapter=runner.MockSolverAdapter({"exitCode": 3}), execute=True, clock=FIXED_CLOCK)["record"]
        self.assertEqual(record["exitClass"], "solver-error")
        self.assertEqual(record["status"], "solver-error")
        self.assertEqual(record["exitCode"], 3)

    def test_adapter_exception_is_solver_error(self):
        plan, files = self.plan_and_files()
        adapter = runner.MockSolverAdapter(raises=RuntimeError("transport exploded"))
        record = runner.execute_cell(plan, files, artifact_root=self.root / "artifacts", adapter=adapter, execute=True, clock=FIXED_CLOCK)["record"]
        self.assertEqual(record["status"], "solver-error")
        self.assertEqual(record["exceptions"][0]["type"], "RuntimeError")

    def test_resolved_model_absent_is_unverified(self):
        plan, files = self.plan_and_files()
        record = runner.execute_cell(plan, files, artifact_root=self.root / "artifacts", adapter=runner.MockSolverAdapter(), execute=True, clock=FIXED_CLOCK)["record"]
        self.assertIsNone(record["modelResolved"])
        self.assertEqual(record["modelIdentityStatus"], "unverified")

    def test_resolved_model_match_is_verified(self):
        plan, files = self.plan_and_files()
        adapter = runner.MockSolverAdapter({"resolvedModel": plan["modelRequested"]})
        record = runner.execute_cell(plan, files, artifact_root=self.root / "artifacts", adapter=adapter, execute=True, clock=FIXED_CLOCK)["record"]
        self.assertEqual(record["modelIdentityStatus"], "verified")

    def test_resolved_model_mismatch_is_flagged(self):
        plan, files = self.plan_and_files()
        adapter = runner.MockSolverAdapter({"resolvedModel": "some-other-model"})
        record = runner.execute_cell(plan, files, artifact_root=self.root / "artifacts", adapter=adapter, execute=True, clock=FIXED_CLOCK)["record"]
        self.assertEqual(record["modelIdentityStatus"], "mismatch")
        self.assertTrue(any("differs" in note for note in record["notes"]))

    def test_stdout_and_stderr_preserved(self):
        plan, files = self.plan_and_files()
        adapter = runner.MockSolverAdapter({"stdout": "solver said hi", "stderr": "warning"})
        outcome = runner.execute_cell(plan, files, artifact_root=self.root / "artifacts", adapter=adapter, execute=True, clock=FIXED_CLOCK)
        self.assertEqual((outcome["cellDir"] / "logs" / "stdout.txt").read_text(), "solver said hi")
        self.assertEqual((outcome["cellDir"] / "logs" / "stderr.txt").read_text(), "warning")
        self.assertTrue(outcome["record"]["solverOutputPresent"])

    def test_secret_in_solver_output_is_redacted_in_artifacts(self):
        plan, files = self.plan_and_files()
        adapter = runner.MockSolverAdapter({"stdout": "OPENAI_API_KEY=sk-live-abc\n/Users/alice/secret/path"})
        outcome = runner.execute_cell(plan, files, artifact_root=self.root / "artifacts", adapter=adapter, execute=True, clock=FIXED_CLOCK)
        log = (outcome["cellDir"] / "logs" / "stdout.txt").read_text()
        self.assertNotIn("sk-live-abc", log)
        self.assertNotIn("alice", log)

    def test_record_never_contains_api_key(self):
        plan, files = self.plan_and_files()
        os.environ["OPENAI_API_KEY"] = "sk-live-should-not-appear"
        self.addCleanup(os.environ.pop, "OPENAI_API_KEY", None)
        outcome = runner.execute_cell(plan, files, artifact_root=self.root / "artifacts", adapter=runner.MockSolverAdapter(), execute=True, clock=FIXED_CLOCK)
        dumped = (outcome["cellDir"] / "record.json").read_text()
        self.assertNotIn("sk-live-should-not-appear", dumped)

    def test_record_is_deterministic_with_injected_clock(self):
        plan, files = self.plan_and_files()
        first = runner.execute_cell(plan, files, artifact_root=self.root / "one", adapter=runner.MockSolverAdapter(), execute=True, clock=FIXED_CLOCK)
        second = runner.execute_cell(plan, files, artifact_root=self.root / "two", adapter=runner.MockSolverAdapter(), execute=True, clock=FIXED_CLOCK)
        self.assertEqual(
            json.dumps(first["record"], sort_keys=True),
            json.dumps(second["record"], sort_keys=True),
        )

    def test_partial_artifacts_preserved_on_adapter_failure(self):
        plan, files = self.plan_and_files()
        adapter = runner.MockSolverAdapter(raises=RuntimeError("boom"))
        outcome = runner.execute_cell(plan, files, artifact_root=self.root / "artifacts", adapter=adapter, execute=True, clock=FIXED_CLOCK)
        self.assertTrue((outcome["cellDir"] / "materials" / "ENTRY.md").exists())
        self.assertTrue((outcome["cellDir"] / "record.json").exists())
        self.assertTrue((outcome["cellDir"] / "workspace").is_dir())

    def test_interrupted_run_is_preserved(self):
        plan, files = self.plan_and_files()
        adapter = runner.MockSolverAdapter(raises=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            runner.execute_cell(plan, files, artifact_root=self.root / "artifacts", adapter=adapter, execute=True, clock=FIXED_CLOCK)
        cell = self.root / "artifacts" / plan["cellId"]
        self.assertTrue((cell / "materials" / "ENTRY.md").exists())
        self.assertTrue((cell / "logs" / "INTERRUPTED").exists())

    def test_record_maps_exit_classes_to_statuses(self):
        for exit_class, expected in runner.STATUS_BY_EXIT_CLASS.items():
            record = runner.build_record(
                make_plan(), exit_class=exit_class, exit_code=None, started_at="s", ended_at="e",
                wall_duration_ms=0, resolved_model=None, stdout_present=False, stderr_present=False,
                patch_present=False, dry_run=False, exceptions=[], notes=[],
            )
            self.assertEqual(record["status"], expected)
            self.assertEqual(record["judgeStatus"], None)
            self.assertEqual(record["tokenUsage"], None)
            self.assertEqual(record["cost"], None)

    def test_unknown_exit_class_rejected(self):
        with self.assertRaises(runner.RunnerError):
            runner.build_record(
                make_plan(), exit_class="mystery", exit_code=0, started_at="s", ended_at="e",
                wall_duration_ms=0, resolved_model=None, stdout_present=False, stderr_present=False,
                patch_present=False, dry_run=False, exceptions=[], notes=[],
            )

    def test_record_artifact_path_is_relative(self):
        plan, files = self.plan_and_files()
        record = runner.execute_cell(plan, files, artifact_root=self.root / "artifacts", adapter=runner.MockSolverAdapter(), execute=True, clock=FIXED_CLOCK)["record"]
        self.assertFalse(Path(record["artifactRootRelative"]).is_absolute())
        self.assertNotIn(str(self.root), json.dumps(record))

    def test_load_materials_offline_roundtrip(self):
        root = self.root / "offline"
        (root / "v1" / "A").mkdir(parents=True)
        (root / "v1" / "A" / "ENTRY.md").write_text("offline entry")
        (root / "tasks.json").write_text(json.dumps([{"task": "T01-task", "materialVariant": "v1"}]))
        materials, _manifest = runner.load_materials_offline(root)
        files = runner.material_files_for("T01-task", "A", materials)
        self.assertEqual(files["ENTRY.md"], b"offline entry")

    def test_offline_materials_missing_tasks_rejected(self):
        with self.assertRaises(runner.RunnerError):
            runner.load_materials_offline(self.root / "empty")


class CliTests(CellDirMixin):
    REAL_TASK = "H4-tsbuildinfo-trap"

    def test_execute_requires_solver_command(self):
        code = runner.main([
            "--task", self.REAL_TASK, "--condition", "A", "--model", "m",
            "--artifact-root", str(self.root / "artifacts"), "--allow-tmp", "--execute",
        ])
        self.assertEqual(code, 2)

    def test_cli_rejects_execute_and_dry_run_together(self):
        with self.assertRaises(SystemExit):
            runner.main([
                "--task", self.REAL_TASK, "--condition", "A", "--model", "m",
                "--artifact-root", str(self.root / "artifacts"), "--allow-tmp", "--execute", "--dry-run",
            ])

    def test_cli_rejects_task_outside_inventory(self):
        code = runner.main([
            "--task", "S22-duplicate-insert-boot-crash-trap", "--condition", "A", "--model", "m",
            "--artifact-root", str(self.root / "artifacts"), "--allow-tmp",
        ])
        self.assertEqual(code, 2)

    def test_cli_rejects_tmp_root_without_flag(self):
        code = runner.main([
            "--task", self.REAL_TASK, "--condition", "A", "--model", "m",
            "--artifact-root", str(self.root / "artifacts"),
        ])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
