from __future__ import annotations

from pathlib import Path

import pytest

from goals_iterm.policy import (
    PolicyDenied,
    PolicyError,
    TaskContextError,
    TaskContextRequiredError,
    authorize,
    check_task_context,
    filter_session_rows,
    load_policy,
    save_policy,
)
from scripts.session_registry import register_record


def _record(session_id: str, *, task_id: str = "task-1", coordinator_id: str = "C1") -> dict[str, str]:
    return {
        "session_id": session_id,
        "owner_task_id": task_id,
        "coordinator_id": coordinator_id,
        "origin": "created",
        "cleanup_policy": "auto_owned",
        "audit_path": "/tmp/task-audit.md",
    }


def test_missing_policy_is_read_only_and_explicit_policy_is_loaded(tmp_path: Path) -> None:
    missing = load_policy(tmp_path)
    assert missing.configured is False
    assert missing.read_only is True
    assert missing.session_ids is None

    saved = save_policy(
        {"schema_version": 1, "read_only": False, "session_ids": ["S1"]},
        state_dir=tmp_path,
    )
    loaded = load_policy(tmp_path)
    assert saved.configured is True
    assert loaded.configured is True
    assert loaded.read_only is False
    assert loaded.session_ids == frozenset({"S1"})
    assert (tmp_path / "policy.json").stat().st_mode & 0o777 == 0o600


def test_policy_save_rejects_invalid_types_and_load_rejects_duplicate_fields(tmp_path: Path) -> None:
    with pytest.raises(PolicyError):
        save_policy({"schema_version": 1, "read_only": "false", "session_ids": None}, state_dir=tmp_path)

    path = tmp_path / "policy.json"
    path.write_text('{"schema_version":1,"read_only":false,"read_only":true,"session_ids":null}', encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(PolicyError):
        load_policy(tmp_path)


def test_read_only_policy_blocks_mutations_but_allows_close_dry_run(tmp_path: Path) -> None:
    policy = save_policy(read_only=True, session_ids=None, state_dir=tmp_path)
    authorize("list_sessions", {}, policy=policy)
    authorize("close_session", {"session_id": "S1", "dry_run": True}, policy=policy)

    with pytest.raises(PolicyDenied) as raised:
        authorize("send_text", {"session_id": "S1", "text": "x"}, policy=policy)
    assert raised.value.code == "READ_ONLY"


def test_allowlist_blocks_unlisted_targets_creation_and_incomplete_container_scope(tmp_path: Path) -> None:
    policy = save_policy(read_only=False, session_ids=["S1", "S2"], state_dir=tmp_path)
    authorize("send_text", {"session_id": "S1", "text": "x"}, policy=policy)
    with pytest.raises(PolicyDenied) as unlisted:
        authorize("send_text", {"session_id": "S3", "text": "x"}, policy=policy)
    assert unlisted.value.code == "SESSION_NOT_ALLOWED"

    with pytest.raises(PolicyDenied):
        authorize("create_tab", {"window_id": "W1"}, policy=policy)

    # Initial request authorization can precede the live topology snapshot.
    authorize("close_tab", {"tab_id": "TAB1"}, policy=policy)
    with pytest.raises(PolicyDenied):
        authorize("close_tab", {"tab_id": "TAB1"}, policy=policy, target_session_ids=["S1", "S3"])
    authorize("close_tab", {"tab_id": "TAB1"}, policy=policy, target_session_ids=["S1", "S2"])


def test_clean_all_requires_explicit_scope_and_respects_the_allowlist(tmp_path: Path) -> None:
    policy = save_policy(read_only=False, session_ids=["S1", "S2"], state_dir=tmp_path)
    with pytest.raises(PolicyDenied) as missing_scope:
        authorize("clean_all_sessions", {}, {}, policy=policy)
    assert missing_scope.value.code == "CLEAN_ALL_SCOPE_REQUIRED"

    authorize(
        "clean_all_sessions",
        {},
        {"authorization_scope": "all_sessions"},
        policy=policy,
        target_session_ids=["S1", "S2"],
    )
    with pytest.raises(PolicyDenied):
        authorize(
            "clean_all_sessions",
            {},
            {"authorization_scope": "all_sessions"},
            policy=policy,
            target_session_ids=["S1", "S3"],
        )


def test_list_and_inspect_rows_are_filtered_by_the_installation_allowlist(tmp_path: Path) -> None:
    policy = save_policy(read_only=True, session_ids=["S2"], state_dir=tmp_path)
    authorize("list_sessions", {}, policy=policy)
    rows = [{"session_id": "S1", "name": "one"}, {"session_id": "S2", "name": "two"}]
    assert filter_session_rows(rows, policy) == [{"session_id": "S2", "name": "two"}]


def test_task_context_checks_exact_registry_identity_and_per_session_revisions(tmp_path: Path) -> None:
    registry_path = tmp_path / "session-registry.json"
    register_record(_record("S1"), path=registry_path)
    register_record(_record("S2"), path=registry_path)

    check_task_context(
        {
            "task_id": "task-1",
            "coordinator_id": "C1",
            "generation": 1,
            "expected_revision": 1,
            "sessions": {"S2": {"generation": 1, "expected_revision": 1}},
        },
        ["S1", "S2"],
        registry_path=registry_path,
    )

    stale = {"task_id": "task-1", "coordinator_id": "C1", "generation": 1, "expected_revision": 2}
    with pytest.raises(TaskContextError) as raised:
        check_task_context(stale, ["S1"], registry_path=registry_path)
    assert raised.value.code == "TASK_CONTEXT_STALE"

    with pytest.raises(TaskContextError):
        check_task_context(
            {"task_id": "task-1", "coordinator_id": "C2", "generation": 1, "expected_revision": 1},
            ["S1"],
            registry_path=registry_path,
        )


def test_create_task_context_is_schema_checked_without_registry_target(tmp_path: Path) -> None:
    check_task_context(
        {"task_id": "task-1", "coordinator_id": "C1", "generation": 1},
        None,
        registry_path=tmp_path / "missing-registry.json",
    )
    with pytest.raises(TaskContextError):
        check_task_context({"task_id": "task-1", "coordinator_id": "C1"}, None)


def test_registered_sessions_require_context_but_unregistered_sessions_do_not(tmp_path: Path) -> None:
    registry_path = tmp_path / "session-registry.json"
    register_record(_record("managed"), path=registry_path)

    with pytest.raises(TaskContextRequiredError) as raised:
        check_task_context(None, ["managed"], registry_path=registry_path)
    assert raised.value.code == "TASK_CONTEXT_REQUIRED"

    # Missing registry file means there are no managed records; direct/manual
    # terminal targets remain operable without a registry ownership claim.
    check_task_context(None, ["manual"], registry_path=tmp_path / "absent.json")


def test_malformed_registry_fails_closed_without_task_context(tmp_path: Path) -> None:
    registry_path = tmp_path / "corrupt-registry.json"
    registry_path.write_text("not valid JSON", encoding="utf-8")
    registry_path.chmod(0o600)

    with pytest.raises(TaskContextError) as raised:
        check_task_context(None, ["S1"], registry_path=registry_path)
    assert raised.value.code == "TASK_CONTEXT_STALE"


def test_task_context_validates_per_session_overrides_without_targets(tmp_path: Path) -> None:
    with pytest.raises(TaskContextError):
        check_task_context(
            {
                "task_id": "task-1",
                "coordinator_id": "C1",
                "generation": 1,
                "sessions": {"S1": {"generation": True, "expected_revision": 1}},
            },
            None,
            registry_path=tmp_path / "absent.json",
        )
