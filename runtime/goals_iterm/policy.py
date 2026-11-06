"""Installation policy and short-lived session-registry preconditions.

The policy is read from the skill's fixed local state directory. It is never
selected by invocation JSON, so a request cannot widen its own permissions.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from .operation_store import OperationStoreError, ensure_private_directory, state_dir_path


POLICY_SCHEMA_VERSION = 1
POLICY_FILENAME = "policy.json"

READ_OPERATIONS = frozenset({"list_sessions", "inspect_sessions", "read_screen", "read_history"})
MUTATING_OPERATIONS = frozenset(
    {
        "send_text",
        "send_keys",
        "create_window",
        "create_tab",
        "rename_session",
        "close_session",
        "close_tab",
        "close_window",
        "clean_all_sessions",
    }
)
ALL_OPERATIONS = READ_OPERATIONS | MUTATING_OPERATIONS
CREATE_OPERATIONS = frozenset({"create_window", "create_tab"})
CONTAINER_OPERATIONS = frozenset({"close_tab", "close_window"})


class PolicyError(ValueError):
    """A malformed policy, invalid task context, or denied operation."""

    code = "POLICY_INVALID"


class PolicyDenied(PolicyError):
    """A valid request is outside the installation's configured authority."""

    def __init__(self, message: str, *, code: str = "OPERATION_NOT_ALLOWED") -> None:
        super().__init__(message)
        self.code = code


class TaskContextError(PolicyError):
    """The request's ownership assertion is absent, stale, or malformed."""

    code = "TASK_CONTEXT_STALE"


class TaskContextRequiredError(TaskContextError):
    """A managed Session was targeted without an ownership precondition."""

    code = "TASK_CONTEXT_REQUIRED"


@dataclass(frozen=True)
class Policy:
    """Validated policy snapshot used for one finite operation."""

    read_only: bool
    session_ids: frozenset[str] | None
    configured: bool
    path: Path

    @property
    def has_session_allowlist(self) -> bool:
        return self.session_ids is not None


def policy_path(state_dir: os.PathLike[str] | str | None = None) -> Path:
    try:
        return state_dir_path(state_dir) / POLICY_FILENAME
    except OperationStoreError as exc:
        raise PolicyError(str(exc)) from exc


def load_policy(state_dir: os.PathLike[str] | str | None = None) -> Policy:
    """Load trusted local policy; absent policy is explicitly read-only.

    A present but malformed, symlinked, non-regular, or group/world-readable
    policy fails closed instead of being treated as an unrestricted default.
    """

    path = policy_path(state_dir)
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return Policy(read_only=True, session_ids=None, configured=False, path=path)
    except OSError as exc:
        raise PolicyError(f"cannot inspect policy file {path}: {exc}") from exc
    if stat.S_ISLNK(mode):
        raise PolicyError(f"policy file must not be a symlink: {path}")
    if not stat.S_ISREG(mode):
        raise PolicyError(f"policy path must be a regular file: {path}")
    if mode & 0o077:
        raise PolicyError(f"policy file must be private (owner-only mode): {path}")
    try:
        parent_mode = os.lstat(path.parent).st_mode
    except OSError as exc:
        raise PolicyError(f"cannot inspect policy directory {path.parent}: {exc}") from exc
    if stat.S_ISLNK(parent_mode) or not stat.S_ISDIR(parent_mode) or parent_mode & 0o077:
        raise PolicyError(f"policy directory must be private and must not be a symlink: {path.parent}")
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise PolicyError(f"cannot read policy file {path}: {exc}") from exc
    try:
        opened_mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(opened_mode) or opened_mode & 0o077:
            raise PolicyError(f"policy file must be a private regular file: {path}")
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = -1
            try:
                value = json.load(stream, object_pairs_hook=_reject_duplicate_keys)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise PolicyError(f"policy file contains invalid JSON: {path}") from exc
    finally:
        if fd != -1:
            os.close(fd)
    return _validate_policy(value, path, configured=True)


