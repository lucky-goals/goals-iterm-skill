from __future__ import annotations

import multiprocessing
from pathlib import Path
import time

import pytest

from goals_iterm.operation_store import (
    OperationLockTimeout,
    OperationPersistenceError,
    OperationRecordError,
    OperationStore,
    RequestConflictError,
    fingerprint_arguments,
)


def _hold_lock(state_dir: str, ready: multiprocessing.synchronize.Event, release: multiprocessing.synchronize.Event) -> None:
    store = OperationStore(state_dir, lock_timeout=1)
    with store.operation_lock():
        ready.set()
        release.wait(3)


def test_reservation_is_durable_and_does_not_store_raw_arguments(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    args = {"session_id": "S1", "text": "private prompt value"}
    fingerprint = fingerprint_arguments(args)

    reserved = store.reserve("req-1", fingerprint, "send_text")

    assert reserved.disposition == "new"
    assert store.status("req-1")["status"] == "unknown"
    record_files = list((tmp_path / "operations").glob("*.json"))
    assert len(record_files) == 1
    stored_text = record_files[0].read_text(encoding="utf-8")
    assert "private prompt value" not in stored_text
    assert fingerprint in stored_text


def test_duplicate_completed_returns_result_and_reserved_is_unknown(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    fingerprint = fingerprint_arguments({"session_id": "S1", "text": "hello"})

    assert store.reserve("pending", fingerprint, "send_text").disposition == "new"
    assert store.reserve("pending", fingerprint, "send_text").disposition == "unknown"

    done_fingerprint = fingerprint_arguments({"session_id": "S2", "text": "hello"})
    assert store.reserve("done", done_fingerprint, "send_text").disposition == "new"
    result = {"api_acknowledged": True, "session_id": "S2"}
    store.finish("done", result)

    repeated = store.reserve("done", done_fingerprint, "send_text")
    assert repeated.disposition == "completed"
    assert repeated.result == result
    assert store.status("done")["result"] == result


def test_same_request_id_with_changed_operation_or_precondition_conflicts(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    fingerprint = fingerprint_arguments({"session_id": "S1"})
    context = {"task_id": "T1", "coordinator_id": "C1", "generation": 1, "expected_revision": 1}
    observation = {"session_id": "S1", "tab_id": "TAB1"}
    store.reserve("same", fingerprint, "send_text", task_context=context, expected_observation=observation)

    with pytest.raises(RequestConflictError):
        store.reserve("same", fingerprint, "send_keys", task_context=context, expected_observation=observation)
    with pytest.raises(RequestConflictError):
        store.reserve(
            "same",
            fingerprint,
            "send_text",
            task_context={**context, "expected_revision": 2},
            expected_observation=observation,
        )


def test_result_persistence_failure_exposes_unknown_outcome(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = OperationStore(tmp_path)
    fingerprint = fingerprint_arguments({"session_id": "S1", "text": "hello"})
    store.reserve("uncertain", fingerprint, "send_text")

    def fail_write(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(store, "_write_record", fail_write)
    with pytest.raises(OperationPersistenceError) as raised:
        store.finish("uncertain", {"api_acknowledged": True})

    assert raised.value.outcome_unknown is True
    assert raised.value.code == "OPERATION_PERSISTENCE_FAILED"
    assert store.status("uncertain")["status"] == "unknown"


def test_operation_lock_has_a_finite_timeout_across_processes(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    child = context.Process(target=_hold_lock, args=(str(tmp_path), ready, release))
    child.start()
    try:
        assert ready.wait(3), "child did not acquire the operation lock"
        store = OperationStore(tmp_path, lock_timeout=0.05)
        started = time.monotonic()
        with pytest.raises(OperationLockTimeout):
            with store.operation_lock():
                pytest.fail("lock unexpectedly acquired")
        assert time.monotonic() - started < 1.0
    finally:
        release.set()
        child.join(3)
        if child.is_alive():
            child.terminate()
            child.join()
    assert child.exitcode == 0


def test_malformed_journal_json_is_not_treated_as_an_unused_id(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    fingerprint = fingerprint_arguments({"session_id": "S1"})
    record_path = store._record_path("broken")
    record_path.parent.mkdir(parents=True, mode=0o700)
    record_path.write_text('{"request_id":"broken","request_id":"other"}', encoding="utf-8")
    record_path.chmod(0o600)

    with pytest.raises(OperationRecordError):
        store.reserve("broken", fingerprint, "send_text")
