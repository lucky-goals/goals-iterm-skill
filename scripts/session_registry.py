"""Small, local, assertion-only registry for iTerm/CLI session ownership.

The registry is deliberately not a source of authorization or live terminal
truth.  It only records assertions made by a coordinator. It never sends
input, closes a terminal, or decides that a terminal is safe to close.

State lives outside the repository by default and is protected with a local
``fcntl`` lock. Mutations use per-record optimistic revisions so an old
coordinator cannot silently overwrite a newer observation.

CLI examples::

    python scripts/session_registry.py register --record record.json
    python scripts/session_registry.py update --session-id S1 \
        --coordinator-id C1 --generation 1 --expected-revision 1 \
        --patch patch.json
    python scripts/session_registry.py handoff --session-id S1 \
        --coordinator-id C1 --generation 1 --expected-revision 2 \
        --new-coordinator-id C2 --new-task-id task-2 \
        --audit-path /abs/audit-2.md --reason "resume work"
    python scripts/session_registry.py report --task-id task-2 --require-settled

Use ``--path PATH`` before or after the subcommand to select a state file.
"""

from __future__ import annotations

import argparse
import copy
import datetime as _datetime
import errno
import fcntl
import json
import os
from pathlib import Path
import stat
import tempfile
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Mapping


SCHEMA_VERSION = 1
DEFAULT_STATE_PATH = Path.home() / ".local" / "state" / "goals-iterm-skill" / "session-registry.json"

ORIGINS = frozenset({"created", "adopted", "borrowed", "unknown"})
CLEANUP_POLICIES = frozenset({"auto_owned", "retain"})
EXECUTION_STATUSES = frozenset({"running", "waiting_user", "completed", "failed", "canceled", "paused"})
CLEANUP_STATUSES = frozenset({"pending", "closing", "closed", "retained", "blocked", "unknown"})
RECOVERY_STATUSES = frozenset({"unknown", "ready", "degraded", "not_applicable"})
COORDINATOR_PHASES = frozenset({"active", "finalizing", "settled"})
MONITOR_STATUSES = frozenset({"unknown", "running", "stopped", "failed"})

REQUIRED_FIELDS = frozenset(
    {"session_id", "owner_task_id", "coordinator_id", "origin", "cleanup_policy", "audit_path"}
)
CONTROLLED_FIELDS = frozenset(
    {
        "session_id",
        "owner_task_id",
        "coordinator_id",
        "generation",
        "revision",
        "created_at",
        "updated_at",
        "handoff_reason",
        "handoff_at",
        "origin",
    }
)
IDENTITY_FIELDS = frozenset(
    {
        "window_id",
        "tab_id",
        "session_epoch",
        "broker_epoch",
        "cli",
        "chat_uuid",
        "identity_source",
        "process_identity",
        "owned_container",
    }
)
OPTIONAL_FIELDS = frozenset(
    {
        "generation",
        "revision",
        "execution_status",
        "cleanup_status",
        "recovery_status",
        "coordinator_phase",
        "created_at",
        "updated_at",
        "window_id",
        "tab_id",
        "session_epoch",
        "broker_epoch",
        "cli",
        "chat_uuid",
        "identity_source",
        "process_identity",
        "owned_container",
        "evidence",
        "monitor_status",
        "cleanup_reason",
        "cleanup_authorization",
        "retention_reason",
        "retain_until",
        "next_check_at",
        "schedule_handle",
        "remaining_work",
        "acceptance_evidence",
        "recovery_record_path",
        # Registry metadata, not inputs to an iTerm operation.
        "handoff_reason",
        "handoff_at",
    }
)
ALLOWED_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS
RESET_ON_NEW_GENERATION = (
    "cleanup_reason",
    "retention_reason",
    "retain_until",
    "next_check_at",
    "schedule_handle",
    "acceptance_evidence",
    "recovery_record_path",
    "monitor_status",
    "remaining_work",
    "chat_uuid",
    "identity_source",
    "process_identity",
    "owned_container",
    "evidence",
)
IDENTITY_CHANGE_FORBIDDEN_FIELDS = frozenset(
    {
        "execution_status",
        "cleanup_status",
        "recovery_status",
        "coordinator_phase",
        "monitor_status",
        "cleanup_reason",
        "retention_reason",
        "retain_until",
        "next_check_at",
        "schedule_handle",
        "remaining_work",
        "acceptance_evidence",
        "recovery_record_path",
    }
)
CROSS_TASK_CLEAR_FIELDS = ("window_id", "tab_id", "session_epoch", "broker_epoch", "owned_container")