def save_policy(
    policy: Mapping[str, Any] | None = None,
    *,
    read_only: bool | None = None,
    session_ids: Sequence[str] | None = None,
    state_dir: os.PathLike[str] | str | None = None,
) -> Policy:
    """Atomically write an explicit local policy with owner-only permissions."""

    path = policy_path(state_dir)
    if policy is not None:
        if read_only is not None or session_ids is not None:
            raise PolicyError("pass either a policy object or read_only/session_ids arguments")
        if not isinstance(policy, Mapping):
            raise PolicyError("policy must be an object")
        payload = dict(policy)
    else:
        if type(read_only) is not bool:
            raise PolicyError("read_only must be an explicit boolean")
        if session_ids is not None and (isinstance(session_ids, (str, bytes)) or not isinstance(session_ids, Sequence)):
            raise PolicyError("session_ids must be an array of exact IDs or null")
        payload = {
            "schema_version": POLICY_SCHEMA_VERSION,
            "read_only": read_only,
            "session_ids": None if session_ids is None else list(session_ids),
        }
    normalized = _validate_policy(payload, path, configured=True)
    parent = path.parent
    try:
        ensure_private_directory(parent)
    except Exception as exc:
        raise PolicyError(f"cannot secure policy directory {parent}: {exc}") from exc
    try:
        existing_mode = os.lstat(path).st_mode
    except FileNotFoundError:
        existing_mode = None
    except OSError as exc:
        raise PolicyError(f"cannot inspect policy file {path}: {exc}") from exc
    if existing_mode is not None and (stat.S_ISLNK(existing_mode) or not stat.S_ISREG(existing_mode)):
        raise PolicyError(f"policy path must be a regular, non-symlink file: {path}")

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    fd = -1
    temporary: str | None = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".policy-", dir=parent)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(encoded)
            stream.write(b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        if fd != -1:
            os.close(fd)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        raise PolicyError(f"cannot persist policy file {path}: {exc}") from exc
    return normalized


def authorize(
    operation: str,
    arguments: Mapping[str, Any],
    request: Mapping[str, Any] | None = None,
    *,
    policy: Policy | None = None,
    target_session_ids: Iterable[str] | None = None,
) -> None:
    """Check read-only, allowlist, and explicit global-cleanup scope.

    For close_tab and close_window, the caller must pass all current member
    Session IDs from its fresh topology snapshot. This prevents container
    selectors from bypassing a session allowlist.
    """

    if operation not in ALL_OPERATIONS:
        raise PolicyDenied(f"unsupported operation: {operation!r}", code="POLICY_INVALID")
    if not isinstance(arguments, Mapping):
        raise PolicyDenied("operation arguments must be an object")
    active_policy = load_policy() if policy is None else policy
    request_data = {} if request is None else request
    if not isinstance(request_data, Mapping):
        raise PolicyDenied("request metadata must be an object")

    dry_run = arguments.get("dry_run", False)
    if "dry_run" in arguments and type(dry_run) is not bool:
        raise PolicyDenied("dry_run must be a boolean", code="POLICY_INVALID")
    read_only_preview = dry_run and operation in {
        "close_session",
        "close_tab",
        "close_window",
        "clean_all_sessions",
    }
    if operation in MUTATING_OPERATIONS and active_policy.read_only and not read_only_preview:
        raise PolicyDenied("installation policy is read-only", code="READ_ONLY")

    if operation == "clean_all_sessions":
        if request_data.get("authorization_scope") != "all_sessions":
            raise PolicyDenied(
                "clean_all_sessions requires authorization_scope='all_sessions'", code="CLEAN_ALL_SCOPE_REQUIRED"
            )
        if active_policy.session_ids is not None and target_session_ids is not None:
            resolved = _resolve_target_ids(arguments, target_session_ids)
            denied = sorted(session_id for session_id in resolved if session_id not in active_policy.session_ids)
            if denied:
                raise PolicyDenied(
                    f"clean_all_sessions target Session ID(s) are outside the installation allowlist: {', '.join(denied)}",
                    code="SESSION_NOT_ALLOWED",
                )
        return

    if active_policy.session_ids is None:
        return

    if operation in CREATE_OPERATIONS:
        raise PolicyDenied(
            f"{operation} is prohibited while a session allowlist is active", code="SESSION_NOT_ALLOWED"
        )

    if operation in {"list_sessions", "inspect_sessions"}:
        # The caller must filter the returned rows with filter_session_rows.
        return

    resolved = _resolve_target_ids(arguments, target_session_ids)
    if operation in CONTAINER_OPERATIONS and target_session_ids is None:
        # Initial authorization can run before a fresh topology is available.
        # The caller must repeat authorization with every current member ID.
        return
    if not resolved:
        if target_session_ids is None and operation == "close_session":
            # Nickname selectors are resolved against a fresh catalogue by
            # the service. Authorization must be repeated with that exact ID.
            return
        raise PolicyDenied(
            f"{operation} requires an exact Session ID under a session allowlist", code="SESSION_NOT_ALLOWED"
        )
    denied = sorted(session_id for session_id in resolved if session_id not in active_policy.session_ids)
    if denied:
        raise PolicyDenied(
            f"target Session ID(s) are outside the installation allowlist: {', '.join(denied)}",
            code="SESSION_NOT_ALLOWED",
        )


def filter_session_rows(rows: Iterable[Mapping[str, Any]], policy: Policy) -> list[dict[str, Any]]:
    """Filter list/inspect result rows when an installation allowlist is active."""

    if policy.session_ids is None:
        return [dict(row) for row in rows]
    return [
        dict(row)
        for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("session_id"), str) and row["session_id"] in policy.session_ids
    ]


