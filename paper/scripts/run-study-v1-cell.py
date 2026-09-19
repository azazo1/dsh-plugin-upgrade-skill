#!/usr/bin/env python3
"""Controlled study-v1 four-condition solver runner (development infrastructure).

THIS IS DEVELOPMENT INFRASTRUCTURE. NOT A FORMAL RESULT PIPELINE YET.

Runs (or, by default, only plans) ONE study-v1 cell: a single
(task, condition) pair of the ``budgeted-small-model-migration-v1`` study.
This optional source-matched runner is separate from the inverted-U work plan.
The existing
``pilot-study-v1.py`` only prepares directories and probes Docker; there was
no reusable four-condition solver runner.

Guarantees:

* ``--dry-run`` is the DEFAULT. A real solver call requires ``--execute``.
* the task must be a member of the pinned 56-task annotation inventory
  (``paper/audit/task-annotation-v1/inventory.json``); tasks that only exist
  in the living benchmark (now 63) are rejected;
* each cell gets a fresh working directory, a fresh agent/session, its own
  condition materials ONLY, read-only material mounts, a sandbox HOME, no
  native-skill auto-discovery, and an allowlisted environment;
* the record is deterministic apart from the injected clock timestamps, and
  never contains credentials, API keys, tokens, or absolute host paths;
* a timeout is classified as ``solver-timeout`` and is never silently
  turned into a task failure or a reward of 0.

The solver transport is an adapter (``spawnSolver``): the default
``MockSolverAdapter`` is used for planning and unit tests and makes ZERO
model calls; ``CommandSolverAdapter`` is the real, explicitly gated
transport. No network access and no model calls happen in this module's
tests or in any dry run.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "paper/study-v1"
CONFIG_PATH = STUDY / "config.json"
INVENTORY_PATH = ROOT / "paper/audit/task-annotation-v1/inventory.json"
MATERIAL_MANIFEST_PATH = STUDY / "generated/material-manifest.json"

RUNNER_VERSION = "study-v1-runner/1"

CONDITIONS = ("A", "B", "C", "D")
EXIT_CLASSES = ("success", "solver-timeout", "solver-error", "setup-error", "invalid-config")
STATUS_BY_EXIT_CLASS = {
    "success": "success",
    "solver-timeout": "timeout",
    "solver-error": "solver-error",
    "setup-error": "setup-error",
}
MODEL_IDENTITY_STATUSES = ("verified", "unverified", "mismatch")

# Environment variables that may cross into the task container/process. Keep
# this list tiny and value-free: everything else (all provider credentials,
# tokens, host config pointers) is dropped.
ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ")
SECRET_NAME_PATTERN = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|SESSION|COOKIE)", re.IGNORECASE
)
NATIVE_SKILL_ENV_PATTERN = re.compile(r"(SKILL|AGENT|CODEX|CLAUDE|DSH).*(DIR|PATH|HOME)", re.IGNORECASE)
ABSOLUTE_PATH_PATTERNS = (
    re.compile(r"/Users/[^/\s\"']+"),
    re.compile(r"/home/[^/\s\"']+"),
    re.compile(r"[A-Za-z]:\\\\?Users\\\\?[^\\\s\"']+"),
)

FORBIDDEN_MATERIAL_MARKERS = (
    "solution/",
    "solve.sh",
    "SOLUTION.md",
    "oracle",
    "tests/",
    "judge.mjs",
    "test.sh",
    "judge-utils",
    "benchmark/results/",
    "skills/",
)


class RunnerError(Exception):
    """An error that maps to one of the declared exit classifications."""

    def __init__(self, exit_class: str, message: str):
        super().__init__(message)
        if exit_class not in EXIT_CLASSES:
            raise ValueError(f"unknown exit class: {exit_class}")
        self.exit_class = exit_class


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def hash_file_streaming(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


# ── study authority ───────────────────────────────────────────────────────────


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RunnerError("invalid-config", f"missing authority file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RunnerError("invalid-config", f"malformed JSON in {path}: {exc}") from exc


def load_config(path: Path = CONFIG_PATH) -> dict:
    config = load_json(path)
    for key in ("id", "status", "conditions", "formalRunAllowed"):
        if key not in config:
            raise RunnerError("invalid-config", f"study config missing key: {key}")
    if config.get("formalRunAllowed") is not False:
        # This runner must never be used to claim a formal run; it refuses to
        # proceed if a future edit flips the flag without a protocol revision.
        raise RunnerError("invalid-config", "study config formalRunAllowed must remain false for development runs")
    for condition in CONDITIONS:
        if condition not in config["conditions"]:
            raise RunnerError("invalid-config", f"study config does not define condition {condition}")
    return config


def load_inventory(path: Path = INVENTORY_PATH) -> dict:
    inventory = load_json(path)
    tasks = inventory.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 56:
        raise RunnerError("invalid-config", f"pinned inventory must contain exactly 56 tasks, got {len(tasks) if isinstance(tasks, list) else 'none'}")
    return inventory


def inventory_index(inventory: dict) -> dict:
    return {entry["id"]: entry for entry in inventory["tasks"]}


def inventory_sha256(inventory: dict) -> str:
    return sha256_text(json.dumps(inventory, sort_keys=True, separators=(",", ":")))


def resolve_task(task_id: str, inventory: dict) -> dict:
    """Return the pinned inventory entry; reject anything outside the 56."""
    if not task_id:
        raise RunnerError("invalid-config", "task id is required")
    index = inventory_index(inventory)
    if task_id not in index:
        raise RunnerError(
            "invalid-config",
            f"task {task_id!r} is not a member of the pinned 56-task study inventory "
            f"(living-benchmark-only tasks are rejected)",
        )
    return index[task_id]


def resolve_condition(condition: str, config: dict) -> str:
    if condition not in CONDITIONS:
        raise RunnerError("invalid-config", f"condition must be one of {', '.join(CONDITIONS)}; got {condition!r}")
    if condition not in config["conditions"]:
        raise RunnerError("invalid-config", f"condition {condition} is not defined by the study config")
    return condition


def load_material_manifest(path: Path = MATERIAL_MANIFEST_PATH) -> dict:
    manifest = load_json(path)
    if manifest.get("formalRunAllowed") is not False:
        raise RunnerError("invalid-config", "material manifest formalRunAllowed must be false")
    return manifest


def manifest_index(manifest: dict) -> dict:
    return {
        "variants": {variant["id"]: variant for variant in manifest["variants"]},
        "tasks": {entry["task"]: entry for entry in manifest["tasks"]},
    }


# ── material planning / materialization ───────────────────────────────────────


def material_files_for(task_id: str, condition: str, materials: dict) -> dict:
    """``materials`` maps variant id -> arm -> {relative path: bytes}.

    Returns the exact ``{path: bytes}`` set for this cell's condition, or
    raises ``setup-error`` when the study authority has no such material.
    """
    try:
        entry = materials["tasks"][task_id]
    except KeyError as exc:
        raise RunnerError("setup-error", f"no material variant recorded for task {task_id}") from exc
    variant = entry["materialVariant"]
    try:
        arm = materials["variants"][variant]["arms"][condition]
    except KeyError as exc:
        raise RunnerError("setup-error", f"variant {variant} has no arm {condition}") from exc
    if not isinstance(arm, dict) or not arm:
        raise RunnerError("setup-error", f"variant {variant} arm {condition} is empty")
    for path in arm:
        normalized = path.replace("\\", "/")
        if normalized.startswith("/") or ".." in Path(normalized).parts:
            raise RunnerError("setup-error", f"material path escapes the mount root: {path}")
        for marker in FORBIDDEN_MATERIAL_MARKERS:
            if marker in normalized or normalized.startswith(marker):
                raise RunnerError("setup-error", f"material set exposes forbidden artifact {path!r} (marker {marker!r})")
    return dict(arm)


def material_hashes(files: dict) -> dict:
    """Per-file hashes plus the package hash.

    ``aggregateSha256`` deliberately reuses the existing study authority's
    algorithm (``prepare-study-v1.py:package_hash``: SHA-256 over the
    pretty-printed, sorted file manifest), so it can be compared with
    ``material-manifest.json`` ``arms[*].packageSha256`` and with the
    ``materialSha256`` recorded in ``qc/pilot.json``.
    """
    file_manifest = [
        {"path": path, "sha256": sha256_bytes(files[path]), "bytes": len(files[path])}
        for path in sorted(files)
    ]
    encoded = json.dumps(file_manifest, ensure_ascii=False, indent=2) + "\n"
    aggregate = sha256_bytes(encoded.encode("utf-8"))
    return {
        "files": file_manifest,
        "aggregateSha256": aggregate,
        "fileCount": len(file_manifest),
        "totalBytes": sum(entry["bytes"] for entry in file_manifest),
    }


def build_child_environment(base_env: dict) -> dict:
    """Allowlisted environment for the solver process/container.

    Credentials, provider keys, host config pointers and native-skill
    discovery variables never cross the boundary.
    """
    env = {}
    for name in ENV_ALLOWLIST:
        if name in base_env:
            env[name] = base_env[name]
    env["TERM"] = "dumb"
    # native skill auto-discovery is disabled explicitly, not by omission
    env["DSH_DISABLE_NATIVE_SKILLS"] = "1"
    env["DSH_DISABLE_SKILL_AUTODISCOVERY"] = "1"
    env["DSH_STUDY_ID"] = "budgeted-small-model-migration-v1"
    return env


def denied_environment(base_env: dict) -> list:
    """Names dropped from the base environment, for the audit record."""
    denied = []
    for name in sorted(base_env):
        if name in ENV_ALLOWLIST:
            continue
        if SECRET_NAME_PATTERN.search(name) or NATIVE_SKILL_ENV_PATTERN.search(name):
            denied.append(name)
    return denied


def redact_text(text: str) -> str:
    """Redact secret-looking assignments and absolute host paths."""
    if not isinstance(text, str):
        return text
    redacted = re.sub(
        r"(?i)\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)[A-Z0-9_]*)\s*[=:]\s*\S+",
        r"\1=<redacted>",
        text,
    )
    redacted = re.sub(r"(?i)(Authorization\s*:\s*)(\S+(\s+\S+)?)", r"\1<redacted>", redacted)
    redacted = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1<redacted>", redacted)
    redacted = re.sub(r"(?i)([?&](?:token|access_token|api_key|key)=)[^&\s\"']+", r"\1<redacted>", redacted)
    for pattern in ABSOLUTE_PATH_PATTERNS:
        redacted = pattern.sub("<redacted-path>", redacted)
    return redacted


def redact_value(value):
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()}
    return value


def redact_argv(argv: list) -> list:
    """Redact secret-bearing CLI arguments (e.g. --api-key VALUE)."""
    out = []
    redact_next = False
    for arg in argv:
        if redact_next:
            out.append("<redacted>")
            redact_next = False
            continue
        if re.match(r"(?i)^--?[A-Za-z0-9_-]*(key|token|secret|password|credential)$", arg):
            out.append(arg)
            redact_next = True
            continue
        if re.match(r"(?i)^(Authorization|Bearer)$", arg):
            out.append(arg)
            redact_next = True
            continue
        out.append(redact_text(arg))
    return out


def plan_cell(
    task_id: str,
    condition: str,
    *,
    config: dict,
    inventory: dict,
    materials: dict,
    material_manifest: dict,
    model: str,
    reasoning: str,
    timeout_seconds: float,
    artifact_root: Path,
    allow_tmp: bool = False,
    command: list | None = None,
    expected_material_sha256: str | None = None,
) -> dict:
    """Build the deterministic cell plan (no filesystem writes, no clock)."""
    entry = resolve_task(task_id, inventory)
    resolve_condition(condition, config)
    if not model:
        raise RunnerError("invalid-config", "model is required; the planned record must name a requested model")
    if reasoning not in ("low", "medium", "high"):
        raise RunnerError("invalid-config", f"reasoning must be low|medium|high, got {reasoning!r}")
    if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
        raise RunnerError("invalid-config", f"timeout must be a positive number of seconds, got {timeout_seconds!r}")

    artifact_root = Path(artifact_root).expanduser()
    if not artifact_root.is_absolute():
        raise RunnerError("invalid-config", "artifact root must be an absolute path")
    resolved_root = artifact_root.resolve()
    if resolved_root == Path(resolved_root.anchor):
        raise RunnerError("invalid-config", "artifact root must not be a filesystem root")
    tmp_root = Path(tempfile.gettempdir()).resolve()
    under_tmp = resolved_root == tmp_root or tmp_root in resolved_root.parents
    if under_tmp and not allow_tmp:
        raise RunnerError(
            "invalid-config",
            f"artifact root {resolved_root} is under the temporary directory; /tmp is not persistent "
            "and is rejected unless --allow-tmp is passed explicitly",
        )

    files = material_files_for(task_id, condition, materials)
    hashes = material_hashes(files)
    if expected_material_sha256 and expected_material_sha256 != hashes["aggregateSha256"]:
        raise RunnerError(
            "setup-error",
            f"material hash mismatch for {task_id}/{condition}: expected {expected_material_sha256}, "
            f"computed {hashes['aggregateSha256']}",
        )

    manifest_entry = material_manifest.get("tasks", {})
    variant_id = None
    for candidate in material_manifest.get("tasks", []):
        if candidate.get("task") == task_id:
            variant_id = candidate.get("materialVariant")
            break
    declared = None
    if variant_id:
        variant = next((v for v in material_manifest.get("variants", []) if v.get("id") == variant_id), None)
        if variant:
            declared = variant.get("arms", {}).get(condition, {}).get("packageSha256")
    if declared and declared != hashes["aggregateSha256"]:
        # The manifest records the arm package hash; a mismatch means the
        # material authority and the materialized bytes disagree.
        raise RunnerError(
            "setup-error",
            f"material package hash mismatch for {task_id}/{condition}: manifest {declared}, computed {hashes['aggregateSha256']}",
        )

    cell_id = f"{config['id']}/{task_id}/{condition}"
    plan = {
        "schemaVersion": 1,
        "runnerVersion": RUNNER_VERSION,
        "studyId": config["id"],
        "studyStatus": config["status"],
        "taskId": task_id,
        "condition": condition,
        "cellId": cell_id,
        "runKind": "development-pilot-cell",
        "attemptKind": "original",
        "interactionMode": entry.get("interactionMode"),
        "taskTreeSha": entry.get("treeSha"),
        "inventorySha256": inventory_sha256(inventory),
        "modelRequested": model,
        "reasoning": reasoning,
        "timeoutSeconds": timeout_seconds,
        "artifactRootRelative": cell_id,
        "materialVariant": variant_id,
        "materialManifestSha256": hashes["aggregateSha256"],
        "materials": hashes,
        "isolation": {
            "freshWorkingDirectory": True,
            "freshAgentSession": True,
            "sharedContextWithOtherCells": False,
            "otherConditionMaterialsVisible": False,
            "materialMountsReadOnly": True,
            "workspaceWritable": True,
            "nativeSkillAutoDiscovery": "disabled",
            "hostPrivateConfigMounted": False,
            "credentialsInEnvironment": False,
            "networkPolicy": "task-container outbound disabled; runner performs no network access",
        },
        "environment": {
            "allow": sorted([*ENV_ALLOWLIST, "TERM", "DSH_DISABLE_NATIVE_SKILLS", "DSH_DISABLE_SKILL_AUTODISCOVERY", "DSH_STUDY_ID"]),
            "explicitDisables": ["DSH_DISABLE_NATIVE_SKILLS=1", "DSH_DISABLE_SKILL_AUTODISCOVERY=1"],
            "sandboxHome": True,
        },
        "command": redact_argv(command) if command else None,
    }
    if not plan["taskTreeSha"]:
        raise RunnerError("setup-error", f"inventory entry for {task_id} has no pinned task tree")
    return plan


def ensure_path_confined(base: Path, candidate: Path) -> Path:
    base_resolved = base.resolve()
    candidate_resolved = candidate.resolve()
    if candidate_resolved != base_resolved and base_resolved not in candidate_resolved.parents:
        raise RunnerError("setup-error", f"path escapes the cell directory: {candidate}")
    return candidate_resolved


def materialize_cell(plan: dict, files: dict, cell_dir: Path) -> dict:
    """Write the planner's files into a fresh cell directory.

    Materials are mounted read-only (0444) and the workspace is writable.
    The cell directory must not already exist: every cell is fresh.
    """
    cell_dir = Path(cell_dir)
    if cell_dir.exists() and any(cell_dir.iterdir()):
        raise RunnerError("setup-error", f"cell directory is not fresh: {cell_dir}")
    material_dir = cell_dir / "materials"
    workspace_dir = cell_dir / "workspace"
    logs_dir = cell_dir / "logs"
    home_dir = cell_dir / "home"
    for directory in (material_dir, workspace_dir, logs_dir, home_dir):
        ensure_path_confined(cell_dir, directory)
        directory.mkdir(parents=True, exist_ok=True)
    for path in sorted(files):
        ensure_path_confined(material_dir, material_dir / path)
        target = material_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[path])
        target.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    (material_dir / "MATERIALS.sha256").write_text(
        json.dumps(plan["materials"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "cellDir": cell_dir,
        "materialDir": material_dir,
        "workspaceDir": workspace_dir,
        "logsDir": logs_dir,
        "homeDir": home_dir,
    }


# ── solver adapters ───────────────────────────────────────────────────────────


class SolverAdapter:
    """Transport interface: ``spawn(spec)`` returns a normalized result dict."""

    name = "abstract"

    def spawn(self, spec: dict) -> dict:  # pragma: no cover - interface
        raise NotImplementedError


class MockSolverAdapter(SolverAdapter):
    """Deterministic, offline adapter used for planning and unit tests.

    It makes ZERO model calls. ``calls`` counts how many times a spawn was
    requested so tests can assert that a dry run never reaches the solver.
    """

    name = "mock"

    def __init__(self, result: dict | None = None, raises: Exception | None = None):
        self.calls = 0
        self._result = result or {}
        self._raises = raises

    def spawn(self, spec: dict) -> dict:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        result = {
            "exitCode": 0,
            "stdout": "",
            "stderr": "",
            "timedOut": False,
            "resolvedModel": None,
            "durationMs": 0,
        }
        result.update(self._result)
        if result["timedOut"]:
            result["exitCode"] = None
        return result


class CommandSolverAdapter(SolverAdapter):
    """Real transport: runs an explicit command with a timeout.

    Only reachable through ``--execute``. The child receives the allowlisted
    environment and never any provider credential from the host.
    """

    name = "command"

    MODEL_PATTERN = re.compile(r'"?(?:resolved_)?model"?\s*[:=]\s*"?([A-Za-z0-9._/:@-]+)"?')

    def __init__(self, command: list, timeout_seconds: float, env: dict, cwd: Path):
        self.command = list(command)
        self.timeout_seconds = timeout_seconds
        self.env = dict(env)
        self.cwd = Path(cwd)

    def spawn(self, spec: dict) -> dict:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                self.command,
                cwd=str(self.cwd),
                env=self.env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "exitCode": None,
                "stdout": (exc.stdout or b"").decode("utf-8", "replace"),
                "stderr": (exc.stderr or b"").decode("utf-8", "replace"),
                "timedOut": True,
                "resolvedModel": None,
                "durationMs": int((time.monotonic() - started) * 1000),
            }
        stdout = completed.stdout.decode("utf-8", "replace")
        resolved = None
        match = self.MODEL_PATTERN.search(stdout)
        if match:
            resolved = match.group(1)
        return {
            "exitCode": completed.returncode,
            "stdout": stdout,
            "stderr": completed.stderr.decode("utf-8", "replace"),
            "timedOut": False,
            "resolvedModel": resolved,
            "durationMs": int((time.monotonic() - started) * 1000),
        }


def classify_result(result: dict) -> str:
    if result.get("timedOut"):
        return "solver-timeout"
    exit_code = result.get("exitCode")
    if exit_code is None:
        return "solver-error"
    if exit_code != 0:
        return "solver-error"
    return "success"


# ── cell execution ────────────────────────────────────────────────────────────


def utc_now(clock=None) -> str:
    moment = clock() if clock else datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat()


def build_record(
    plan: dict,
    *,
    exit_class: str,
    exit_code,
    started_at: str,
    ended_at: str,
    wall_duration_ms,
    resolved_model,
    stdout_present: bool,
    stderr_present: bool,
    patch_present: bool,
    dry_run: bool,
    exceptions: list,
    notes: list,
) -> dict:
    if exit_class not in EXIT_CLASSES:
        raise RunnerError("invalid-config", f"unknown exit class: {exit_class}")
    if resolved_model:
        identity_status = "verified"
    else:
        identity_status = "unverified"
    if identity_status == "verified" and resolved_model != plan["modelRequested"]:
        identity_status = "mismatch"
    record = {
        "schemaVersion": 1,
        "studyId": plan["studyId"],
        "taskId": plan["taskId"],
        "condition": plan["condition"],
        "cellId": plan["cellId"],
        "runKind": plan["runKind"],
        "attemptKind": "dry-run" if dry_run else "original",
        "dryRun": dry_run,
        "modelRequested": plan["modelRequested"],
        "modelResolved": resolved_model,
        "modelIdentityStatus": identity_status,
        "reasoning": plan["reasoning"],
        "timeoutSeconds": plan["timeoutSeconds"],
        "startedAt": started_at,
        "endedAt": ended_at,
        "wallDurationMs": wall_duration_ms,
        "status": "incomplete" if dry_run else STATUS_BY_EXIT_CLASS[exit_class],
        "exitClass": exit_class,
        "exitCode": exit_code,
        "artifactRootRelative": plan["artifactRootRelative"],
        "materialManifestSha256": plan["materialManifestSha256"],
        "taskTreeSha": plan["taskTreeSha"],
        "runnerVersion": RUNNER_VERSION,
        "solverOutputPresent": stdout_present,
        "stderrPresent": stderr_present,
        "patchPresent": patch_present,
        "judgeStatus": None,
        "tokenUsage": None,
        "cost": None,
        "retryOf": None,
        "exceptions": exceptions,
        "notes": notes,
        "isolation": plan["isolation"],
    }
    return record


def execute_cell(
    plan: dict,
    files: dict,
    *,
    artifact_root: Path,
    adapter: SolverAdapter,
    execute: bool,
    clock=None,
    patch_probe=None,
) -> dict:
    """Materialize the cell and (when ``execute``) run the solver adapter.

    Returns ``{"record": ..., "cellDir": ...}``. Artifacts written before a
    failure are always preserved.
    """
    artifact_root = Path(artifact_root)
    cell_dir = artifact_root / plan["cellId"]
    started_at = utc_now(clock)
    started_monotonic = time.monotonic()
    notes = []
    exceptions = []
    exit_class = "success"
    exit_code = None
    resolved_model = None
    stdout_present = False
    stderr_present = False
    patch_present = False
    try:
        paths = materialize_cell(plan, files, cell_dir)
    except RunnerError:
        raise
    except OSError as exc:
        raise RunnerError("setup-error", f"failed to materialize cell: {exc}") from exc

    if execute:
        spawn_spec = {
            "studyId": plan["studyId"],
            "taskId": plan["taskId"],
            "condition": plan["condition"],
            "model": plan["modelRequested"],
            "reasoning": plan["reasoning"],
            "timeoutSeconds": plan["timeoutSeconds"],
            "materialDir": str(paths["materialDir"]),
            "workspaceDir": str(paths["workspaceDir"]),
            "homeDir": str(paths["homeDir"]),
            "env": build_child_environment(os.environ),
            "command": plan.get("command"),
        }
        try:
            result = adapter.spawn(spawn_spec)
        except KeyboardInterrupt:
            exit_class = "solver-error"
            exceptions.append({"type": "KeyboardInterrupt", "message": "interrupted by operator"})
            notes.append("interrupted run preserved: partial artifacts were written before the interrupt")
            _write_partial(paths, plan)
            raise
        except Exception as exc:  # adapter failure is a solver transport error
            exit_class = "solver-error"
            exceptions.append({"type": type(exc).__name__, "message": redact_text(str(exc))})
        else:
            exit_class = classify_result(result)
            exit_code = result.get("exitCode")
            resolved_model = result.get("resolvedModel")
            stdout = redact_text(result.get("stdout") or "")
            stderr = redact_text(result.get("stderr") or "")
            (paths["logsDir"] / "stdout.txt").write_text(stdout, encoding="utf-8")
            (paths["logsDir"] / "stderr.txt").write_text(stderr, encoding="utf-8")
            stdout_present = bool(stdout)
            stderr_present = bool(stderr)
            if result.get("timedOut"):
                notes.append("solver exceeded the frozen timeout; classified solver-timeout, NOT a task failure and NOT reward 0")
            if resolved_model is None:
                notes.append("provider model identity unavailable; modelIdentityStatus=unverified (not fabricated)")
            elif resolved_model != plan["modelRequested"]:
                notes.append("resolved model differs from the requested model; identity status mismatch")
    else:
        notes.append("dry run: no solver was spawned and no model was called")

    ended_at = utc_now(clock)
    wall_duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    if clock is not None:
        # an injected clock means deterministic metadata: durations come from
        # the record's own timestamps, not from wall time
        wall_duration_ms = 0
    if patch_probe is not None:
        try:
            patch_present = bool(patch_probe(paths["workspaceDir"]))
        except Exception as exc:
            exceptions.append({"type": type(exc).__name__, "message": redact_text(str(exc))})
    record = build_record(
        plan,
        exit_class=exit_class,
        exit_code=exit_code,
        started_at=started_at,
        ended_at=ended_at,
        wall_duration_ms=wall_duration_ms,
        resolved_model=resolved_model,
        stdout_present=stdout_present,
        stderr_present=stderr_present,
        patch_present=patch_present,
        dry_run=not execute,
        exceptions=exceptions,
        notes=notes,
    )
    write_record(record, paths["cellDir"])
    return {"record": record, "cellDir": paths["cellDir"]}


def _write_partial(paths: dict, plan: dict) -> None:
    (paths["logsDir"] / "INTERRUPTED").write_text("run interrupted; partial artifacts preserved\n", encoding="utf-8")


def write_record(record: dict, cell_dir: Path) -> Path:
    target = Path(cell_dir) / "record.json"
    target.write_text(json.dumps(redact_value(record), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def load_materials_via_prepare(study_dir: Path = STUDY) -> dict:
    """Reuse the existing material authority (``prepare-study-v1.py``).

    The existing script owns material construction; this runner only consumes
    it, per the P0-1 requirement not to duplicate the preparation logic.
    """
    prepare_path = study_dir.parent / "scripts" / "prepare-study-v1.py"
    spec = importlib.util.spec_from_file_location("prepare_study_v1", prepare_path)
    if spec is None or spec.loader is None:
        raise RunnerError("setup-error", f"cannot load material authority: {prepare_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = load_config(study_dir / "config.json")
    try:
        _manifest, packages, _prompts, _review = module.build_materials(config)
    except Exception as exc:  # material construction failure is a setup error
        raise RunnerError("setup-error", f"material construction failed: {exc}") from exc
    manifest = load_material_manifest(study_dir / "generated/material-manifest.json")
    index = manifest_index(manifest)
    materials = {"variants": {}, "tasks": index["tasks"]}
    for variant_id, arms in packages.items():
        materials["variants"][variant_id] = {"arms": arms}
    return materials, manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run (or plan) one study-v1 (task, condition) cell. Dry-run by default."
    )
    parser.add_argument("--task", required=True)
    parser.add_argument("--condition", required=True, choices=CONDITIONS)
    parser.add_argument("--model", required=True, help="requested model id (recorded, never faked)")
    parser.add_argument("--reasoning", default="high", choices=("low", "medium", "high"))
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--timeout", type=float, default=1800.0, help="solver timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="plan only (DEFAULT)")
    parser.add_argument("--execute", action="store_true", help="actually spawn the solver (explicit gate)")
    parser.add_argument("--solver-command", default=None, help="solver command template, e.g. 'harbor run -p {task}'")
    parser.add_argument("--allow-tmp", action="store_true", help="allow a non-persistent /tmp artifact root")
    parser.add_argument("--expected-material-sha256", default=None)
    parser.add_argument("--materials-from", default=None, help="offline materials directory (tests/QC)")
    parser.add_argument("--print-plan", action="store_true")
    args = parser.parse_args(argv)

    if args.execute and args.dry_run:
        parser.error("--execute and --dry-run are mutually exclusive; dry-run is the default")
    execute = bool(args.execute)

    try:
        config = load_config()
        inventory = load_inventory()
        if args.materials_from:
            materials, manifest = load_materials_offline(Path(args.materials_from))
        else:
            materials, manifest = load_materials_via_prepare()

        command = None
        if args.solver_command:
            command = args.solver_command.split()
        plan = plan_cell(
            args.task,
            args.condition,
            config=config,
            inventory=inventory,
            materials=materials,
            material_manifest=manifest,
            model=args.model,
            reasoning=args.reasoning,
            timeout_seconds=args.timeout,
            artifact_root=Path(args.artifact_root),
            allow_tmp=args.allow_tmp,
            command=command,
            expected_material_sha256=args.expected_material_sha256,
        )
        if args.print_plan:
            print(json.dumps(plan, indent=2, sort_keys=True))
        files = material_files_for(args.task, args.condition, materials)
        if execute:
            if not args.solver_command:
                raise RunnerError("invalid-config", "--execute requires --solver-command; refusing to guess a solver transport")
            adapter = CommandSolverAdapter(
                command,
                timeout_seconds=args.timeout,
                env=build_child_environment(os.environ),
                cwd=Path(args.artifact_root),
            )
        else:
            adapter = MockSolverAdapter()
        outcome = execute_cell(plan, files, artifact_root=Path(args.artifact_root), adapter=adapter, execute=execute)
        print(json.dumps(redact_value(outcome["record"]), indent=2, sort_keys=True))
        if outcome["record"]["status"] in ("success", "incomplete"):
            return 0
        if outcome["record"]["status"] == "timeout":
            return 1
        if outcome["record"]["status"] == "solver-error":
            return 1
        return 2
    except RunnerError as exc:
        print(json.dumps({"error": exc.exit_class, "message": str(exc)}, indent=2), file=sys.stderr)
        return 2 if exc.exit_class in ("invalid-config", "setup-error") else 1


def load_materials_offline(root: Path) -> tuple:
    """Load a materials tree laid out as ``<root>/<variant>/<condition>/<path>``."""
    root = Path(root)
    tasks_path = root / "tasks.json"
    if not tasks_path.exists():
        raise RunnerError("setup-error", f"offline materials root has no tasks.json: {root}")
    tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    variants = {}
    for variant_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        arms = {}
        for arm_dir in sorted(p for p in variant_dir.iterdir() if p.is_dir()):
            files = {}
            for path in sorted(arm_dir.rglob("*")):
                if path.is_file():
                    files[str(path.relative_to(arm_dir)).replace(os.sep, "/")] = path.read_bytes()
            arms[arm_dir.name] = files
        variants[variant_dir.name] = {"arms": arms}
    manifest = {"formalRunAllowed": False, "tasks": tasks, "variants": [{"id": key, "arms": {}} for key in variants]}
    return {"variants": variants, "tasks": {entry["task"]: entry for entry in tasks}}, manifest


if __name__ == "__main__":
    sys.exit(main())