class RegistryError(ValueError):
    """A user-correctable registry, schema, or optimistic-concurrency error."""


def _utc_now() -> str:
    """Return an actual, timezone-aware UTC timestamp suitable for records."""

    return _datetime.datetime.now(_datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _absolute_path(value: os.PathLike[str] | str) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(value))))


def _state_path(value: os.PathLike[str] | str | None) -> Path:
    return _absolute_path(DEFAULT_STATE_PATH if value is None else value)


def _fail(message: str) -> None:
    raise RegistryError(message)


def _require_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{name} must be a non-empty string")
    return value


def _require_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _fail(f"{name} must be an integer >= 1")
    return value


def _validate_timestamp(value: Any, name: str) -> None:
    if not isinstance(value, str):
        _fail(f"{name} must be an ISO-8601 UTC timestamp")
    try:
        parsed = _datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RegistryError(f"{name} must be an ISO-8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.utcoffset() != _datetime.timedelta(0):
        _fail(f"{name} must include a UTC offset")


def _validate_optional_path(value: Any, name: str) -> None:
    if value is not None and (not isinstance(value, str) or not os.path.isabs(value)):
        _fail(f"{name} must be an absolute path")


def _validate_record(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        _fail("record must be a JSON object")
    unknown = set(record) - ALLOWED_FIELDS
    if unknown:
        _fail(f"unknown record field(s): {', '.join(sorted(unknown))}")
    missing = REQUIRED_FIELDS - set(record)
    if missing:
        _fail(f"missing required record field(s): {', '.join(sorted(missing))}")

    result = dict(record)
    result.setdefault("generation", 1)
    result.setdefault("revision", 1)
    result.setdefault("execution_status", "running")
    result.setdefault("cleanup_status", "pending")
    result.setdefault("recovery_status", "unknown")
    result.setdefault("coordinator_phase", "active")
    result.setdefault("monitor_status", "unknown")
    for field in ("session_id", "owner_task_id", "coordinator_id"):
        _require_nonempty_string(result[field], field)
    if result["origin"] not in ORIGINS:
        _fail(f"origin must be one of: {', '.join(sorted(ORIGINS))}")
    if result["cleanup_policy"] not in CLEANUP_POLICIES:
        _fail(f"cleanup_policy must be one of: {', '.join(sorted(CLEANUP_POLICIES))}")
    if not isinstance(result["audit_path"], str) or not os.path.isabs(result["audit_path"]):
        _fail("audit_path must be an absolute path")

    _require_integer(result.get("generation", 1), "generation")
    _require_integer(result.get("revision", 1), "revision")
    for field, allowed in (
        ("execution_status", EXECUTION_STATUSES),
        ("cleanup_status", CLEANUP_STATUSES),
        ("recovery_status", RECOVERY_STATUSES),
        ("coordinator_phase", COORDINATOR_PHASES),
        ("monitor_status", MONITOR_STATUSES),
    ):
        if field in result and result[field] not in allowed:
            _fail(f"{field} must be one of: {', '.join(sorted(allowed))}")

    for field in ("created_at", "updated_at", "handoff_at", "retain_until", "next_check_at"):
        if field in result and result[field] is not None:
            _validate_timestamp(result[field], field)
    _validate_optional_path(result.get("recovery_record_path"), "recovery_record_path")

    if "process_identity" in result and result["process_identity"] is not None:
        if not isinstance(result["process_identity"], dict):
            _fail("process_identity must be a JSON object")
    if "owned_container" in result and result["owned_container"] is not None:
        container = result["owned_container"]
        if not isinstance(container, dict):
            _fail("owned_container must be a JSON object or null")
        if not container:
            _fail("owned_container must contain at least one field")
        unknown_container_fields = set(container) - {"tab_id", "window_id", "basis"}
        if unknown_container_fields:
            _fail(f"unknown owned_container field(s): {', '.join(sorted(unknown_container_fields))}")
        for field, value in container.items():
            if value is not None and (not isinstance(value, str) or not value.strip()):
                _fail(f"owned_container.{field} must be a non-empty string or null")
    if "remaining_work" in result and result["remaining_work"] is not None:
        if not isinstance(result["remaining_work"], list):
            _fail("remaining_work must be a JSON list")
    if "handoff_reason" in result:
        _require_nonempty_string(result["handoff_reason"], "handoff_reason")
    for field in ("cleanup_reason", "cleanup_authorization", "retention_reason", "schedule_handle"):
        if field in result and result[field] is not None and not isinstance(result[field], str):
            _fail(f"{field} must be a string")
    if "cleanup_authorization" in result:
        _require_nonempty_string(result["cleanup_authorization"], "cleanup_authorization")
    for field in ("window_id", "tab_id", "session_epoch", "broker_epoch", "cli", "chat_uuid", "identity_source"):
        if field in result and result[field] is not None:
            if isinstance(result[field], bool) or not isinstance(result[field], (str, int, float)):
                _fail(f"{field} must be a string or number")
    return result


def _new_record(input_record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and fill defaults for a newly registered record."""

    record = dict(input_record)
    if "generation" in record and record["generation"] != 1:
        _fail("new records must start at generation 1")
    if "revision" in record and record["revision"] != 1:
        _fail("new records must start at revision 1")
    record.setdefault("generation", 1)
    record.setdefault("revision", 1)
    record.setdefault("execution_status", "running")
    record.setdefault("cleanup_status", "pending")
    record.setdefault("recovery_status", "unknown")
    record.setdefault("coordinator_phase", "active")
    record.setdefault("monitor_status", "unknown")
    now = _utc_now()
    record.setdefault("created_at", now)
    record.setdefault("updated_at", now)
    return _validate_record(record)


def _reject_symlink(path: Path, label: str) -> None:
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(mode):
        _fail(f"{label} path must not be a symlink: {path}")


def _ensure_parent_directory(path: Path) -> None:
    """Create missing parent components privately and validate directories."""

    parent = path.parent
    current = Path(parent.anchor) if parent.anchor else Path()
    parts = parent.parts[1:] if parent.anchor else parent.parts
    for component in parts:
        current = current / component
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            try:
                os.mkdir(current, 0o700)
            except FileExistsError:
                mode = os.lstat(current).st_mode
            else:
                continue
        # System paths such as macOS /var commonly contain legitimate
        # symlinked parent components.  The state and lock *leaf* paths are
        # rejected separately; a parent symlink is fine when it resolves to a
        # directory.
        if stat.S_ISLNK(mode):
            if not os.path.isdir(current):
                _fail(f"state parent symlink does not resolve to a directory: {current}")
            continue
        if not stat.S_ISDIR(mode):
            _fail(f"state parent is not a directory: {current}")


def _assert_private_mode(path: Path, mode: int) -> None:
    if mode & 0o077:
        _fail(f"{path} must be private (owner-only mode)")


def _assert_regular(path: Path, mode: int, label: str) -> None:
    if not stat.S_ISREG(mode):
        _fail(f"{label} path must be a regular file: {path}")


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """Take an actual local advisory lock on a private sibling lock file."""

    _ensure_parent_directory(path)
    _reject_symlink(path, "state")
    lock_path = Path(str(path) + ".lock")
    _reject_symlink(lock_path, "lock")
    flags = os.O_RDWR | os.O_CREAT | os.O_NONBLOCK
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            _fail(f"lock path must not be a symlink: {lock_path}")
        raise RegistryError(f"cannot open lock path {lock_path}: {exc}") from exc
    try:
        mode = os.fstat(fd).st_mode
        _assert_regular(lock_path, mode, "lock")
        _assert_private_mode(lock_path, mode)
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            _reject_symlink(path, "state")
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _read_state(path: Path) -> dict[str, Any]:
    _reject_symlink(path, "state")
    if not os.path.lexists(path):
        return {"schema_version": SCHEMA_VERSION, "records": {}}
    flags = os.O_RDONLY | os.O_NONBLOCK
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            _fail(f"state path must not be a symlink: {path}")
        raise RegistryError(f"cannot read state path {path}: {exc}") from exc
    try:
        mode = os.fstat(fd).st_mode
        _assert_regular(path, mode, "state")
        _assert_private_mode(path, mode)
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = -1
            try:
                state = json.load(stream)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise RegistryError(f"state file is corrupt JSON: {path}") from exc
    finally:
        if fd != -1:
            os.close(fd)
    return _validate_state(state)


def _validate_state(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        _fail("state root must be a JSON object")
    if state.get("schema_version") != SCHEMA_VERSION:
        _fail(f"unsupported schema_version {state.get('schema_version')!r}; expected {SCHEMA_VERSION}")
    records = state.get("records")
    if not isinstance(records, dict):
        _fail("state records must be a JSON object")
    validated: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "records": {}}
    for key, value in records.items():
        if not isinstance(key, str) or not key:
            _fail("state record keys must be non-empty strings")
        record = _validate_record(value)
        if record["session_id"] != key:
            _fail(f"state key {key!r} does not match record session_id")
        validated["records"][key] = record
    return validated


def _write_state(path: Path, state: Mapping[str, Any]) -> None:
    _ensure_parent_directory(path)
    _reject_symlink(path, "state")
    if os.path.lexists(path):
        mode = os.lstat(path).st_mode
        _assert_regular(path, mode, "state")
        _assert_private_mode(path, mode)
    payload = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    fd = -1
    temporary: str | None = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent), text=True)
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            fd = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            directory_fd = -1
        if directory_fd != -1:
            try:
                try:
                    os.fsync(directory_fd)
                except OSError:
                    # Some filesystems do not support directory fsync.  The
                    # file itself was already fsynced before replacement.
                    pass
            finally:
                os.close(directory_fd)
    finally:
        if fd != -1:
            os.close(fd)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _mutate(path: Path, operation: Callable[[dict[str, Any]], Any]) -> Any:
    with _file_lock(path):
        state = _read_state(path)
        result = operation(state)
        _validate_state(state)
        _write_state(path, state)
        return copy.deepcopy(result)


def _read_json_object(path: os.PathLike[str] | str, label: str) -> dict[str, Any]:
    input_path = _absolute_path(path)
    try:
        with input_path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except FileNotFoundError as exc:
        raise RegistryError(f"{label} file not found: {input_path}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RegistryError(f"{label} file is corrupt JSON: {input_path}") from exc
    if not isinstance(value, dict):
        _fail(f"{label} must contain a JSON object")
    return value


def register_record(record: Mapping[str, Any], path: os.PathLike[str] | str | None = None) -> dict[str, Any]:
    """Register a new session, refusing to overwrite an existing session ID."""

    normalized = _new_record(record)
    state_path = _state_path(path)

    def operation(state: dict[str, Any]) -> dict[str, Any]:
        session_id = normalized["session_id"]
        if session_id in state["records"]:
            _fail(f"session_id already registered: {session_id}")
        state["records"][session_id] = normalized
        return normalized

    return _mutate(state_path, operation)


def _guard(record: Mapping[str, Any], session_id: str, coordinator_id: str, generation: int, revision: int) -> None:
    if record["session_id"] != session_id:
        _fail("session_id does not match the stored record")
    if record["coordinator_id"] != coordinator_id:
        _fail("coordinator_id is stale or does not own this record")
    if record["generation"] != generation:
        _fail(f"generation is stale: expected {record['generation']}, got {generation}")
    if record["revision"] != revision:
        _fail(f"revision is stale: expected {record['revision']}, got {revision}")


def _reset_for_new_generation(record: dict[str, Any], generation: int) -> None:
    record["generation"] = generation
    record["execution_status"] = "running"
    record["cleanup_status"] = "pending"
    record["recovery_status"] = "unknown"
    record["coordinator_phase"] = "active"
    for field in RESET_ON_NEW_GENERATION:
        record.pop(field, None)


def update_record(
    session_id: str,
    coordinator_id: str,
    generation: int,
    expected_revision: int,
    patch: Mapping[str, Any],
    path: os.PathLike[str] | str | None = None,
) -> dict[str, Any]:
    """Apply a guarded patch and return the new record.

    Session/owner/coordinator identity is immutable in an ordinary update.
    A change to observed topology/CLI identity increments generation and resets
    completion/recovery/cleanup eligibility, making old completion evidence
    unable to close the newly observed work.
    """

    _require_nonempty_string(session_id, "session_id")
    _require_nonempty_string(coordinator_id, "coordinator_id")
    generation = _require_integer(generation, "generation")
    expected_revision = _require_integer(expected_revision, "expected_revision")
    if not isinstance(patch, Mapping):
        _fail("patch must be a JSON object")
    unknown = set(patch) - ALLOWED_FIELDS
    if unknown:
        _fail(f"unknown patch field(s): {', '.join(sorted(unknown))}")
    forbidden = set(patch) & CONTROLLED_FIELDS
    if forbidden:
        _fail(
            "ordinary update cannot change controlled field(s): "
            + ", ".join(sorted(forbidden))
            + "; use handoff for owner/coordinator changes"
        )
    state_path = _state_path(path)

    def operation(state: dict[str, Any]) -> dict[str, Any]:
        record = state["records"].get(session_id)
        if record is None:
            _fail(f"unknown session_id: {session_id}")
        _guard(record, session_id, coordinator_id, generation, expected_revision)
        if record["cleanup_policy"] == "retain" and patch.get("cleanup_policy") == "auto_owned":
            authorization = patch.get("cleanup_authorization")
            if not isinstance(authorization, str) or not authorization.strip():
                _fail("cleanup_policy=auto_owned requires explicit new cleanup authorization in the same patch")
        identity_changed = any(field in patch and patch[field] != record.get(field) for field in IDENTITY_FIELDS)
        if identity_changed:
            if record["cleanup_status"] in {"closing", "unknown"}:
                _fail("identity/topology change requires reconciliation of cleanup closing/unknown state first")
            if record["cleanup_policy"] != "auto_owned" and patch.get("cleanup_policy") == "auto_owned":
                _fail("identity/topology change cannot restore auto_owned in the same patch; update after rebind")
            forbidden_after_rebind = set(patch) & IDENTITY_CHANGE_FORBIDDEN_FIELDS
            if forbidden_after_rebind:
                _fail(
                    "identity/topology change requires a separate new-generation update; "
                    "do not submit completion/cleanup/recovery fields in the same patch: "
                    + ", ".join(sorted(forbidden_after_rebind))
                )
        updated = dict(record)
        if identity_changed:
            _reset_for_new_generation(updated, record["generation"] + 1)
        # Apply a new observed identity after the reset so it is retained while
        # stale chat/process evidence not supplied by the patch is removed.
        updated.update(dict(patch))
        updated["revision"] = record["revision"] + 1
        updated["updated_at"] = _utc_now()
        updated = _validate_record(updated)
        state["records"][session_id] = updated
        return updated

    return _mutate(state_path, operation)


def handoff_record(
    session_id: str,
    coordinator_id: str,
    generation: int,
    expected_revision: int,
    new_coordinator_id: str,
    new_task_id: str,
    reason: str,
    path: os.PathLike[str] | str | None = None,
    audit_path: str | None = None,
) -> dict[str, Any]:
    """Explicitly hand a session to a new task/coordinator and advance generation."""

    _require_nonempty_string(session_id, "session_id")
    _require_nonempty_string(coordinator_id, "coordinator_id")
    _require_nonempty_string(new_coordinator_id, "new_coordinator_id")
    _require_nonempty_string(new_task_id, "new_task_id")
    _require_nonempty_string(reason, "reason")
    if audit_path is not None:
        _validate_optional_path(audit_path, "audit_path")
    generation = _require_integer(generation, "generation")
    expected_revision = _require_integer(expected_revision, "expected_revision")
    state_path = _state_path(path)

    def operation(state: dict[str, Any]) -> dict[str, Any]:
        record = state["records"].get(session_id)
        if record is None:
            _fail(f"unknown session_id: {session_id}")
        _guard(record, session_id, coordinator_id, generation, expected_revision)
        cross_task = new_task_id != record["owner_task_id"]
        if cross_task and record["cleanup_status"] in {"closing", "unknown"}:
            _fail("cross-task handoff requires reconciliation of cleanup closing/unknown state first")
        if cross_task and audit_path is None:
            _fail("handoff to a new task requires --audit-path (absolute path)")
        updated = dict(record)
        updated["owner_task_id"] = new_task_id
        updated["coordinator_id"] = new_coordinator_id
        if cross_task:
            _reset_for_new_generation(updated, record["generation"] + 1)
            # A new task must not inherit the old task's container ownership
            # or automatic cleanup authority. Later updates can re-observe
            # topology and obtain fresh cleanup authorization.
            for field in CROSS_TASK_CLEAR_FIELDS:
                updated.pop(field, None)
            updated.pop("cleanup_authorization", None)
            updated["origin"] = "borrowed"
            updated["cleanup_policy"] = "retain"
            updated["cleanup_reason"] = "new cleanup authorization required before auto_owned"
        else:
            # A coordinator handoff within one task is not a new execution.
            # Preserve completion/recovery/cleanup evidence while making an
            # old monitor unable to act until the new coordinator rechecks it.
            updated["generation"] = record["generation"] + 1
            updated["monitor_status"] = "unknown"
        updated["handoff_reason"] = reason
        updated["handoff_at"] = _utc_now()
        if audit_path is not None:
            updated["audit_path"] = audit_path
        updated["revision"] = record["revision"] + 1
        updated["updated_at"] = _utc_now()
        updated = _validate_record(updated)
        state["records"][session_id] = updated
        return updated

    return _mutate(state_path, operation)


def list_records(
    path: os.PathLike[str] | str | None = None, task_id: str | None = None
) -> list[dict[str, Any]]:
    """Return a consistent snapshot, optionally filtered by owner task."""

    state_path = _state_path(path)
    with _file_lock(state_path):
        state = _read_state(state_path)
    records = list(state["records"].values())
    if task_id is not None:
        _require_nonempty_string(task_id, "task_id")
        records = [record for record in records if record["owner_task_id"] == task_id]
    return copy.deepcopy(sorted(records, key=lambda record: record["session_id"]))


def _report_row(record: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(record)
    reasons: list[str] = []
    cleanup_status = record["cleanup_status"]
    phase = record.get("coordinator_phase", "active")
    monitor_status = record.get("monitor_status", "unknown")
    if phase != "settled":
        reasons.append(f"coordinator_phase={phase}")
    if monitor_status in {"running", "failed", "unknown"}:
        reasons.append(f"monitor_status={monitor_status}")
    if cleanup_status in {"pending", "closing", "blocked", "unknown"}:
        reasons.append(f"cleanup_status={cleanup_status}")
    if cleanup_status == "retained" and not str(record.get("retention_reason") or "").strip():
        reasons.append("retained_without_retention_reason")
    row["outstanding"] = bool(reasons)
    row["outstanding_reasons"] = reasons
    # A timestamp is only a requested check point; without a real scheduler
    # handle this remains explicitly unscheduled.
    row["schedule_status"] = "scheduled" if str(record.get("schedule_handle") or "").strip() else "unscheduled"
    return row


def report_records(
    path: os.PathLike[str] | str | None = None, task_id: str | None = None
) -> dict[str, Any]:
    """Build a reconciliation report without taking any terminal action."""

    records = list_records(path=path, task_id=task_id)
    rows = [_report_row(record) for record in records]
    outstanding = [row for row in rows if row["outstanding"]]

    def counts(field: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for row in rows:
            value = row.get(field)
            result[value] = result.get(value, 0) + 1
        return result

    scheduled_count = sum(row["schedule_status"] == "scheduled" for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "assertion_only": True,
        "task_id": task_id,
        "counts": {
            "total": len(rows),
            "outstanding": len(outstanding),
            "settled": len(rows) - len(outstanding),
            "execution_status": counts("execution_status"),
            "cleanup_status": counts("cleanup_status"),
            "recovery_status": counts("recovery_status"),
            "coordinator_phase": counts("coordinator_phase"),
            "schedule": {"scheduled": scheduled_count, "unscheduled": len(rows) - scheduled_count},
        },
        "resources": rows,
        "rows": rows,
        "outstanding": outstanding,
        "outstanding_resources": outstanding,
        "settled": bool(rows) and not outstanding,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Maintain a private, local session registry of host assertions. "
            "Records are not authorization or verified live terminal truth; no input or cleanup is performed."
        ),
        epilog=(
            "Enums: origin=created|adopted|borrowed|unknown; cleanup_policy=auto_owned|retain; "
            "execution_status=running|waiting_user|completed|failed|canceled|paused; "
            "cleanup_status=pending|closing|closed|retained|blocked|unknown; "
            "recovery_status=unknown|ready|degraded|not_applicable; "
            "coordinator_phase=active|finalizing|settled; monitor_status=unknown|running|stopped|failed."
            " owned_container may contain only non-empty-string-or-null tab_id, window_id, basis."
            " cleanup_authorization is an assertion only; retain->auto_owned requires a new value in that patch."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--path", type=Path, default=DEFAULT_STATE_PATH, help=f"state JSON path (default: {DEFAULT_STATE_PATH})")
    commands = parser.add_subparsers(dest="command", required=True)

    register = commands.add_parser("register", help="register a new session record")
    register.add_argument("--path", type=Path, default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    register.add_argument("--record", required=True, type=Path, help="JSON object containing the required record fields")

    update = commands.add_parser("update", help="guarded optimistic record update")
    update.add_argument("--path", type=Path, default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    update.add_argument("--session-id", required=True)
    update.add_argument("--coordinator-id", required=True)
    update.add_argument("--generation", required=True, type=int)
    update.add_argument("--expected-revision", required=True, type=int)
    update.add_argument("--patch", required=True, type=Path, help="JSON object containing fields to change")

    handoff = commands.add_parser("handoff", help="explicitly hand a session to new work")
    handoff.add_argument("--path", type=Path, default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    handoff.add_argument("--session-id", required=True)
    handoff.add_argument("--coordinator-id", required=True, help="current coordinator ID")
    handoff.add_argument("--generation", required=True, type=int)
    handoff.add_argument("--expected-revision", required=True, type=int)
    handoff.add_argument("--new-coordinator-id", required=True)
    handoff.add_argument("--new-task-id", required=True)
    handoff.add_argument("--reason", required=True)
    handoff.add_argument("--audit-path", help="absolute audit path required when changing owner task")

    listing = commands.add_parser("list", help="list assertion records")
    listing.add_argument("--path", type=Path, default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    listing.add_argument("--task-id", help="filter by owner_task_id")

    report = commands.add_parser("report", help="report reconciliation state")
    report.add_argument("--path", type=Path, default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    report.add_argument("--task-id", help="filter by owner_task_id")
    report.add_argument(
        "--require-settled",
        action="store_true",
        help="exit nonzero when any resource requires reconciliation",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        state_path = args.path
        if args.command == "register":
            result: Any = register_record(_read_json_object(args.record, "record"), state_path)
        elif args.command == "update":
            result = update_record(
                args.session_id,
                args.coordinator_id,
                args.generation,
                args.expected_revision,
                _read_json_object(args.patch, "patch"),
                state_path,
            )
        elif args.command == "handoff":
            result = handoff_record(
                args.session_id,
                args.coordinator_id,
                args.generation,
                args.expected_revision,
                args.new_coordinator_id,
                args.new_task_id,
                args.reason,
                state_path,
                args.audit_path,
            )
        elif args.command == "list":
            result = list_records(state_path, args.task_id)
        else:
            result = report_records(state_path, args.task_id)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
            if args.require_settled and (not result["settled"] or (args.task_id is not None and not result["resources"])):
                return 1
            return 0
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (RegistryError, OSError) as exc:
        print(f"error: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised through CLI tests
    raise SystemExit(main())
