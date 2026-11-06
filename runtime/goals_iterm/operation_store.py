"""Durable, local request reservations for standalone iTerm operations.

The store is a small write-ahead journal, not an exactly-once transport. A
reservation is flushed before a caller performs a side effect. If the process
dies before the result is flushed, a repeated request ID is reported as
unknown and must not be replayed automatically.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import datetime as _datetime
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping


SCHEMA_VERSION = 1
DEFAULT_STATE_DIR = Path(
    os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
) / "goals-iterm-skill"
DEFAULT_LOCK_TIMEOUT = 5.0
MAX_RESULT_BYTES = 1_048_576
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class OperationStoreError(RuntimeError):
    """Base class for request journal and locking errors."""

    code = "OPERATION_STORE_ERROR"


class OperationLockTimeout(OperationStoreError):
    """The cross-process operation lock was not acquired before its deadline."""

    code = "OPERATION_LOCK_TIMEOUT"


class OperationRecordError(OperationStoreError):
    """A journal record is unsafe, corrupt, or inconsistent."""

    code = "OPERATION_RECORD_INVALID"


class RequestConflictError(OperationStoreError):
    """A request ID was reused with a different operation or fingerprint."""

    code = "REQUEST_ID_CONFLICT"


class OperationPersistenceError(OperationStoreError):
    """A result could not be durably recorded after execution may have begun."""

    outcome_unknown = True
    code = "OPERATION_PERSISTENCE_FAILED"


@dataclass(frozen=True)
class Reservation:
    """Result of reserving a request ID.

    ``disposition`` is ``new`` for the sole caller allowed to execute,
    ``completed`` when a durable result is available, or ``unknown`` when a
    prior invocation reserved the ID but did not persist a final result.
    """

    request_id: str
    operation: str
    fingerprint: str
    disposition: str
    result: Any = None

    @property
    def is_new(self) -> bool:
        return self.disposition == "new"


def state_dir_path(state_dir: os.PathLike[str] | str | None = None) -> Path:
    """Return the absolute skill state directory, honoring XDG_STATE_HOME."""

    chosen = DEFAULT_STATE_DIR if state_dir is None else Path(state_dir).expanduser()
    if not chosen.is_absolute():
        raise OperationStoreError("state_dir must be an absolute path")
    return chosen


def fingerprint_arguments(value: Any) -> str:
    """Hash JSON-compatible request metadata without retaining its contents."""

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise OperationStoreError("request metadata must be finite JSON data") from exc
    return hashlib.sha256(encoded).hexdigest()


def _utc_now() -> str:
    return _datetime.datetime.now(_datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise OperationStoreError("journal data must be finite JSON data") from exc


def _reject_symlink(path: Path, label: str) -> None:
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(mode):
        raise OperationRecordError(f"{label} path must not be a symlink: {path}")


def _fsync_directory(path: Path) -> None:
    fd = -1
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        os.fsync(fd)
    except OSError as exc:
        raise OperationStoreError(f"cannot fsync directory {path}: {exc}") from exc
    finally:
        if fd != -1:
            os.close(fd)


def ensure_private_directory(path: os.PathLike[str] | str) -> None:
    """Create a private leaf directory and reject a symlink at that leaf."""

    path = Path(path)

    missing: list[Path] = []
    current = path
    while True:
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            missing.append(current)
            if current.parent == current:
                break
            current = current.parent
            continue
        if stat.S_ISLNK(mode):
            if not current.is_dir():
                raise OperationRecordError(f"state parent symlink does not resolve to a directory: {current}")
        elif not stat.S_ISDIR(mode):
            raise OperationRecordError(f"state parent is not a directory: {current}")
        break
    for directory in reversed(missing):
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            mode = os.lstat(directory).st_mode
            if stat.S_ISLNK(mode):
                if not directory.is_dir():
                    raise OperationRecordError(f"state parent symlink does not resolve to a directory: {directory}")
            elif not stat.S_ISDIR(mode):
                raise OperationRecordError(f"state parent is not a directory: {directory}")
        except OSError as exc:
            raise OperationStoreError(f"cannot create state directory {directory}: {exc}") from exc
        _fsync_directory(directory.parent)
    _reject_symlink(path, "state directory")
    try:
        mode = os.lstat(path).st_mode
        if not stat.S_ISDIR(mode):
            raise OperationRecordError(f"state path is not a directory: {path}")
        os.chmod(path, 0o700, follow_symlinks=False)
    except OSError as exc:
        raise OperationStoreError(f"cannot secure state directory {path}: {exc}") from exc


@contextmanager
def _file_lock(path: Path, timeout: float) -> Iterator[None]:
    """Acquire a private advisory lock with a finite, monotonic deadline."""

    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout < 0:
        raise OperationStoreError("lock timeout must be a non-negative number")
    ensure_private_directory(path.parent)
    _reject_symlink(path, "lock")
    flags = os.O_RDWR | os.O_CREAT | os.O_NONBLOCK
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise OperationRecordError(f"lock path must not be a symlink: {path}") from exc
        raise OperationStoreError(f"cannot open lock file {path}: {exc}") from exc
    try:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            raise OperationRecordError(f"lock path must be a regular file: {path}")
        if mode & 0o077:
            raise OperationRecordError(f"lock file must be private (owner-only mode): {path}")
        os.fchmod(fd, 0o600)
        deadline = time.monotonic() + float(timeout)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise OperationLockTimeout(f"timed out acquiring operation lock: {path}")
                time.sleep(min(0.05, remaining))
        try:
            _reject_symlink(path, "lock")
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _validate_record(record: Any, expected_request_id: str) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise OperationRecordError("operation record root must be a JSON object")
    expected_fields = {
        "schema_version",
        "request_id",
        "operation",
        "fingerprint",
        "task_context_fingerprint",
        "expected_observation_fingerprint",
        "state",
        "created_at",
        "updated_at",
        "result",
    }
    if set(record) != expected_fields:
        raise OperationRecordError("operation record has missing or unknown fields")
    if type(record["schema_version"]) is not int or record["schema_version"] != SCHEMA_VERSION:
        raise OperationRecordError("operation record schema version is unsupported")
    if record["request_id"] != expected_request_id:
        raise OperationRecordError("operation record request ID does not match its file name")
    if not isinstance(record["operation"], str) or not record["operation"].strip():
        raise OperationRecordError("operation record has an invalid operation")
    if not isinstance(record["fingerprint"], str) or not _SHA256_RE.fullmatch(record["fingerprint"]):
        raise OperationRecordError("operation record has an invalid fingerprint")
    for field in ("task_context_fingerprint", "expected_observation_fingerprint"):
        value = record[field]
        if value is not None and (not isinstance(value, str) or not _SHA256_RE.fullmatch(value)):
            raise OperationRecordError(f"operation record has an invalid {field}")
    if not isinstance(record["state"], str) or record["state"] not in {"reserved", "completed"}:
        raise OperationRecordError("operation record has an invalid state")
    if not isinstance(record["created_at"], str) or not isinstance(record["updated_at"], str):
        raise OperationRecordError("operation record timestamps are invalid")
    for field in ("created_at", "updated_at"):
        try:
            timestamp = _datetime.datetime.fromisoformat(record[field].replace("Z", "+00:00"))
        except ValueError as exc:
            raise OperationRecordError(f"operation record {field} is invalid") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() != _datetime.timedelta(0):
            raise OperationRecordError(f"operation record {field} must be UTC")
    if record["state"] == "reserved" and record["result"] is not None:
        raise OperationRecordError("reserved operation record cannot contain a result")
    return record


class OperationStore:
    """File-backed operation journal and cross-process operation lock.

    ``state_dir`` is the skill state root. Journal records are stored under
    ``state_dir/operations``. The operation lock is separate from both the
    journal lock and the session-registry lock.
    """

    def __init__(
        self,
        state_dir: os.PathLike[str] | str | None = None,
        *,
        lock_timeout: float = DEFAULT_LOCK_TIMEOUT,
    ) -> None:
        self.state_dir = state_dir_path(state_dir)
        self.operations_dir = self.state_dir / "operations"
        self._operation_lock_path = self.state_dir / "operation.lock"
        self._journal_lock_path = self.state_dir / "operation-store.lock"
        if isinstance(lock_timeout, bool) or not isinstance(lock_timeout, (int, float)) or lock_timeout < 0:
            raise OperationStoreError("lock_timeout must be a non-negative number")
        self.lock_timeout = float(lock_timeout)

    @contextmanager
    def operation_lock(self, timeout: float | None = None) -> Iterator[None]:
        """Serialize complete terminal operations across local processes."""

        with _file_lock(self._operation_lock_path, self.lock_timeout if timeout is None else timeout):
            yield

    def reserve(
        self,
        request_id: str,
        fingerprint: str,
        operation: str,
        *,
        task_context: Any = None,
        expected_observation: Any = None,
    ) -> Reservation:
        """Durably reserve an ID before execution, or return its known state.

        Only SHA-256 digests of request arguments, task context, and expected
        observation are written. The caller should include all replay-relevant
        request fields in ``fingerprint`` via :func:`fingerprint_arguments`.
        """

        if not isinstance(request_id, str) or not _REQUEST_ID_RE.fullmatch(request_id):
            raise OperationStoreError("request_id must be 1-128 safe ASCII characters")
        if not isinstance(fingerprint, str) or not _SHA256_RE.fullmatch(fingerprint):
            raise OperationStoreError("fingerprint must be a lowercase SHA-256 hex digest")
        if not isinstance(operation, str) or not operation.strip() or len(operation) > 128:
            raise OperationStoreError("operation must be a non-empty string of at most 128 characters")
        context_fingerprint = None if task_context is None else fingerprint_arguments(task_context)
        observation_fingerprint = None if expected_observation is None else fingerprint_arguments(expected_observation)
        record_path = self._record_path(request_id)

        with _file_lock(self._journal_lock_path, self.lock_timeout):
            existing = self._read_record(record_path, request_id)
            if existing is not None:
                if (
                    existing["operation"] != operation
                    or existing["fingerprint"] != fingerprint
                    or existing["task_context_fingerprint"] != context_fingerprint
                    or existing["expected_observation_fingerprint"] != observation_fingerprint
                ):
                    raise RequestConflictError("request_id was already used with different request metadata")
                if existing["state"] == "completed":
                    return Reservation(request_id, operation, fingerprint, "completed", existing["result"])
                return Reservation(request_id, operation, fingerprint, "unknown")

            now = _utc_now()
            record = {
                "schema_version": SCHEMA_VERSION,
                "request_id": request_id,
                "operation": operation,
                "fingerprint": fingerprint,
                "task_context_fingerprint": context_fingerprint,
                "expected_observation_fingerprint": observation_fingerprint,
                "state": "reserved",
                "created_at": now,
                "updated_at": now,
                "result": None,
            }
            try:
                self._write_record(record_path, record)
            except Exception as exc:
                raise OperationStoreError(f"request reservation was not durably recorded: {exc}") from exc
        return Reservation(request_id, operation, fingerprint, "new")

    def finish(self, request_id: str, result: Any) -> None:
        """Persist the completed outcome; failures must be surfaced as unknown."""

        # Validate/serialize the result before opening or changing the record.
        try:
            encoded_result = _canonical_json(result)
            if len(encoded_result) > MAX_RESULT_BYTES:
                raise OperationStoreError(f"result exceeds the {MAX_RESULT_BYTES}-byte journal limit")
        except Exception as exc:
            raise OperationPersistenceError(
                "operation may have completed, but its result could not be represented in the journal; outcome is unknown"
            ) from exc
        record_path = self._record_path(request_id)
        with _file_lock(self._journal_lock_path, self.lock_timeout):
            record = self._read_record(record_path, request_id)
            if record is None:
                raise OperationStoreError("cannot finish an operation without a durable reservation")
            if record["state"] == "completed":
                if record["result"] != result:
                    raise RequestConflictError("completed request_id cannot be assigned a different result")
                return
            record["state"] = "completed"
            record["updated_at"] = _utc_now()
            record["result"] = result
            try:
                self._write_record(record_path, record)
            except Exception as exc:
                raise OperationPersistenceError(
                    "operation may have completed, but its result was not confirmed durable; outcome is unknown"
                ) from exc

    def status(self, request_id: str) -> dict[str, Any] | None:
        """Return a redacted status view, or ``None`` for an unused request ID."""

        if not isinstance(request_id, str) or not _REQUEST_ID_RE.fullmatch(request_id):
            raise OperationStoreError("request_id must be 1-128 safe ASCII characters")
        with _file_lock(self._journal_lock_path, self.lock_timeout):
            record = self._read_record(self._record_path(request_id), request_id)
        if record is None:
            return None
        return {
            "request_id": record["request_id"],
            "operation": record["operation"],
            "status": "completed" if record["state"] == "completed" else "unknown",
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
            "result": record["result"] if record["state"] == "completed" else None,
        }

    def _record_path(self, request_id: str) -> Path:
        digest = hashlib.sha256(request_id.encode("ascii")).hexdigest()
        return self.operations_dir / f"{digest}.json"

    def _read_record(self, path: Path, request_id: str) -> dict[str, Any] | None:
        ensure_private_directory(self.operations_dir)
        _reject_symlink(path, "operation record")
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return None
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise OperationRecordError(f"operation record path must not be a symlink: {path}") from exc
            raise OperationRecordError(f"cannot read operation record {path}: {exc}") from exc
        try:
            mode = os.fstat(fd).st_mode
            if not stat.S_ISREG(mode):
                raise OperationRecordError(f"operation record must be a regular file: {path}")
            if mode & 0o077:
                raise OperationRecordError(f"operation record must be private (owner-only mode): {path}")
            with os.fdopen(fd, "r", encoding="utf-8") as stream:
                fd = -1
                try:
                    value = json.load(
                        stream,
                        object_pairs_hook=_reject_duplicate_keys,
                        parse_constant=_reject_json_constant,
                    )
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise OperationRecordError(f"operation record is corrupt JSON: {path}") from exc
        finally:
            if fd != -1:
                os.close(fd)
        return _validate_record(value, request_id)

    def _write_record(self, path: Path, record: Mapping[str, Any]) -> None:
        ensure_private_directory(self.operations_dir)
        _reject_symlink(path, "operation record")
        payload = _canonical_json(dict(record))
        fd = -1
        temporary: str | None = None
        try:
            fd, temporary = tempfile.mkstemp(prefix=".operation-", dir=self.operations_dir)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                fd = -1
                stream.write(payload)
                stream.write(b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
            directory_fd = os.open(self.operations_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            if fd != -1:
                os.close(fd)
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
            raise


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise OperationRecordError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise OperationRecordError(f"non-finite JSON value is not permitted: {value}")


__all__ = [
    "DEFAULT_STATE_DIR",
    "OperationLockTimeout",
    "OperationPersistenceError",
    "OperationRecordError",
    "OperationStore",
    "OperationStoreError",
    "Reservation",
    "RequestConflictError",
    "fingerprint_arguments",
    "ensure_private_directory",
    "state_dir_path",
    "MAX_RESULT_BYTES",
]
