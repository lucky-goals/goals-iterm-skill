"""Targeted tests for the local session registry helper."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest

from scripts import session_registry as registry


def _record(session_id: str = "S1", task_id: str = "T1", coordinator_id: str = "C1") -> dict:
    return {
        "session_id": session_id,
        "owner_task_id": task_id,
        "coordinator_id": coordinator_id,
        "origin": "created",
        "cleanup_policy": "auto_owned",
        "audit_path": "/tmp/audit.md",
    }


def _thread_update(path: str, barrier: threading.Barrier, result: list[tuple[str, object]], marker: str) -> None:
    barrier.wait()
    try:
        value = registry.update_record("S1", "C1", 1, 1, {"evidence": {"writer": marker}}, path)
    except registry.RegistryError as exc:
        result.append((marker, str(exc)))
    else:
        result.append((marker, value["revision"]))


class SessionRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.state = Path(self.tempdir.name) / "nested" / "registry.json"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def register(self, **overrides: object) -> dict:
        record = _record()
        if "task_id" in overrides:
            overrides["owner_task_id"] = overrides.pop("task_id")
        record.update(overrides)
        return registry.register_record(record, self.state)

    def test_register_defaults_are_private_and_timestamped(self) -> None:
        result = self.register()
        self.assertEqual(result["generation"], 1)
        self.assertEqual(result["revision"], 1)
        self.assertEqual(result["execution_status"], "running")
        self.assertEqual(result["cleanup_status"], "pending")
        self.assertEqual(result["recovery_status"], "unknown")
        self.assertEqual(result["coordinator_phase"], "active")
        self.assertEqual(result["monitor_status"], "unknown")
        self.assertEqual(result["monitor_mode"], "unknown")
        self.assertTrue(result["created_at"].endswith("Z"))
        self.assertTrue(result["updated_at"].endswith("Z"))
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.state.with_name(self.state.name + ".lock").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.state.parent.stat().st_mode) & 0o077, 0)

    def test_stale_revision_and_coordinator_are_rejected(self) -> None:
        self.register()
        patch = {"execution_status": "waiting_user"}
        updated = registry.update_record("S1", "C1", 1, 1, patch, self.state)
        self.assertEqual(updated["revision"], 2)
        with self.assertRaisesRegex(registry.RegistryError, "revision is stale"):
            registry.update_record("S1", "C1", 1, 1, patch, self.state)
        with self.assertRaisesRegex(registry.RegistryError, "coordinator_id"):
            registry.update_record("S1", "old-coordinator", 1, 2, patch, self.state)

    def test_concurrent_optimistic_writers_allow_one_revision(self) -> None:
        self.register()
        barrier = threading.Barrier(2)
        result: list[tuple[str, object]] = []
        threads = [
            threading.Thread(target=_thread_update, args=(str(self.state), barrier, result, "a")),
            threading.Thread(target=_thread_update, args=(str(self.state), barrier, result, "b")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(len(result), 2)
        self.assertEqual(sum(isinstance(value, int) for _, value in result), 1)
        self.assertEqual(registry.list_records(self.state)[0]["revision"], 2)

    def test_identity_update_advances_generation_and_clears_old_evidence(self) -> None:
        self.register(
            tab_id="old-tab",
            monitor_mode="background",
            schedule_handle="scheduler-old-generation",
            chat_uuid="old-chat",
            process_identity={"pid": 12},
            owned_container={"tab_id": "old-tab", "window_id": "old-window", "basis": "created"},
            evidence={"source": "old"},
            acceptance_evidence={"accepted": True},
            recovery_record_path="/tmp/old-recovery.json",
        )
        completed = registry.update_record(
            "S1",
            "C1",
            1,
            1,
            {"execution_status": "completed", "cleanup_status": "closed", "coordinator_phase": "settled"},
            self.state,
        )
        rebound = registry.update_record("S1", "C1", 1, completed["revision"], {"tab_id": "new-tab"}, self.state)
        self.assertEqual(rebound["generation"], 2)
        self.assertEqual(rebound["revision"], 3)
        self.assertEqual(rebound["tab_id"], "new-tab")
        self.assertEqual(rebound["execution_status"], "running")
        self.assertEqual(rebound["cleanup_status"], "pending")
        self.assertEqual(rebound["recovery_status"], "unknown")
        self.assertEqual(rebound["coordinator_phase"], "active")
        self.assertEqual(rebound["monitor_mode"], "unknown")
        self.assertNotIn("schedule_handle", rebound)
        for field in (
            "chat_uuid",
            "process_identity",
            "owned_container",
            "evidence",
            "acceptance_evidence",
            "recovery_record_path",
        ):
            self.assertNotIn(field, rebound)
        with self.assertRaisesRegex(registry.RegistryError, "generation is stale"):
            registry.update_record("S1", "C1", 1, rebound["revision"], {}, self.state)

    def test_handoff_resets_old_work_and_requires_new_audit_path(self) -> None:
        self.register(
            window_id="old-window",
            tab_id="old-tab",
            owned_container={"tab_id": "old-tab", "window_id": "old-window", "basis": "created"},
            chat_uuid="old-chat",
            process_identity={"pid": 12},
            evidence={"source": "old"},
            cleanup_authorization="old task authorization",
            acceptance_evidence={"accepted": True},
            recovery_record_path="/tmp/old-recovery.json",
            cleanup_status="closed",
            execution_status="completed",
            coordinator_phase="settled",
            recovery_status="ready",
        )
        with self.assertRaisesRegex(registry.RegistryError, "requires --audit-path"):
            registry.handoff_record("S1", "C1", 1, 1, "C2", "T2", "resume", self.state)
        handed = registry.handoff_record(
            "S1", "C1", 1, 1, "C2", "T2", "resume after reuse", self.state, "/tmp/new-audit.md"
        )
        self.assertEqual(handed["owner_task_id"], "T2")
        self.assertEqual(handed["coordinator_id"], "C2")
        self.assertEqual(handed["audit_path"], "/tmp/new-audit.md")
        self.assertEqual(handed["generation"], 2)
        self.assertEqual(handed["revision"], 2)
        self.assertEqual(handed["execution_status"], "running")
        self.assertEqual(handed["cleanup_status"], "pending")
        self.assertEqual(handed["recovery_status"], "unknown")
        self.assertEqual(handed["coordinator_phase"], "active")
        self.assertEqual(handed["monitor_status"], "unknown")
        self.assertEqual(handed["origin"], "borrowed")
        self.assertEqual(handed["cleanup_policy"], "retain")
        self.assertIn("new cleanup authorization", handed["cleanup_reason"])
        for field in (
            "window_id",
            "tab_id",
            "owned_container",
            "cleanup_authorization",
            "chat_uuid",
            "process_identity",
            "evidence",
            "acceptance_evidence",
            "recovery_record_path",
        ):
            self.assertNotIn(field, handed)
        with self.assertRaisesRegex(registry.RegistryError, "coordinator_id"):
            registry.update_record("S1", "C1", 1, 2, {"execution_status": "completed"}, self.state)

    def test_identity_change_requires_separate_new_generation_update(self) -> None:
        self.register(tab_id="old-tab", cleanup_status="closed", coordinator_phase="settled")
        with self.assertRaisesRegex(registry.RegistryError, "separate new-generation"):
            registry.update_record(
                "S1",
                "C1",
                1,
                1,
                {"tab_id": "new-tab", "execution_status": "completed", "cleanup_status": "closed"},
                self.state,
            )
        original = registry.list_records(self.state)[0]
        self.assertEqual(original["generation"], 1)
        self.assertEqual(original["revision"], 1)
        rebound = registry.update_record("S1", "C1", 1, 1, {"tab_id": "new-tab"}, self.state)
        self.assertEqual((rebound["generation"], rebound["revision"]), (2, 2))
        finished = registry.update_record(
            "S1",
            "C1",
            2,
            2,
            {"execution_status": "completed", "cleanup_status": "closed", "coordinator_phase": "settled"},
            self.state,
        )
        self.assertEqual(finished["execution_status"], "completed")

    def test_same_task_handoff_preserves_work_and_cleanup_evidence(self) -> None:
        self.register(
            execution_status="waiting_user",
            coordinator_phase="finalizing",
            cleanup_status="retained",
            recovery_status="degraded",
            cleanup_reason="awaiting user confirmation",
            retention_reason="user requested review",
            cleanup_authorization="same-task authorization",
            remaining_work=["confirm result"],
            monitor_status="running",
            monitor_mode="background",
            schedule_handle="scheduler-1",
            next_check_at="2026-10-25T15:00:00Z",
            owned_container={"tab_id": "tab-1", "basis": "created"},
            evidence={"source": "same-task"},
        )
        handed = registry.handoff_record("S1", "C1", 1, 1, "C2", "T1", "coordinator rotation", self.state)
        self.assertEqual(handed["owner_task_id"], "T1")
        self.assertEqual(handed["coordinator_id"], "C2")
        self.assertEqual(handed["generation"], 2)
        self.assertEqual(handed["execution_status"], "waiting_user")
        self.assertEqual(handed["coordinator_phase"], "finalizing")
        self.assertEqual(handed["cleanup_status"], "retained")
        self.assertEqual(handed["recovery_status"], "degraded")
        self.assertEqual(handed["cleanup_reason"], "awaiting user confirmation")
        self.assertEqual(handed["remaining_work"], ["confirm result"])
        self.assertEqual(handed["owned_container"]["tab_id"], "tab-1")
        self.assertEqual(handed["monitor_status"], "unknown")
        self.assertEqual(handed["monitor_mode"], "unknown")
        self.assertEqual(handed["schedule_handle"], "scheduler-1")
        self.assertEqual(handed["next_check_at"], "2026-10-25T15:00:00Z")

    def test_new_cleanup_authorization_is_required_and_consumed_with_policy_change(self) -> None:
        retained = self.register(cleanup_policy="retain", origin="borrowed")
        with self.assertRaisesRegex(registry.RegistryError, "same patch"):
            registry.update_record(
                "S1", "C1", 1, retained["revision"], {"cleanup_policy": "auto_owned"}, self.state
            )
        with self.assertRaisesRegex(registry.RegistryError, "same patch"):
            registry.update_record(
                "S1",
                "C1",
                1,
                retained["revision"],
                {"cleanup_policy": "auto_owned", "cleanup_authorization": " "},
                self.state,
            )
        authorized = registry.update_record(
            "S1",
            "C1",
            1,
            retained["revision"],
            {"cleanup_policy": "auto_owned", "cleanup_authorization": "new user authorization"},
            self.state,
        )
        self.assertEqual(authorized["cleanup_policy"], "auto_owned")
        self.assertEqual(authorized["cleanup_authorization"], "new user authorization")
        self.assertEqual(authorized["origin"], "borrowed")

        identity_patch = Path(self.tempdir.name) / "identity-state.json"
        registry.register_record(
            dict(_record("S2", "T2", "C2"), cleanup_policy="retain", origin="borrowed"), identity_patch
        )
        with self.assertRaisesRegex(registry.RegistryError, "cannot restore auto_owned"):
            registry.update_record(
                "S2",
                "C2",
                1,
                1,
                {
                    "tab_id": "new-tab",
                    "cleanup_policy": "auto_owned",
                    "cleanup_authorization": "new auth",
                },
                identity_patch,
            )
        rebound = registry.update_record("S2", "C2", 1, 1, {"tab_id": "new-tab"}, identity_patch)
        authorized_after_rebind = registry.update_record(
            "S2",
            "C2",
            rebound["generation"],
            rebound["revision"],
            {"cleanup_policy": "auto_owned", "cleanup_authorization": "new auth"},
            identity_patch,
        )
        self.assertEqual(authorized_after_rebind["cleanup_policy"], "auto_owned")

    def test_unknown_cleanup_blocks_cross_task_handoff_and_identity_change(self) -> None:
        self.register(cleanup_status="unknown")
        with self.assertRaisesRegex(registry.RegistryError, "closing/unknown"):
            registry.handoff_record("S1", "C1", 1, 1, "C2", "T2", "new task", self.state, "/tmp/t2.md")
        with self.assertRaisesRegex(registry.RegistryError, "closing/unknown"):
            registry.update_record("S1", "C1", 1, 1, {"tab_id": "new-tab"}, self.state)

    def test_report_marks_unsettled_states_and_unmatched_task(self) -> None:
        self.register()
        self.register(session_id="S2", task_id="T2", coordinator_id="C2", cleanup_status="blocked")
        self.register(
            session_id="S3",
            task_id="T3",
            cleanup_status="retained",
            retention_reason="user asked to keep it",
            coordinator_phase="settled",
            monitor_status="stopped",
        )
        report = registry.report_records(self.state)
        self.assertEqual(report["counts"]["total"], 3)
        self.assertEqual(report["counts"]["outstanding"], 2)
        self.assertEqual(report["counts"]["schedule"]["unscheduled"], 3)
        rows = {row["session_id"]: row for row in report["resources"]}
        self.assertIn("cleanup_status=pending", rows["S1"]["outstanding_reasons"])
        self.assertIn("cleanup_status=blocked", rows["S2"]["outstanding_reasons"])
        self.assertFalse(rows["S3"]["outstanding"])
        self.assertFalse(report["settled"])

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = registry.main(["--path", str(self.state), "report", "--task-id", "missing", "--require-settled"])
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output.getvalue())["resources"], [])
        self.assertFalse(json.loads(output.getvalue())["settled"])

    def test_schedule_requires_a_real_handle_and_empty_report_is_unsettled(self) -> None:
        self.register(
            coordinator_phase="settled",
            cleanup_status="closed",
            monitor_status="stopped",
            monitor_mode="inline",
            next_check_at="2026-10-25T15:00:00Z",
        )
        report = registry.report_records(self.state)
        row = report["resources"][0]
        self.assertEqual(row["monitor_mode"], "inline")
        self.assertEqual(row["schedule_status"], "unscheduled")
        self.assertEqual(report["counts"]["monitor_mode"], {"inline": 1})
        self.assertEqual(report["counts"]["schedule"]["unscheduled"], 1)
        # The mode describes where monitoring would run; it is not evidence
        # that the inline coordinator is still alive.
        self.assertTrue(report["settled"])
        scheduled = registry.update_record("S1", "C1", 1, 1, {"schedule_handle": "scheduler-1"}, self.state)
        self.assertEqual(registry.report_records(self.state)["resources"][0]["schedule_status"], "scheduled")
        self.assertEqual(scheduled["revision"], 2)
        empty_state = Path(self.tempdir.name) / "empty.json"
        empty_report = registry.report_records(empty_state, task_id="missing")
        self.assertFalse(empty_report["settled"])

    def test_legacy_v1_record_without_monitor_mode_reads_as_unknown_without_rewrite(self) -> None:
        self.register(
            schedule_handle="scheduler-legacy",
            monitor_status="running",
        )
        state = json.loads(self.state.read_text(encoding="utf-8"))
        del state["records"]["S1"]["monitor_mode"]
        self.state.write_text(json.dumps(state), encoding="utf-8")
        self.state.chmod(0o600)
        legacy_bytes = self.state.read_bytes()

        record = registry.list_records(self.state)[0]
        report = registry.report_records(self.state)
        row = report["resources"][0]

        self.assertEqual(record["monitor_mode"], "unknown")
        self.assertEqual(row["monitor_mode"], "unknown")
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(row["schedule_status"], "scheduled")
        self.assertEqual(self.state.read_bytes(), legacy_bytes)

    def test_cross_task_handoff_clears_monitor_mode_and_old_schedule_handle(self) -> None:
        self.register(
            monitor_mode="background",
            schedule_handle="scheduler-old-task",
            cleanup_status="closed",
            coordinator_phase="settled",
        )
        handed = registry.handoff_record(
            "S1", "C1", 1, 1, "C2", "T2", "new task", self.state, "/tmp/t2.md"
        )
        self.assertEqual(handed["monitor_mode"], "unknown")
        self.assertNotIn("schedule_handle", handed)

    def test_monitor_mode_enum_is_validated(self) -> None:
        with self.assertRaisesRegex(registry.RegistryError, "monitor_mode must be one of"):
            self.register(monitor_mode="daemon")

    def test_active_failed_or_unknown_monitor_is_not_settled(self) -> None:
        for index, monitor_status in enumerate(("running", "failed", "unknown"), start=1):
            state = Path(self.tempdir.name) / f"monitor-{index}.json"
            registry.register_record(
                _record(f"S{index}", f"T{index}", f"C{index}")
                | {
                    "execution_status": "completed",
                    "cleanup_status": "closed",
                    "coordinator_phase": "settled",
                    "monitor_status": monitor_status,
                },
                state,
            )
            row = registry.report_records(state)["resources"][0]
            self.assertTrue(row["outstanding"])
            self.assertIn(f"monitor_status={monitor_status}", row["outstanding_reasons"])

    def test_state_and_lock_must_be_regular_files(self) -> None:
        self.state.parent.mkdir(parents=True)
        os.mkfifo(self.state)
        with self.assertRaisesRegex(registry.RegistryError, "regular file"):
            registry.list_records(self.state)

        self.state.unlink()
        lock = self.state.with_name(self.state.name + ".lock")
        lock.unlink()
        os.mkfifo(lock)
        with self.assertRaisesRegex(registry.RegistryError, "regular file"):
            registry.register_record(_record(), self.state)

    def test_retained_without_reason_and_completed_pending_are_visible(self) -> None:
        self.register(
            cleanup_status="retained",
            execution_status="completed",
            coordinator_phase="settled",
        )
        row = registry.report_records(self.state)["resources"][0]
        self.assertTrue(row["outstanding"])
        self.assertIn("retained_without_retention_reason", row["outstanding_reasons"])
        self.assertEqual(row["execution_status"], "completed")
        self.assertEqual(row["cleanup_status"], "retained")

        other = Path(self.tempdir.name) / "other.json"
        registry.register_record(_record("S2", "T2", "C2"), other)
        row2 = registry.report_records(other)["resources"][0]
        self.assertIn("cleanup_status=pending", row2["outstanding_reasons"])

    def test_corrupt_or_old_state_is_not_replaced(self) -> None:
        self.state.parent.mkdir(parents=True)
        self.state.write_text("not json", encoding="utf-8")
        self.state.chmod(0o600)
        with self.assertRaisesRegex(registry.RegistryError, "corrupt JSON"):
            registry.list_records(self.state)
        self.assertEqual(self.state.read_text(encoding="utf-8"), "not json")

        self.state.write_text(json.dumps({"schema_version": 0, "records": {}}), encoding="utf-8")
        with self.assertRaisesRegex(registry.RegistryError, "unsupported schema_version"):
            registry.list_records(self.state)

    def test_state_and_lock_symlinks_are_rejected(self) -> None:
        target = Path(self.tempdir.name) / "target.json"
        target.write_text("{}", encoding="utf-8")
        target.chmod(0o600)
        self.state.parent.mkdir(parents=True)
        self.state.symlink_to(target)
        with self.assertRaisesRegex(registry.RegistryError, "symlink"):
            registry.list_records(self.state)

        self.state.unlink()
        lock = self.state.with_name(self.state.name + ".lock")
        lock_target = Path(self.tempdir.name) / "lock-target"
        lock_target.touch()
        lock_target.chmod(0o600)
        lock.symlink_to(lock_target)
        with self.assertRaisesRegex(registry.RegistryError, "symlink"):
            registry.register_record(_record(), self.state)

    def test_owned_container_schema_is_bounded(self) -> None:
        with self.assertRaisesRegex(registry.RegistryError, "owned_container.*non-empty"):
            self.register(owned_container={"tab_id": ""})
        with self.assertRaisesRegex(registry.RegistryError, "unknown owned_container field"):
            self.register(owned_container={"session_id": "not-allowed"})
        record = self.register(owned_container={"tab_id": "tab-1", "window_id": None, "basis": "created"})
        self.assertEqual(record["owned_container"]["tab_id"], "tab-1")

    def test_cli_prints_mutation_record_and_help_documents_enums(self) -> None:
        record_path = Path(self.tempdir.name) / "record.json"
        record_path.write_text(json.dumps(_record()), encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = registry.main(["register", "--path", str(self.state), "--record", str(record_path)])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["revision"], 1)

        help_output = io.StringIO()
        with contextlib.redirect_stdout(help_output):
            with self.assertRaises(SystemExit) as raised:
                registry.main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("coordinator_phase=active|finalizing|settled", help_output.getvalue())
        self.assertIn("monitor_mode=inline|background|none|unknown", help_output.getvalue())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