def check_task_context(
    task_context: Mapping[str, Any] | None,
    session_ids: Iterable[str] | None,
    *,
    registry_path: os.PathLike[str] | str | None = None,
) -> None:
    """Validate request ownership claims against a short registry snapshot.

    The registry uses atomic replacement, so this reads and validates one
    opened snapshot without waiting on its advisory lock. Callers must check at
    the operation boundary and again before a write; no registry lock is held
    during terminal/API work.
    """

    targets: list[str] | None
    if session_ids is None:
        targets = None
    else:
        targets = list(session_ids)
        if any(not isinstance(value, str) or not value for value in targets) or len(targets) != len(set(targets)):
            raise TaskContextError("target Session IDs must be unique non-empty strings")

    if task_context is None:
        if not targets:
            return
        try:
            records = _read_registry_records(registry_path)
        except Exception as exc:
            raise TaskContextError(f"cannot read session registry snapshot: {exc}") from exc
        registered = {record.get("session_id") for record in records}
        missing_context = sorted(set(targets) & registered)
        if missing_context:
            raise TaskContextRequiredError(
                "task_context is required for registered Session(s): " + ", ".join(missing_context)
            )
        return
    if not isinstance(task_context, Mapping):
        raise TaskContextError("task_context must be an object")
    allowed = {"task_id", "coordinator_id", "generation", "expected_revision", "sessions"}
    unknown = set(task_context) - allowed
    if unknown:
        raise TaskContextError(f"unknown task_context field(s): {', '.join(sorted(str(item) for item in unknown))}")
    task_id = _context_string(task_context.get("task_id"), "task_context.task_id")
    coordinator_id = _context_string(task_context.get("coordinator_id"), "task_context.coordinator_id")
    if "generation" in task_context and task_context["generation"] is None:
        raise TaskContextError("task_context.generation cannot be null")
    if "expected_revision" in task_context and task_context["expected_revision"] is None:
        raise TaskContextError("task_context.expected_revision cannot be null")
    common_generation = _context_positive_int(task_context.get("generation"), "task_context.generation")
    common_revision = _context_positive_int(task_context.get("expected_revision"), "task_context.expected_revision")

    overrides_value = task_context.get("sessions", {})
    if not isinstance(overrides_value, Mapping):
        raise TaskContextError("task_context.sessions must be an object")
    overrides: dict[str, Mapping[str, Any]] = {}
    for session_id, override in overrides_value.items():
        _context_string(session_id, "task_context.sessions key")
        if not isinstance(override, Mapping) or set(override) - {"generation", "expected_revision"}:
            raise TaskContextError(f"task_context.sessions[{session_id!r}] has invalid fields")
        if any(field in override and override[field] is None for field in ("generation", "expected_revision")):
            raise TaskContextError(f"task_context.sessions[{session_id!r}] values cannot be null")
        _context_positive_int(override.get("generation"), f"generation for {session_id}")
        _context_positive_int(override.get("expected_revision"), f"expected_revision for {session_id}")
        overrides[session_id] = override

    if session_ids is None:
        if common_generation is None:
            raise TaskContextError("task_context.generation is required")
        return
    if not targets:
        if common_generation is None:
            raise TaskContextError("task_context.generation is required")
        return
    if set(overrides) - set(targets):
        raise TaskContextError("task_context.sessions contains a Session outside this operation's target set")

    try:
        records = _read_registry_records(registry_path)
    except Exception as exc:
        if isinstance(exc, TaskContextError):
            raise
        raise TaskContextError(f"cannot read session registry snapshot: {exc}") from exc
    by_id = {record.get("session_id"): record for record in records}
    registered_targets = [session_id for session_id in targets if session_id in by_id]
    if not registered_targets:
        # Direct/manual Sessions have no ownership assertion to compare. A
        # supplied context is schema-checked above but is not required here.
        if common_generation is None:
            raise TaskContextError("task_context.generation is required")
        return
    for session_id in registered_targets:
        override = overrides.get(session_id, {})
        generation = _context_positive_int(override.get("generation", common_generation), f"generation for {session_id}")
        revision = _context_positive_int(
            override.get("expected_revision", common_revision), f"expected_revision for {session_id}"
        )
        if generation is None or revision is None:
            raise TaskContextError(
                f"task_context must provide generation and expected_revision for registered Session {session_id}"
            )
        record = by_id[session_id]
        if record.get("owner_task_id") != task_id:
            raise TaskContextError(f"Session {session_id} is registered to a different task")
        if record.get("coordinator_id") != coordinator_id:
            raise TaskContextError(f"Session {session_id} is owned by a different coordinator")
        if record.get("generation") != generation:
            raise TaskContextError(f"Session {session_id} generation is stale")
        if record.get("revision") != revision:
            raise TaskContextError(f"Session {session_id} revision is stale")


