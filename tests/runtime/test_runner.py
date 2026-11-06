"""Focused runner acceptance tests with a transport-free iTerm service."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from goals_iterm.cli import execute, _close_result
from goals_iterm.contract import OPERATION_SCHEMAS
from goals_iterm.observations import observation
from goals_iterm.operation_store import OperationStore
from goals_iterm.policy import save_policy


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
ROWS = [
    {"session_id": "s1", "tab_id": "t1", "window_id": "w1", "name": "alpha"},
    {"session_id": "s2", "tab_id": "t1", "window_id": "w1", "name": "beta"},
]


class FakeBackend:
    def __init__(self, events):
        self.events = events

    async def connect(self):
        self.events.append(("connect",))

    async def close(self, *, timeout):
        self.events.append(("disconnect", timeout))


class FakeService:
    """Expose the real runner surface while recording every dispatched call."""

    def __init__(self, events, rows=None, send_error=None, boundary_rows=None):
        self.events = events
        self.rows = [dict(row) for row in (ROWS if rows is None else rows)]
        self.boundary_rows = None if boundary_rows is None else [dict(row) for row in boundary_rows]
        self.backend = FakeBackend(events)
        self.allowed = None
        self.before_write = None
        self._closing_backend = None
        self.send_error = send_error

    async def _all_rows(self):
        return [dict(row) for row in self.rows]

    async def _call(self, name, *args):
        if name in {"send", "send_key", "rename_session", "create"}:
            if self.boundary_rows is not None:
                self.rows = self.boundary_rows
                self.boundary_rows = None
            await self.before_write()
        self.events.append((name, *args))
        if name == "catalogue":
            rows = self.rows if self.allowed is None else [r for r in self.rows if r["session_id"] in self.allowed]
            return [dict(row) for row in rows]
        if name == "inspect_sessions":
            return {"sessions": [], "observation": "advisory"}
        if name == "screen":
            return {"session_id": args[0], "screen": {}, "captured_at": "2026-11-06T00:00:00Z", "truncated": False}
        if name == "history":
            return {"session_id": args[0], "lines": [], "source_bounds": None, "truncated": False}
        if name in {"send", "send_key"}:
            if self.send_error is not None:
                raise self.send_error
            return {"session_id": args[0], "api_acknowledged": True, "task_completion": "unknown"}
        if name == "rename_session":
            return {"session_id": args[0], "name": args[1] or "alpha-2"}
        if name == "create":
            kind, target_id, command = args
            return {"window_id": "w2" if kind == "window" else target_id, "tab_id": "t2", "session_id": "s3", "name": "created", "command": command}
        raise AssertionError(f"unexpected service call: {name}")

    async def invoke(self, operation, *args):
        return await self._call(operation.__name__, *args)

    async def invoke_close(self, kind, **kwargs):
        if not kwargs.get("dry_run", False):
            await self.before_write()
        self.events.append(("invoke_close", kind, dict(kwargs)))
        return {
            "operation": "clean_all_sessions" if kind == "all" else f"close_{kind}",
            "status": "dry_run" if kwargs.get("dry_run", False) else "closed",
            "code": "DRY_RUN" if kwargs.get("dry_run", False) else "CLOSED",
            "force": kwargs.get("force", False),
            "dry_run": kwargs.get("dry_run", False),
            "target": {"kind": kind},
            "blocking_sessions": [],
            "close_attempted": not kwargs.get("dry_run", False),
            "closed_sessions": [],
            "failed_sessions": [],
            "unknown_sessions": [],
            "skipped_sessions": [],
            "recovery_record_id": None,
            "recovery_record_path": None,
        }

    async def catalogue(self):
        return await self._call("catalogue")

    async def inspect_sessions(self, *args):
        return await self._call("inspect_sessions", *args)

    async def screen(self, *args):
        return await self._call("screen", *args)

    async def history(self, *args):
        return await self._call("history", *args)

    async def send(self, *args):
        return await self._call("send", *args)

    async def send_key(self, *args):
        return await self._call("send_key", *args)

    async def rename_session(self, *args):
        return await self._call("rename_session", *args)

    async def create(self, *args):
        return await self._call("create", *args)


def make_request(operation, arguments=None, **metadata):
    return {
        "schema_version": 1,
        "request_id": metadata.pop("request_id", f"req-{operation}"),
        "operation": operation,
        "arguments": {} if arguments is None else arguments,
        **metadata,
    }


def observed_request(operation, arguments, **metadata):
    return make_request(operation, arguments, expected_observation=observation(ROWS), **metadata)


class RunnerDispatchTests(unittest.TestCase):
    def test_late_close_refusal_preserves_uncertain_effects(self):
        detail = {"status": "refused", "code": "TARGET_CHANGED", "failed_sessions": [{"session_id": "s1", "interruption": "unknown"}]}
        reply = _close_result({"request_id": "late-close"}, detail, True)
        self.assertEqual(reply["status"], "unknown")
        self.assertEqual(reply["side_effects"], "unknown")
        self.assertIs(reply["data"], detail)
        self.assertEqual(_close_result({"request_id": "early-close"}, detail, False)["side_effects"], "none")

    def run_request(self, request, state_dir, *, rows=None, send_error=None, boundary_rows=None):
        events = []
        services = []

        def factory():
            service = FakeService(events, rows=rows, send_error=send_error, boundary_rows=boundary_rows)
            services.append(service)
            return service

        payload = asyncio.run(execute(request, state_dir=state_dir, service_factory=factory))
        return payload, events, services

    def test_all_thirteen_operations_dispatch_with_expected_shapes(self):
        requests = [
            make_request("list_sessions", request_id="dispatch-list"),
            make_request("inspect_sessions", {"session_id": "s1"}, request_id="dispatch-inspect"),
            make_request("read_screen", {"session_id": "s1"}, request_id="dispatch-screen"),
            make_request("read_history", {"session_id": "s1", "lines": 7}, request_id="dispatch-history"),
            observed_request("send_text", {"session_id": "s1", "text": "hello"}, request_id="dispatch-send"),
            observed_request("send_keys", {"session_id": "s1", "key": "ctrl_c"}, request_id="dispatch-key"),
            observed_request("rename_session", {"session_id": "s1", "name": "renamed"}, request_id="dispatch-rename"),
            make_request("create_window", {"command": "echo hi"}, request_id="dispatch-window"),
            observed_request("create_tab", {"window_id": "w1", "command": None}, request_id="dispatch-tab"),
            observed_request("close_session", {"session_id": "s1"}, request_id="dispatch-close-session"),
            observed_request("close_tab", {"tab_id": "t1"}, request_id="dispatch-close-tab"),
            observed_request("close_window", {"window_id": "w1"}, request_id="dispatch-close-window"),
            make_request("clean_all_sessions", {}, request_id="dispatch-clean-all", authorization_scope="all_sessions", expected_observation=observation(ROWS)),
        ]
        expected_calls = [
            ("catalogue",),
            ("inspect_sessions", "s1", None),
            ("screen", "s1"),
            ("history", "s1", 7),
            ("send", "s1", "hello"),
            ("send_key", "s1", "ctrl_c"),
            ("rename_session", "s1", "renamed"),
            ("create", "window", None, "echo hi"),
            ("create", "tab", "w1", None),
            ("invoke_close", "session", {"session_id": "s1", "force": False, "dry_run": False}),
            ("invoke_close", "tab", {"tab_id": "t1", "force": False, "dry_run": False}),
            ("invoke_close", "window", {"window_id": "w1", "force": False, "dry_run": False}),
            ("invoke_close", "all", {"force": False, "dry_run": False}),
        ]

        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary) / "state"
            save_policy(read_only=False, session_ids=None, state_dir=state_dir)
            self.assertEqual(set(item["operation"] for item in requests), set(OPERATION_SCHEMAS))
            for request, expected in zip(requests, expected_calls, strict=True):
                with self.subTest(operation=request["operation"]):
                    payload, events, _ = self.run_request(request, state_dir)
                    self.assertEqual(payload["schema_version"], 1)
                    self.assertEqual(payload["request_id"], request["request_id"])
                    self.assertIn(payload["status"], {"ok", "unknown", "partial"})
                    self.assertIsInstance(payload["warnings"], list)
                    self.assertIn(payload["side_effects"], {"none", "confirmed", "unknown"})
                    self.assertIn(expected, events)
                    if request["operation"] == "list_sessions":
                        self.assertEqual(set(payload["data"]), {"sessions", "observation"})
                        self.assertEqual(payload["data"]["observation"], observation(ROWS))
                    elif request["operation"] == "inspect_sessions":
                        self.assertEqual(set(payload["data"]), {"sessions", "observation"})
                    elif request["operation"] == "read_screen":
                        self.assertEqual(set(payload["data"]), {"session_id", "screen", "captured_at", "truncated"})
                    elif request["operation"] == "read_history":
                        self.assertEqual(set(payload["data"]), {"session_id", "lines", "source_bounds", "truncated"})
                    elif request["operation"] in {"send_text", "send_keys"}:
                        self.assertEqual(payload["data"]["task_completion"], "unknown")
                    elif request["operation"] == "rename_session":
                        self.assertEqual(set(payload["data"]), {"session_id", "name"})
                    elif request["operation"] in {"create_window", "create_tab"}:
                        self.assertTrue({"window_id", "tab_id", "session_id", "name"}.issubset(payload["data"]))
                    elif request["operation"].startswith("close_") or request["operation"] == "clean_all_sessions":
                        self.assertTrue({"operation", "status", "code", "force", "dry_run", "target", "blocking_sessions", "close_attempted", "closed_sessions", "failed_sessions", "unknown_sessions", "skipped_sessions", "recovery_record_id", "recovery_record_path"}.issubset(payload["data"]))

    def test_empty_allowlist_hides_sessions_and_refuses_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary) / "state"
            save_policy(read_only=False, session_ids=[], state_dir=state_dir)
            payload, _, services = self.run_request(make_request("list_sessions", request_id="empty-list"), state_dir)
            self.assertEqual(payload["data"]["sessions"], [])
            self.assertEqual(payload["data"]["observation"], {"sessions": []})
            self.assertEqual(services[0].allowed, set())

            denied, events, services = self.run_request(
                observed_request("send_text", {"session_id": "s1", "text": "blocked"}, request_id="empty-write"), state_dir
            )
            self.assertEqual(denied["status"], "refused")
            self.assertEqual(denied["side_effects"], "none")
            self.assertNotIn(("send", "s1", "blocked"), events)
            self.assertEqual(services, [])

    def test_read_only_refuses_write_and_allows_read_only_dry_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary) / "state"
            save_policy(read_only=True, session_ids=None, state_dir=state_dir)
            denied, events, services = self.run_request(
                observed_request("send_text", {"session_id": "s1", "text": "blocked"}, request_id="readonly-write"), state_dir
            )
            self.assertEqual(denied["status"], "refused")
            self.assertEqual(denied["side_effects"], "none")
            self.assertEqual(events, [])
            self.assertEqual(services, [])

            dry_run, events, services = self.run_request(
                make_request("close_session", {"session_id": "s1", "dry_run": True}, request_id="readonly-dry-run"), state_dir
            )
            self.assertEqual(dry_run["status"], "ok")
            self.assertEqual(dry_run["data"]["status"], "dry_run")
            self.assertEqual(dry_run["side_effects"], "none")
            self.assertIn(("invoke_close", "session", {"session_id": "s1", "dry_run": True, "force": False}), events)
            self.assertEqual(OperationStore(state_dir).status("readonly-dry-run"), None)
            self.assertEqual(len(services), 1)

    def test_stale_observation_refuses_before_any_service_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary) / "state"
            save_policy(read_only=False, session_ids=None, state_dir=state_dir)
            changed = [dict(ROWS[0], window_id="replacement-window"), ROWS[1]]
            payload, events, _ = self.run_request(
                observed_request("send_text", {"session_id": "s1", "text": "stale"}, request_id="stale-write"),
                state_dir,
                rows=changed,
            )
            self.assertEqual(payload["status"], "refused")
            self.assertEqual(payload["side_effects"], "none")
            self.assertFalse(any(event[0] == "send" for event in events))

    def test_observation_change_between_preflight_and_write_is_rechecked(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary) / "state"
            save_policy(read_only=False, session_ids=None, state_dir=state_dir)
            changed = [dict(ROWS[0], tab_id="replacement-tab"), ROWS[1]]
            payload, events, _ = self.run_request(
                observed_request("send_text", {"session_id": "s1", "text": "boundary-stale"}, request_id="boundary-stale"),
                state_dir,
                rows=ROWS,
                boundary_rows=changed,
            )
            self.assertEqual(payload["status"], "refused")
            self.assertEqual(payload["side_effects"], "none")
            self.assertFalse(any(event[0] == "send" for event in events))

    def test_stale_task_owner_at_write_boundary_prevents_send(self):
        current_owner = [{"session_id": "s1", "owner_task_id": "task-1", "coordinator_id": "coord-1", "generation": 1, "revision": 1}]
        replaced_owner = [{"session_id": "s1", "owner_task_id": "other-task", "coordinator_id": "coord-1", "generation": 1, "revision": 1}]
        task_context = {"task_id": "task-1", "coordinator_id": "coord-1", "generation": 1, "expected_revision": 1}
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary) / "state"
            save_policy(read_only=False, session_ids=None, state_dir=state_dir)
            events = []
            services = []

            def factory():
                service = FakeService(events)
                services.append(service)
                return service

            request = observed_request("send_text", {"session_id": "s1", "text": "owned"}, request_id="owner-boundary", task_context=task_context)
            with mock.patch("goals_iterm.policy._read_registry_records", side_effect=[current_owner, replaced_owner]):
                payload = asyncio.run(execute(request, state_dir=state_dir, service_factory=factory))
            self.assertEqual(payload["status"], "refused")
            self.assertEqual(payload["side_effects"], "none")
            self.assertFalse(any(event[0] == "send" for event in events))
            self.assertEqual(len(services), 1)

    def test_after_send_failure_is_unknown_and_completed_request_is_not_replayed(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary) / "state"
            save_policy(read_only=False, session_ids=None, state_dir=state_dir)
            events = []
            services = []

            def factory():
                service = FakeService(events, send_error=OSError("transport dropped after send"))
                services.append(service)
                return service

            request = observed_request("send_text", {"session_id": "s1", "text": "once"}, request_id="send-then-fail")
            first = asyncio.run(execute(request, state_dir=state_dir, service_factory=factory))
            second = asyncio.run(execute(request, state_dir=state_dir, service_factory=factory))
            self.assertEqual(first["status"], "unknown")
            self.assertEqual(first["side_effects"], "unknown")
            self.assertEqual(first, second)
            self.assertEqual(sum(event[0] == "send" for event in events), 1)
            self.assertEqual(len(services), 1)

    def test_finish_failure_after_send_leaves_unknown_reservation_without_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary) / "state"
            save_policy(read_only=False, session_ids=None, state_dir=state_dir)
            events = []
            services = []

            def factory():
                service = FakeService(events)
                services.append(service)
                return service

            request = observed_request("send_text", {"session_id": "s1", "text": "sent"}, request_id="finish-failure")
            with mock.patch.object(OperationStore, "finish", side_effect=OSError("disk failure")):
                failed = asyncio.run(execute(request, state_dir=state_dir, service_factory=factory))
            self.assertEqual(failed["status"], "unknown")
            self.assertEqual(failed["code"], "OPERATION_PERSISTENCE_FAILED")
            self.assertEqual(sum(event[0] == "send" for event in events), 1)

            retry = asyncio.run(execute(request, state_dir=state_dir, service_factory=factory))
            self.assertEqual(retry["status"], "unknown")
            self.assertEqual(retry["code"], "REQUEST_OUTCOME_UNKNOWN")
            self.assertEqual(sum(event[0] == "send" for event in events), 1)
            self.assertEqual(len(services), 1)

    def test_reserved_unknown_request_is_not_dispatched(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary) / "state"
            save_policy(read_only=False, session_ids=None, state_dir=state_dir)
            request = observed_request("send_text", {"session_id": "s1", "text": "maybe sent"}, request_id="crashed-request")
            # A durable reservation without a result is the on-disk state left
            # by a crashed process whose side effects cannot be determined.
            import goals_iterm.cli as runner

            reservation = OperationStore(state_dir).reserve(
                request["request_id"], runner._fingerprint(request), request["operation"],
                task_context=None, expected_observation=request["expected_observation"],
            )
            self.assertEqual(reservation.disposition, "new")
            payload, events, services = self.run_request(request, state_dir)
            self.assertEqual(payload["status"], "unknown")
            self.assertEqual(payload["code"], "REQUEST_OUTCOME_UNKNOWN")
            self.assertEqual(events, [])
            self.assertEqual(services, [])


class RunnerCliTests(unittest.TestCase):
    def invoke_cli(self, args, stdin=None, state_home=None):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(RUNTIME) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        if state_home is not None:
            env["XDG_STATE_HOME"] = str(state_home)
        return subprocess.run(
            [sys.executable, "-m", "goals_iterm.cli", *args],
            input=stdin,
            capture_output=True,
            cwd=ROOT,
            env=env,
            check=False,
        )

    def test_cli_capabilities_emits_only_structured_stdout(self):
        with tempfile.TemporaryDirectory() as temporary:
            completed = self.invoke_cli(["capabilities", "--json"], state_home=temporary)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors="replace"))
        self.assertEqual(completed.stderr, b"")
        lines = completed.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        payload = json.loads(lines[0])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(set(payload["data"]["operations"]), set(OPERATION_SCHEMAS))

    def test_cli_invalid_boolean_string_and_arguments_return_json_errors(self):
        invalid = [
            make_request("close_session", {"session_id": "s1", "force": "false"}, request_id="bad-bool"),
            make_request("read_history", {"session_id": "s1", "lines": True}, request_id="bad-int"),
            make_request("list_sessions", "not-an-object", request_id="bad-arguments"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            for request in invalid:
                with self.subTest(request_id=request["request_id"]):
                    completed = self.invoke_cli(["invoke"], stdin=json.dumps(request).encode(), state_home=temporary)
                    self.assertEqual(completed.returncode, 4, completed.stderr.decode(errors="replace"))
                    self.assertEqual(completed.stderr, b"")
                    lines = completed.stdout.splitlines()
                    self.assertEqual(len(lines), 1)
                    payload = json.loads(lines[0])
                    self.assertEqual(payload["status"], "error")
                    self.assertEqual(payload["code"], "INVALID_REQUEST")


if __name__ == "__main__":
    unittest.main()
