#!/usr/bin/env python3
"""Completeness and consistency validator for study-v1 development pilot run records.

Read-only and offline: no model calls, no network, no benchmark/skill mutation, and
no claim that any pilot cell has been executed. The repository currently contains
zero pilot run records, so ``--check-plan`` must accept the ``not-started`` state.

Usage::

    validate-study-run-records.py --check-plan [--records PATH]
    validate-study-run-records.py --check-record FILE
    validate-study-run-records.py --check-directory DIR

Exit codes: 0 valid, 1 invalid, 2 usage/config error. Output is deterministic JSON
on stdout.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDY_DIR = ROOT / "paper" / "study-v1"
CONFIG_PATH = STUDY_DIR / "config.json"
PLAN_PATH = STUDY_DIR / "qc" / "pilot.json"
SCHEMA_PATH = STUDY_DIR / "run-record.schema.json"
INVENTORY_PATH = ROOT / "paper" / "audit" / "task-annotation-v1" / "inventory.json"
DEFAULT_RECORDS_DIR = STUDY_DIR / "qc" / "runs"

VALIDATOR_NAME = "validate-study-run-records"
VALIDATOR_VERSION = 1

STUDY_ID = "budgeted-small-model-migration-v1"
CONDITIONS = ("A", "B", "C", "D")
PILOT_TASKS = (
    "H4-tsbuildinfo-trap",
    "H6-remote-error-trap",
    "H12-remote-result-boundary-trap",
    "H25-session-seed-boundary-trap",
)
STATUSES = (
    "success",
    "task-failure",
    "timeout",
    "setup-error",
    "solver-error",
    "judge-error",
    "incomplete",
)
TERMINAL_STATUSES = frozenset(status for status in STATUSES if status != "incomplete")
MODEL_IDENTITY_STATUSES = ("unverified", "verified", "mismatch")
ATTEMPT_KINDS = ("original", "retry")
RUN_KINDS = ("development-pilot",)
JUDGE_STATUSES = ("not-run", "scored", "judge-error", "not-applicable")
TOKEN_ACCOUNTING = ("input-includes-cached", "input-excludes-cached")
DEFAULT_TOKEN_ACCOUNTING = "input-includes-cached"

DURATION_TOLERANCE_MS = 1000
EXPECTED_CELL_COUNT = len(PILOT_TASKS) * len(CONDITIONS)

REQUIRED_FIELDS = (
    "studyId",
    "taskId",
    "condition",
    "modelRequested",
    "modelResolved",
    "modelIdentityStatus",
    "reasoning",
    "runKind",
    "attemptKind",
    "startedAt",
    "endedAt",
    "wallDurationMs",
    "timeoutSeconds",
    "status",
    "exitCode",
    "artifactRootRelative",
    "materialManifestSha256",
    "taskTreeSha",
    "runnerVersion",
    "solverOutputPresent",
    "patchPresent",
    "judgeStatus",
    "tokenUsage",
    "cost",
    "exceptions",
    "retryOf",
    "notes",
)
OPTIONAL_FIELDS = ("recordId", "schemaVersion")

# Metadata that would silently select a favourable attempt, replace a preselected
# task/condition, or smuggle a score into a run record without provenance.
FORBIDDEN_SELECTION = frozenset(
    {
        "selectedRun",
        "selectedAttempt",
        "selectedRuns",
        "chosenRun",
        "chosenAttempt",
        "bestRun",
        "bestAttempt",
        "bestOf",
        "bestOfN",
        "attemptSelection",
        "retainedAttempt",
        "retainedRuns",
        "discardedAttempts",
        "discardedRuns",
        "droppedAttempts",
        "omittedAttempts",
        "excludedAttempts",
        "selection",
        "selectionRule",
        "selectionMetadata",
    }
)
FORBIDDEN_REPLACEMENT = frozenset(
    {
        "replacement",
        "replaces",
        "replacedBy",
        "replacementFor",
        "replacementTask",
        "replacementCondition",
        "taskReplacement",
        "conditionReplacement",
        "replacedTask",
        "replacedCondition",
        "substituteTask",
        "substituteCondition",
        "originalTaskId",
        "originalCondition",
        "newTask",
        "newTaskId",
        "newCondition",
    }
)
FORBIDDEN_SCORE = frozenset({"score", "scores", "reward", "rewards", "grade", "points", "judgeScore", "finalScore"})
SECRET_KEY_PATTERN = re.compile(
    r"(api[_-]?key|secret|passwd|password|credential|access[_-]?token|auth[_-]?token|private[_-]?key|bearer)",
    re.IGNORECASE,
)
RECORD_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]+")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
GIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
CURRENCY_PATTERN = re.compile(r"[A-Z]{3}")
TMP_PATH_PATTERN = re.compile(r"(^|/)(tmp|private/tmp|var/folders|private/var/folders)(/|$)", re.IGNORECASE)
USER_PATH_PATTERN = re.compile(r"^(users|home)/[^/]+(/|$)", re.IGNORECASE)


class ConfigError(Exception):
    """Raised for usage or authority/configuration problems (exit code 2)."""


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _diag(code, message, field=None, record=None):
    return {"code": code, "field": field, "record": record, "message": message}


def sort_diags(diags):
    """Deterministic diagnostic ordering."""
    return sorted(
        diags,
        key=lambda d: (d.get("code") or "", d.get("field") or "", d.get("record") or "", d.get("message") or ""),
    )


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_sha256(value):
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def is_git_sha(value):
    return isinstance(value, str) and GIT_SHA_PATTERN.fullmatch(value) is not None


def parse_timestamp(value):
    """Return ``(state, datetime)`` where state is one of null/ok/malformed."""
    if value is None:
        return "null", None
    if not isinstance(value, str) or not value.strip():
        return "malformed", None
    text = value.strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return "malformed", None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return "ok", parsed


def artifact_path_diagnostics(value):
    """Return ``[(code, message)]`` for an artifactRootRelative candidate."""
    problems = []
    if not isinstance(value, str) or not value.strip():
        return [("artifact-path-invalid", "artifactRootRelative must be a non-empty relative path string")]
    if value != value.strip():
        problems.append(("artifact-path-invalid", "artifactRootRelative must not carry surrounding whitespace"))
    stripped = value.strip()
    if stripped.startswith("/") or stripped.startswith("\\") or re.match(r"^[A-Za-z]:[\\/]", stripped):
        problems.append(("artifact-path-absolute", "artifactRootRelative must not be an absolute path"))
    if stripped.startswith("~"):
        problems.append(("artifact-path-absolute", "artifactRootRelative must not be home-relative"))
    if "\\" in stripped:
        problems.append(("artifact-path-invalid", "artifactRootRelative must use POSIX '/' separators"))
    parts = stripped.split("/")
    if any(part == ".." for part in parts):
        problems.append(("artifact-path-traversal", "artifactRootRelative must not contain '..' components"))
    if any(part == "" for part in parts[:-1]):
        problems.append(("artifact-path-invalid", "artifactRootRelative must not contain empty components"))
    if TMP_PATH_PATTERN.search(stripped):
        problems.append(("artifact-path-tmp", "artifactRootRelative must not point at a temporary directory"))
    if USER_PATH_PATTERN.match(stripped):
        problems.append(("artifact-path-username", "artifactRootRelative must not embed a username/home path"))
    if not problems and all(part in (".", "..") for part in parts):
        problems.append(("artifact-path-invalid", "artifactRootRelative must name a concrete relative directory"))
    return problems


def record_identity(record):
    """Stable identity used for retry references; explicit recordId wins."""
    explicit = record.get("recordId") if isinstance(record, dict) else None
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    return "{}/{}".format(record.get("taskId"), record.get("condition"))


# --------------------------------------------------------------------------- #
# per-record validation
# --------------------------------------------------------------------------- #
def _validate_token_usage(value, err):
    if value is None:
        return
    if not isinstance(value, dict):
        err("token-usage-invalid", "tokenUsage", "tokenUsage must be an object or null")
        return
    allowed = {"input", "cachedInput", "output", "totalReported", "accounting"}
    for key in sorted(value):
        if key not in allowed:
            err("unknown-field", "tokenUsage." + key, "field is not part of the tokenUsage sub-schema")
    for name in ("input", "cachedInput", "output", "totalReported"):
        if name not in value:
            err("field-missing", "tokenUsage." + name, "missing token fields must be explicit null, never 0")
    counts = {}
    for name in ("input", "cachedInput", "output", "totalReported"):
        item = value.get(name)
        if item is None:
            counts[name] = None
            continue
        if not _is_int(item):
            err("token-usage-invalid", "tokenUsage." + name, "token counts must be integers or null")
            counts[name] = None
        elif item < 0:
            err("token-negative", "tokenUsage." + name, "token counts must not be negative")
            counts[name] = None
        else:
            counts[name] = item
    accounting = value.get("accounting")
    if accounting is None:
        accounting = DEFAULT_TOKEN_ACCOUNTING
    if accounting not in TOKEN_ACCOUNTING:
        err("token-accounting-unknown", "tokenUsage.accounting", "unknown token accounting convention")
        return
    total, prompt_in, cached, out = counts["totalReported"], counts["input"], counts["cachedInput"], counts["output"]
    if accounting == "input-includes-cached":
        # Declared convention: `input` is the full prompt total and already counts
        # cached input; totalReported = input + output.
        if prompt_in is not None and cached is not None and cached > prompt_in:
            err("token-cached-exceeds-input", "tokenUsage.cachedInput", "cachedInput must be a subset of an inclusive input")
        if prompt_in is not None and out is not None and total is not None and total != prompt_in + out:
            err(
                "token-total-inconsistent",
                "tokenUsage.totalReported",
                "with {!r}, totalReported must equal input + output".format(DEFAULT_TOKEN_ACCOUNTING),
            )
            if cached is not None and cached > 0 and total == prompt_in + cached + out:
                err(
                    "token-double-counted-cached",
                    "tokenUsage.totalReported",
                    "cachedInput added on top of an inclusive input double counts cached tokens",
                )
    else:
        if prompt_in is not None and cached is not None and out is not None and total is not None and total != prompt_in + cached + out:
            err(
                "token-total-inconsistent",
                "tokenUsage.totalReported",
                "with 'input-excludes-cached', totalReported must equal input + cachedInput + output",
            )


def _validate_cost(value, err):
    if value is None:
        return
    if not isinstance(value, dict):
        err("cost-invalid", "cost", "cost must be an object or null")
        return
    for key in sorted(value):
        if key not in ("amount", "currency"):
            err("unknown-field", "cost." + key, "field is not part of the cost sub-schema")
    if "amount" not in value:
        err("field-missing", "cost.amount", "missing cost fields must be explicit null, never 0")
    if "currency" not in value:
        err("field-missing", "cost.currency", "missing cost fields must be explicit null, never 0")
    amount, currency = value.get("amount"), value.get("currency")
    if amount is not None and not _is_number(amount):
        err("cost-invalid", "cost.amount", "cost.amount must be a number or null")
    elif _is_number(amount) and amount < 0:
        err("cost-negative", "cost.amount", "cost.amount must not be negative")
    if currency is not None and (not isinstance(currency, str) or CURRENCY_PATTERN.fullmatch(currency) is None):
        err("cost-currency-invalid", "cost.currency", "cost.currency must be an uppercase ISO 4217 code or null")
    elif currency is None and amount is not None:
        err("cost-currency-missing", "cost.currency", "a measured amount requires an explicit currency")
    elif currency is not None and amount is None:
        err("cost-amount-missing", "cost.amount", "a currency without an amount is not a measurement; use cost null")


def validate_record(record, index, inventory_trees):
    """Validate one record. Returns ``(errors, warnings)``."""
    if not isinstance(record, dict):
        return [_diag("record-invalid", "record must be a JSON object", None, "index:{}".format(index))], []
    identity = record_identity(record)
    errors = []
    warnings = []

    def err(code, field, message):
        errors.append(_diag(code, message, field, identity))

    def warn(code, field, message):
        warnings.append(_diag(code, message, field, identity))

    for key in sorted(record):
        if key in REQUIRED_FIELDS or key in OPTIONAL_FIELDS:
            continue
        if key in FORBIDDEN_REPLACEMENT:
            err("replacement-rejected", key, "task/condition replacement metadata is not permitted")
        elif key in FORBIDDEN_SELECTION:
            err("best-run-selection-rejected", key, "best-run selection metadata is not permitted")
        elif key in FORBIDDEN_SCORE:
            err("score-only-record-rejected", key, "scores belong in a separate judge packet, never in a run record")
        elif SECRET_KEY_PATTERN.search(key):
            err("secret-field-rejected", key, "credential-like field names must never appear in a run record")
        else:
            err("unknown-field", key, "field is not part of the pilot run-record schema")
    for name in REQUIRED_FIELDS:
        if name not in record:
            err("field-missing", name, "missing fields must be explicit null, never omitted and never 0")

    if "schemaVersion" in record and record.get("schemaVersion") is not None:
        if record.get("schemaVersion") != 1:
            err("schema-version-unsupported", "schemaVersion", "only schemaVersion 1 is supported")

    if record.get("studyId") != STUDY_ID:
        err("study-id-mismatch", "studyId", "studyId must equal {!r}".format(STUDY_ID))

    task = record.get("taskId")
    if task is not None:
        if not isinstance(task, str) or not task.strip():
            err("field-invalid", "taskId", "taskId must be a non-empty string")
            task = None
        else:
            if task not in inventory_trees:
                err("task-not-in-inventory", "taskId", "task is not one of the pinned inventory members")
            if task not in PILOT_TASKS:
                err("task-replacement", "taskId", "development-pilot cells are fixed to the four preselected tasks")

    condition = record.get("condition")
    if condition not in CONDITIONS:
        err("condition-invalid", "condition", "condition must be one of {}".format(list(CONDITIONS)))

    if record.get("runKind") not in RUN_KINDS:
        err("run-kind-invalid", "runKind", "runKind must be {!r}".format(RUN_KINDS[0]))

    attempt_kind = record.get("attemptKind")
    if attempt_kind not in ATTEMPT_KINDS:
        err("attempt-kind-invalid", "attemptKind", "attemptKind must be one of {}".format(list(ATTEMPT_KINDS)))

    for field in ("modelRequested", "modelResolved", "reasoning", "runnerVersion"):
        value = record.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            err("field-invalid", field, "{} must be a non-empty string or null".format(field))

    model_requested = record.get("modelRequested")
    model_resolved = record.get("modelResolved")
    identity_status = record.get("modelIdentityStatus")
    if identity_status not in MODEL_IDENTITY_STATUSES:
        err("model-identity-unknown", "modelIdentityStatus", "modelIdentityStatus must be one of {}".format(list(MODEL_IDENTITY_STATUSES)))
    else:
        if model_resolved is None and identity_status != "unverified":
            err("model-identity-fabricated", "modelResolved", "an unresolved model identity must be recorded as unverified")
        if identity_status in ("verified", "mismatch") and (model_resolved is None or model_requested is None):
            err("model-identity-fabricated", "modelResolved", "verified/mismatch requires both requested and resolved model strings")

    started_state, started = parse_timestamp(record.get("startedAt"))
    ended_state, ended = parse_timestamp(record.get("endedAt"))
    if started_state == "malformed":
        err("timestamp-malformed", "startedAt", "startedAt must be an ISO 8601 timestamp or null")
    if ended_state == "malformed":
        err("timestamp-malformed", "endedAt", "endedAt must be an ISO 8601 timestamp or null")

    wall = record.get("wallDurationMs")
    if wall is not None:
        if not _is_int(wall):
            err("field-invalid", "wallDurationMs", "wallDurationMs must be an integer or null")
        elif wall < 0:
            err("duration-negative", "wallDurationMs", "wallDurationMs must not be negative")
    timeout = record.get("timeoutSeconds")
    if timeout is not None:
        if not _is_int(timeout):
            err("field-invalid", "timeoutSeconds", "timeoutSeconds must be an integer or null")
        elif timeout < 0:
            err("duration-negative", "timeoutSeconds", "timeoutSeconds must not be negative")

    if started_state == "ok" and ended_state == "ok":
        if ended < started:
            err("duration-ended-before-started", "endedAt", "endedAt must not precede startedAt")
        elif _is_int(wall) and wall >= 0:
            delta = int((ended - started).total_seconds() * 1000)
            if abs(delta - wall) > DURATION_TOLERANCE_MS:
                err("duration-inconsistent", "wallDurationMs", "wallDurationMs disagrees with startedAt/endedAt beyond tolerance")

    exit_code = record.get("exitCode")
    if exit_code is not None and not _is_int(exit_code):
        err("field-invalid", "exitCode", "exitCode must be an integer or null")

    status = record.get("status")
    if status not in STATUSES:
        err("status-unknown", "status", "status must be one of {}".format(list(STATUSES)))

    for field in ("solverOutputPresent", "patchPresent"):
        value = record.get(field)
        if value is not None and not isinstance(value, bool):
            err("field-invalid", field, "{} must be a boolean or null".format(field))

    judge = record.get("judgeStatus")
    if judge is not None:
        if judge not in JUDGE_STATUSES:
            err("judge-status-unknown", "judgeStatus", "judgeStatus must be one of {}".format(list(JUDGE_STATUSES)))
        elif judge == "scored" and status in ("timeout", "setup-error", "solver-error", "judge-error"):
            err(
                "non-solver-outcome-cannot-be-scored",
                "judgeStatus",
                "status {!r} must never be recorded as a scored solver result".format(status),
            )
        elif judge == "judge-error" and status == "success":
            warn("judge-error-with-success-status", "judgeStatus", "solver success with a failed judge must not be read as a score")

    if status == "judge-error" and judge == "scored":
        err("judge-error-cannot-be-scored", "judgeStatus", "a judge error must never be converted into a solver score")

    artifact = record.get("artifactRootRelative")
    if artifact is not None:
        for code, message in artifact_path_diagnostics(artifact):
            err(code, "artifactRootRelative", message)

    material = record.get("materialManifestSha256")
    if material is not None and not is_sha256(material):
        err("material-hash-malformed", "materialManifestSha256", "materialManifestSha256 must be 64 lowercase hex characters")
    tree = record.get("taskTreeSha")
    if tree is not None:
        if not is_git_sha(tree):
            err("task-tree-malformed", "taskTreeSha", "taskTreeSha must be a 40-character lowercase git object id")
        elif task is not None and task in inventory_trees and tree != inventory_trees[task]:
            err("task-tree-mismatch", "taskTreeSha", "taskTreeSha does not match the pinned inventory tree for {}".format(task))

    needs_provenance = bool(record.get("solverOutputPresent")) or bool(record.get("patchPresent")) or status == "success"
    if needs_provenance:
        for field in ("artifactRootRelative", "materialManifestSha256", "taskTreeSha"):
            if record.get(field) is None:
                err("missing-artifact-provenance", field, "a record with a produced artifact must carry full provenance")

    if status == "success" and record.get("solverOutputPresent") is not True:
        err("success-without-output", "solverOutputPresent", "success requires a recorded solver output artifact")
    if status == "task-failure":
        evidence = (
            record.get("solverOutputPresent") is True
            or record.get("patchPresent") is True
            or judge == "scored"
        )
        if not evidence:
            err("task-failure-without-evidence", None, "task-failure requires solver output, a patch, or a scored judge packet")

    _validate_token_usage(record.get("tokenUsage"), err)
    _validate_cost(record.get("cost"), err)

    exceptions = record.get("exceptions")
    if exceptions is not None:
        if not isinstance(exceptions, list):
            err("field-invalid", "exceptions", "exceptions must be an array of strings or null")
        else:
            for item in exceptions:
                if not isinstance(item, str) or not item.strip():
                    err("field-invalid", "exceptions", "exception entries must be non-empty strings")

    retry_of = record.get("retryOf")
    if retry_of is not None and (not isinstance(retry_of, str) or not retry_of.strip()):
        err("field-invalid", "retryOf", "retryOf must be a non-empty record reference or null")
    if attempt_kind == "retry" and retry_of is None:
        err("hidden-retry", "retryOf", "a retry attempt must reference the original attempt it retries")

    record_id = record.get("recordId")
    if record_id is not None and (not isinstance(record_id, str) or RECORD_ID_PATTERN.fullmatch(record_id) is None):
        err("record-id-invalid", "recordId", "recordId must match [A-Za-z0-9._:-]+ or be null")

    notes = record.get("notes")
    if notes is not None and (not isinstance(notes, str) or not notes.strip()):
        err("field-invalid", "notes", "notes must be a non-empty string or null")

    return errors, warnings


# --------------------------------------------------------------------------- #
# record-set validation (retry chains, duplicates, completeness)
# --------------------------------------------------------------------------- #
def validate_set(records):
    """Cross-record checks. Returns ``(errors, warnings, summary)``."""
    errors = []
    warnings = []
    cells = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        cells.setdefault((record.get("taskId"), record.get("condition")), []).append((index, record))

    identities = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        identity = record_identity(record)
        if identity in identities:
            if isinstance(record.get("recordId"), str) and record.get("recordId").strip():
                errors.append(_diag("duplicate-record-id", "recordId {!r} is used more than once".format(identity), "recordId", identity))
            else:
                errors.append(_diag("duplicate-cell", "cell {!r} appears more than once without a retry link".format(identity), None, identity))
        else:
            identities[identity] = (index, record)

    retry_edges = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict) or record.get("attemptKind") != "retry":
            continue
        identity = record_identity(record)
        reference = record.get("retryOf")
        if not isinstance(reference, str) or not reference.strip():
            errors.append(_diag("hidden-retry", "retry {!r} does not declare retryOf".format(identity), "retryOf", identity))
            continue
        if reference not in identities:
            errors.append(_diag("retry-unregistered", "retryOf {!r} has no matching record".format(reference), "retryOf", identity))
            continue
        _, target = identities[reference]
        if (target.get("taskId"), target.get("condition")) != (record.get("taskId"), record.get("condition")):
            errors.append(_diag("retry-cell-mismatch", "retry must target an attempt in the same task+condition cell", "retryOf", identity))
            continue
        retry_edges[identity] = reference

    for start in sorted(retry_edges):
        seen = []
        node = start
        while node in retry_edges:
            if node in seen:
                errors.append(_diag("retry-cycle", "retryOf loop detected: {}".format(" -> ".join(seen + [node])), "retryOf", start))
                break
            seen.append(node)
            node = retry_edges[node]
        else:
            target = identities.get(node, (None, None))[1]
            if target is not None and target.get("attemptKind") != "original":
                errors.append(_diag("retry-chain-broken", "retry chain does not terminate at an original attempt", "retryOf", start))

    duplicate_cells = []
    unresolved = 0
    terminal_cells = 0
    for cell in sorted(cells, key=lambda c: (str(c[0]), str(c[1]))):
        entries = cells[cell]
        cell_records = [record for _, record in entries]
        originals = [record for record in cell_records if record.get("attemptKind") == "original"]
        retries = [record for record in cell_records if record.get("attemptKind") == "retry"]
        label = "{}/{}".format(cell[0], cell[1])
        if len(originals) > 1:
            errors.append(_diag("duplicate-original-attempt", "cell {!r} has more than one original attempt".format(label), None, label))
        if retries and not originals:
            errors.append(_diag("missing-original-attempt", "cell {!r} has retries but the original attempt is absent".format(label), None, label))
        resolved = len(originals) == 1 and len(retries) == len(cell_records) - 1 and not any(
            record.get("attemptKind") not in ATTEMPT_KINDS for record in cell_records
        )
        if len(cell_records) > 1 and not resolved:
            duplicate_cells.append(cell)
        if any(record.get("status") in TERMINAL_STATUSES for record in cell_records):
            terminal_cells += 1
        for record in retries:
            if record.get("status") not in TERMINAL_STATUSES:
                unresolved += 1

    summary = {
        "cells": [(cell[0], cell[1]) for cell in sorted(cells, key=lambda c: (str(c[0]), str(c[1])))],
        "duplicateCells": sorted(duplicate_cells, key=lambda c: (str(c[0]), str(c[1]))),
        "unresolvedRetries": unresolved,
        "terminalCellCount": terminal_cells,
        "retryEdges": sorted(retry_edges.items()),
    }
    return errors, warnings, summary


# --------------------------------------------------------------------------- #
# authority loading
# --------------------------------------------------------------------------- #
def load_authority():
    try:
        config = json.loads(CONFIG_PATH.read_text())
        inventory = json.loads(INVENTORY_PATH.read_text())
        plan = json.loads(PLAN_PATH.read_text())
    except FileNotFoundError as error:
        raise ConfigError("authority file missing: {}".format(error))
    except json.JSONDecodeError as error:
        raise ConfigError("authority file is not valid JSON: {}".format(error))
    tasks = inventory.get("tasks")
    if not isinstance(tasks, list):
        raise ConfigError("inventory.json has no 'tasks' array")
    trees = {}
    for entry in tasks:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            trees[entry["id"]] = entry.get("treeSha")
    if config.get("id") != STUDY_ID:
        raise ConfigError("study config id {!r} does not match {!r}".format(config.get("id"), STUDY_ID))
    return config, inventory, plan, trees


def expected_cells(plan):
    """Sorted unique (taskId, condition) cells declared by the pilot plan."""
    cells = []
    trials = plan.get("trials") if isinstance(plan, dict) else None
    if not isinstance(trials, list):
        return []
    for trial in trials:
        if not isinstance(trial, dict):
            continue
        task, arm = trial.get("task"), trial.get("arm")
        if isinstance(task, str) and isinstance(arm, str):
            cells.append((task, arm))
    return sorted(set(cells), key=lambda c: (c[0], c[1]))


def plan_diagnostics(plan, inventory_trees):
    """Validate the pilot plan itself. Returns ``(errors, warnings)``."""
    errors = []
    warnings = []
    trials = plan.get("trials")
    if not isinstance(trials, list):
        return [_diag("plan-invalid", "pilot.json must contain a 'trials' array", "trials", "pilot.json")], []
    seen = set()
    for index, trial in enumerate(trials):
        if not isinstance(trial, dict):
            errors.append(_diag("plan-invalid", "trial {} is not an object".format(index), "trials", "pilot.json"))
            continue
        task, arm = trial.get("task"), trial.get("arm")
        if not isinstance(task, str) or task not in inventory_trees:
            errors.append(_diag("plan-task-not-in-inventory", "trial task {!r} is not a pinned inventory member".format(task), "task", "pilot.json"))
        if arm not in CONDITIONS:
            errors.append(_diag("plan-condition-invalid", "trial arm {!r} is not one of {}".format(arm, list(CONDITIONS)), "arm", "pilot.json"))
        cell = (task, arm)
        if cell in seen:
            errors.append(_diag("plan-duplicate-cell", "trial cell {}/{} appears more than once".format(task, arm), None, "pilot.json"))
        seen.add(cell)
        if trial.get("developmentOnly") is not True:
            warnings.append(_diag("plan-not-development-only", "trial {}/{} is not marked developmentOnly".format(task, arm), "developmentOnly", "pilot.json"))
        if trial.get("solverExecuted") is not False:
            warnings.append(_diag("plan-solver-executed-flag", "trial {}/{} does not record solverExecuted=false".format(task, arm), "solverExecuted", "pilot.json"))
    required = {(task, arm) for task in PILOT_TASKS for arm in CONDITIONS}
    for cell in sorted(required - seen, key=lambda c: (c[0], c[1])):
        errors.append(_diag("plan-missing-cell", "pilot plan is missing {}/{}".format(cell[0], cell[1]), None, "pilot.json"))
    for cell in sorted(seen - required, key=lambda c: (str(c[0]), str(c[1]))):
        errors.append(_diag("plan-extra-cell", "pilot plan declares unexpected cell {}/{}".format(cell[0], cell[1]), None, "pilot.json"))
    if plan.get("solverCalls") not in (0, None):
        warnings.append(_diag("plan-solver-calls", "pilot.json reports solverCalls={!r}; no pilot run is claimed by this validator".format(plan.get("solverCalls")), "solverCalls", "pilot.json"))
    return errors, warnings


def inventory_task_ids(inventory):
    tasks = inventory.get("tasks")
    if not isinstance(tasks, list):
        return []
    return sorted(entry.get("id") for entry in tasks if isinstance(entry, dict) and isinstance(entry.get("id"), str))


# --------------------------------------------------------------------------- #
# record discovery
# --------------------------------------------------------------------------- #
def extract_records(document, source):
    if isinstance(document, list):
        return document
    if isinstance(document, dict):
        records = document.get("records")
        if isinstance(records, list):
            return records
        return [document]
    raise ConfigError("{}: JSON document must be a record object or an array of records".format(source))


def load_json(path, source):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        raise ConfigError("{}: file not found".format(source))
    except json.JSONDecodeError as error:
        raise ConfigError("{}: invalid JSON ({})".format(source, error))


def load_records_from_file(path, source=None):
    source = source or str(path)
    document = load_json(path, source)
    return source, extract_records(document, source)


def load_records_from_directory(directory):
    base = Path(directory)
    entries = []
    for path in sorted(base.glob("*.json"), key=lambda p: p.name):
        entries.append(load_records_from_file(path, "{}".format(path.name)))
    return entries


# --------------------------------------------------------------------------- #
# report construction
# --------------------------------------------------------------------------- #
def _cells_json(cells):
    return [{"taskId": task, "condition": condition} for task, condition in sorted(cells, key=lambda c: (str(c[0]), str(c[1])))]


def _state(record_count, errors, pilot_complete):
    if errors:
        return "invalid"
    if record_count == 0:
        return "not-started"
    if pilot_complete:
        return "complete"
    return "in-progress"


def build_report(
    mode,
    config,
    records,
    inventory,
    plan,
    inventory_trees,
    errors,
    warnings,
    summary=None,
    files=None,
    source=None,
    record_count=None,
    plan_errors=(),
    plan_warnings=(),
):
    plan_cells = set(expected_cells(plan))
    summary = summary or {}
    present = set(summary.get("cells", []))
    missing = sorted(plan_cells - present, key=lambda c: (str(c[0]), str(c[1])))
    extra = sorted(present - plan_cells, key=lambda c: (str(c[0]), str(c[1])))
    duplicates = summary.get("duplicateCells", [])
    terminal_cells = summary.get("terminalCellCount", 0)
    unresolved = summary.get("unresolvedRetries", 0)
    pilot_complete = (
        not errors
        and not plan_errors
        and set(plan_cells) == present
        and terminal_cells == len(plan_cells)
        and unresolved == 0
    )
    count = record_count if record_count is not None else len(records)
    report = {
        "validator": VALIDATOR_NAME,
        "version": VALIDATOR_VERSION,
        "mode": mode,
        "studyId": STUDY_ID,
        "schema": "paper/study-v1/run-record.schema.json",
        "authority": {
            "config": "paper/study-v1/config.json",
            "plan": "paper/study-v1/qc/pilot.json",
            "inventory": "paper/audit/task-annotation-v1/inventory.json",
            "inventoryTaskCount": len(inventory_task_ids(inventory)),
            "formalRunAllowed": config.get("formalRunAllowed"),
            "studyStatus": config.get("status"),
        },
        "source": source,
        "files": files or [],
        "recordCount": count,
        "expectedCellCount": len(plan_cells),
        "presentCellCount": len(present),
        "terminalCellCount": terminal_cells,
        "expectedCells": _cells_json(plan_cells),
        "presentCells": _cells_json(present),
        "missingCells": _cells_json(missing),
        "duplicateCells": _cells_json(duplicates),
        "extraCells": _cells_json(extra),
        "unresolvedRetries": unresolved,
        "pilotComplete": bool(pilot_complete),
        "state": _state(count, list(errors) + list(plan_errors), pilot_complete),
        "valid": not errors and not plan_errors,
        "errors": sort_diags(list(errors) + list(plan_errors)),
        "warnings": sort_diags(list(warnings) + list(plan_warnings)),
    }
    return report


def evaluate_records(records, inventory, plan, inventory_trees):
    """Run per-record and set-level validation over a combined record list."""
    errors = []
    warnings = []
    plan_material = {}
    for trial in plan.get("trials", []) if isinstance(plan, dict) else []:
        if isinstance(trial, dict) and isinstance(trial.get("task"), str) and isinstance(trial.get("arm"), str):
            plan_material[(trial["task"], trial["arm"])] = trial.get("materialSha256")
    for index, record in enumerate(records):
        record_errors, record_warnings = validate_record(record, index, inventory_trees)
        if isinstance(record, dict):
            material = record.get("materialManifestSha256")
            cell = (record.get("taskId"), record.get("condition"))
            expected = plan_material.get(cell)
            if material is not None and isinstance(expected, str) and material != expected:
                errors.append(
                    _diag(
                        "material-hash-mismatch",
                        "materialManifestSha256 does not match the pilot plan hash for {}/{}".format(*cell),
                        "materialManifestSha256",
                        record_identity(record),
                    )
                )
        errors.extend(record_errors)
        warnings.extend(record_warnings)
    set_errors, set_warnings, summary = validate_set(records)
    errors.extend(set_errors)
    warnings.extend(set_warnings)
    return errors, warnings, summary


# --------------------------------------------------------------------------- #
# modes
# --------------------------------------------------------------------------- #
def _records_for_plan(path):
    """Return ``(records, files, source, exists)`` for the plan's records path.

    The default location is ``paper/study-v1/qc/runs``; when it does not exist yet
    the plan is reported as ``not-started`` rather than as a configuration error.
    An explicitly supplied path that is missing is a configuration error.
    """
    explicit = path is not None
    candidate = Path(path) if explicit else DEFAULT_RECORDS_DIR
    if not candidate.exists():
        if explicit:
            raise ConfigError("records path not found: {}".format(path))
        return [], [], str(candidate), False
    if candidate.is_dir():
        entries = load_records_from_directory(candidate)
        records = [record for _, block in entries for record in block]
        files = [{"name": name, "recordCount": len(block)} for name, block in entries]
        return records, files, str(candidate), True
    source, block = load_records_from_file(candidate)
    return block, [{"name": source, "recordCount": len(block)}], source, True


def run_check_plan(records_path):
    config, inventory, plan, inventory_trees = load_authority()
    plan_errors, plan_warnings = plan_diagnostics(plan, inventory_trees)
    records, files, source, exists = _records_for_plan(records_path)
    errors, warnings, summary = evaluate_records(records, inventory, plan, inventory_trees)
    if records:
        # With records present the set must cover the plan exactly; an empty
        # repository is reported as `not-started` instead.
        plan_cells = set(expected_cells(plan))
        present = set(summary.get("cells", []))
        for cell in sorted(plan_cells - present, key=lambda c: (str(c[0]), str(c[1]))):
            errors.append(_diag("missing-cell", "record set is missing plan cell {}/{}".format(cell[0], cell[1]), None, "plan"))
        for cell in sorted(present - plan_cells, key=lambda c: (str(c[0]), str(c[1]))):
            errors.append(_diag("extra-cell", "record set contains non-plan cell {}/{}".format(cell[0], cell[1]), None, "plan"))
    report = build_report(
        "check-plan",
        config,
        records,
        inventory,
        plan,
        inventory_trees,
        errors,
        warnings,
        summary=summary,
        files=files,
        source=source,
        plan_errors=plan_errors,
        plan_warnings=plan_warnings,
    )
    report["recordsPathExists"] = exists
    return report


def run_check_record(path):
    config, inventory, plan, inventory_trees = load_authority()
    source, records = load_records_from_file(path)
    errors, warnings, summary = evaluate_records(records, inventory, plan, inventory_trees)
    report = build_report(
        "check-record",
        config,
        records,
        inventory,
        plan,
        inventory_trees,
        errors,
        warnings,
        summary=summary,
        source=source,
    )
    return report


def run_check_directory(directory):
    config, inventory, plan, inventory_trees = load_authority()
    base = Path(directory)
    if not base.exists():
        raise ConfigError("directory not found: {}".format(directory))
    if not base.is_dir():
        raise ConfigError("not a directory: {}".format(directory))
    entries = load_records_from_directory(base)
    records = [record for _, block in entries for record in block]
    errors, warnings, summary = evaluate_records(records, inventory, plan, inventory_trees)
    files = []
    for name, block in entries:
        file_errors = []
        for index, record in enumerate(block):
            record_errors, _ = validate_record(record, index, inventory_trees)
            file_errors.extend(record_errors)
        files.append({"name": name, "recordCount": len(block), "valid": not file_errors, "errorCount": len(file_errors)})
    report = build_report(
        "check-directory",
        config,
        records,
        inventory,
        plan,
        inventory_trees,
        errors,
        warnings,
        summary=summary,
        files=files,
        source=str(base),
    )
    return report


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
class _Parser(argparse.ArgumentParser):
    def error(self, message):
        emit(
            {
                "validator": VALIDATOR_NAME,
                "version": VALIDATOR_VERSION,
                "mode": "usage",
                "state": "config-error",
                "valid": False,
                "pilotComplete": False,
                "errors": [_diag("usage-error", message, None, "argv")],
                "warnings": [],
            }
        )
        raise SystemExit(2)


def emit(report):
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def main(argv=None):
    parser = _Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check-plan", action="store_true", help="validate the 16-cell plan; accepts not-started")
    group.add_argument("--check-record", metavar="FILE", help="validate one record JSON file or record set")
    group.add_argument("--check-directory", metavar="DIR", help="validate a directory of *.json records")
    parser.add_argument("--records", metavar="PATH", help="optional record file/directory used by --check-plan")
    args = parser.parse_args(argv)
    try:
        if args.check_plan:
            report = run_check_plan(args.records)
        elif args.check_record:
            report = run_check_record(args.check_record)
        else:
            report = run_check_directory(args.check_directory)
    except ConfigError as error:
        emit(
            {
                "validator": VALIDATOR_NAME,
                "version": VALIDATOR_VERSION,
                "mode": "config",
                "state": "config-error",
                "valid": False,
                "pilotComplete": False,
                "errors": [_diag("config-error", str(error), None, "config")],
                "warnings": [],
            }
        )
        return 2
    emit(report)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