def _read_registry_records(registry_path: os.PathLike[str] | str | None) -> list[dict[str, Any]]:
    module = _session_registry_module()
    path = (
        Path(registry_path).expanduser().absolute()
        if registry_path is not None
        else state_dir_path() / "session-registry.json"
    )
    # The registry writes with atomic replacement. Reading a single opened
    # snapshot through the same validator avoids blocking indefinitely on its
    # advisory lock; no registry lock is held while any terminal call runs.
    state = module._read_state(path)
    return sorted(state["records"].values(), key=lambda record: record["session_id"])


def _session_registry_module() -> Any:
    module_name = "_goals_iterm_session_registry_for_policy"
    if module_name in sys.modules:
        return sys.modules[module_name]
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "session_registry.py"
    if not module_path.is_file():
        raise TaskContextError(f"session registry helper was not found: {module_path}")
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise TaskContextError("cannot load session registry helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _validate_policy(value: Any, path: Path, *, configured: bool) -> Policy:
    if not isinstance(value, dict):
        raise PolicyError("policy must be a JSON object")
    if set(value) != {"schema_version", "read_only", "session_ids"}:
        raise PolicyError("policy must contain exactly schema_version, read_only, and session_ids")
    if type(value["schema_version"]) is not int or value["schema_version"] != POLICY_SCHEMA_VERSION:
        raise PolicyError(f"unsupported policy schema_version: {value['schema_version']!r}")
    if type(value["read_only"]) is not bool:
        raise PolicyError("policy.read_only must be a boolean")
    session_ids_value = value["session_ids"]
    if session_ids_value is None:
        normalized_ids = None
    elif isinstance(session_ids_value, list):
        normalized: list[str] = []
        for session_id in session_ids_value:
            normalized.append(_required_string(session_id, "policy.session_ids entry"))
        if len(normalized) != len(set(normalized)):
            raise PolicyError("policy.session_ids must not contain duplicates")
        normalized_ids = frozenset(normalized)
    else:
        raise PolicyError("policy.session_ids must be an array of exact IDs or null")
    return Policy(read_only=value["read_only"], session_ids=normalized_ids, configured=configured, path=path)


def _resolve_target_ids(arguments: Mapping[str, Any], target_session_ids: Iterable[str] | None) -> list[str]:
    if target_session_ids is None:
        candidate = arguments.get("session_id")
        if isinstance(candidate, str) and candidate:
            return [candidate]
        candidates = arguments.get("session_ids")
    else:
        candidates = target_session_ids
    if candidates is None or isinstance(candidates, (str, bytes)):
        return []
    try:
        resolved = list(candidates)
    except TypeError:
        return []
    if any(not isinstance(value, str) or not value for value in resolved):
        return []
    return resolved


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1024 or any(ord(char) < 0x20 for char in value):
        raise PolicyError(f"{field} must be a non-empty string without control characters")
    return value


def _optional_positive_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PolicyError(f"{field} must be an integer >= 1")
    return value


def _context_string(value: Any, field: str) -> str:
    try:
        return _required_string(value, field)
    except PolicyError as exc:
        raise TaskContextError(str(exc)) from exc


def _context_positive_int(value: Any, field: str) -> int | None:
    try:
        return _optional_positive_int(value, field)
    except PolicyError as exc:
        raise TaskContextError(str(exc)) from exc


__all__ = [
    "ALL_OPERATIONS",
    "CREATE_OPERATIONS",
    "CONTAINER_OPERATIONS",
    "MUTATING_OPERATIONS",
    "POLICY_FILENAME",
    "POLICY_SCHEMA_VERSION",
    "Policy",
    "PolicyDenied",
    "PolicyError",
    "READ_OPERATIONS",
    "TaskContextError",
    "TaskContextRequiredError",
    "authorize",
    "check_task_context",
    "filter_session_rows",
    "load_policy",
    "policy_path",
    "save_policy",
]
