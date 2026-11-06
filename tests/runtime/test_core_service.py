"""Focused service contract tests; no real terminal writes are performed."""

from __future__ import annotations

import unittest
import asyncio
from unittest.mock import AsyncMock

from goals_iterm.backend_types import CaptureDTO, CaptureLineDTO
from goals_iterm.errors import DomainError
from goals_iterm.service import ItermTools, KEYS


class FakeBackend:
    def __init__(self):
        target = {
            "session_id": "session-1",
            "session_epoch": "epoch-1",
            "broker_epoch": "broker-1",
        }
        self.rows = [
            {
                "target": target,
                "window_id": "window-1",
                "tab_id": "tab-1",
                "name": "alpha",
                "title": "alpha",
            }
        ]
        self.events: list[str] = []
        self.sent: list[tuple[dict, str]] = []
        self.renamed: list[tuple[dict, str]] = []
        self.created: list[tuple[str, str | None, str | None, str]] = []
        self.connected = 0

    async def connect(self):
        self.connected += 1
        self.events.append("connect")

    async def close(self, timeout=None):
        self.events.append("close")
        return None

    async def list_sessions(self):
        self.events.append("catalogue")
        return [dict(row) for row in self.rows]

    async def capture(self, target):
        self.events.append("capture")
        return CaptureDTO(
            screen={"lines": [{"row": 0, "text": "界😀"}]}, captured_at="now"
        )

    async def history(self, target, last_lines):
        self.events.append("history")
        return CaptureDTO(
            history_lines=(CaptureLineDTO(3, "prior\tline", wrapped=False),),
            history_source_bounds={"start": 3, "end_exclusive": 4},
        )

    async def send(self, target, text):
        self.events.append("send")
        self.sent.append((dict(target), text))

    async def rename(self, target, name):
        self.events.append("rename")
        self.renamed.append((dict(target), name))

    async def create(self, kind, target_id=None, command=None, *, name):
        self.events.append("create")
        self.created.append((kind, target_id, command, name))
        return {
            "window_id": "window-new",
            "tab_id": "tab-new",
            "session_id": "session-new",
        }


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_operation_methods_return_plain_payloads_and_preserve_reads(self):
        backend = FakeBackend()
        service = ItermTools(backend)

        listed = {"sessions": await service.invoke(service.catalogue)}
        screen = await service.invoke(service.screen, "session-1")
        history = await service.invoke(service.history, "session-1", 10)

        self.assertIs(type(listed), dict)
        self.assertEqual(listed["sessions"][0]["target"]["session_id"], "session-1")
        self.assertEqual(screen["screen"]["lines"][0]["text"], "界😀")
        self.assertEqual(history["lines"][0], {
            "position": 3,
            "text": "prior\tline",
            "wrapped": False,
        })
        self.assertEqual(history["source_bounds"], {"start": 3, "end_exclusive": 4})

    async def test_exact_text_and_key_sequences_are_sent_once(self):
        backend = FakeBackend()
        service = ItermTools(backend)
        text = "a\t界😀\nb\n"

        result = await service.invoke(service.send, "session-1", text)
        key_result = await service.invoke(service.send_key, "session-1", "enter")

        self.assertEqual(result["api_acknowledged"], True)
        self.assertEqual(result["task_completion"], "unknown")
        self.assertEqual(key_result["api_acknowledged"], True)
        self.assertEqual([text for _target, text in backend.sent], [text, KEYS["enter"]])

    async def test_all_supported_keys_send_the_exact_terminal_sequences(self):
        backend = FakeBackend()
        service = ItermTools(backend)

        for key, sequence in KEYS.items():
            result = await service.invoke(service.send_key, "session-1", key)
            self.assertEqual(result["api_acknowledged"], True)
            self.assertEqual(backend.sent[-1][1], sequence)
        self.assertEqual(len(backend.sent), len(KEYS))

    async def test_inspect_is_advisory_read_only_and_respects_the_allowlist(self):
        backend = FakeBackend()
        second = dict(backend.rows[0])
        second["target"] = dict(second["target"], session_id="session-2")
        second.update(name="Beta", title="Beta")
        backend.rows[0].update(name="Alpha", title="Alpha")
        backend.rows.append(second)

        class ProbeBackend:
            async def probe(self, row):
                return {
                    "state": "idle",
                    "reason": "fixture",
                    "identity": None,
                    "cli_sessions": [],
                }

        service = ItermTools(
            backend,
            session_ids=["session-1"],
            closing_backend=ProbeBackend(),
        )
        result = await service.invoke(service.inspect_sessions)
        selected = await service.invoke(service.inspect_sessions, None, " alpha ")

        self.assertEqual([item["session_id"] for item in result["sessions"]], ["session-1"])
        self.assertEqual(selected["sessions"][0]["session_id"], "session-1")
        self.assertTrue(selected["sessions"][0]["close_readiness"]["advisory"])
        self.assertEqual(backend.sent, [])
        self.assertEqual(backend.renamed, [])
        self.assertEqual(backend.created, [])
        with self.assertRaises(DomainError) as denied:
            await service.invoke(service.inspect_sessions, "session-2", None)
        self.assertEqual(denied.exception.code, "SESSION_NOT_ALLOWED")

    async def test_inspect_rejects_conflicting_and_ambiguous_selectors(self):
        backend = FakeBackend()
        second = dict(backend.rows[0])
        second["target"] = dict(second["target"], session_id="session-2")
        second.update(name=" alpha ", title=" alpha ")
        backend.rows[0].update(name="Alpha", title="Alpha")
        backend.rows.append(second)

        class ProbeBackend:
            async def probe(self, row):
                return {"state": "unknown", "reason": "fixture", "cli_sessions": []}

        service = ItermTools(backend, closing_backend=ProbeBackend())
        with self.assertRaises(DomainError) as conflicting:
            await service.invoke(service.inspect_sessions, "session-1", "Alpha")
        self.assertEqual(conflicting.exception.code, "SELECTOR_CONFLICT")
        with self.assertRaises(DomainError) as ambiguous:
            await service.invoke(service.inspect_sessions, None, "ALPHA")
        self.assertEqual(ambiguous.exception.code, "AMBIGUOUS_SELECTOR")

    async def test_backend_failure_is_sanitized_and_never_retried(self):
        backend = FakeBackend()
        backend.send = AsyncMock(side_effect=RuntimeError("private terminal secret"))
        service = ItermTools(backend)

        with self.assertRaises(DomainError) as failed:
            await service.invoke(service.send, "session-1", "x")

        self.assertEqual(failed.exception.code, "ITERM_API_ERROR")
        self.assertNotIn("private terminal secret", str(failed.exception))
        backend.send.assert_awaited_once()

    async def test_before_write_runs_after_target_resolution_and_before_send(self):
        backend = FakeBackend()
        events = backend.events

        async def before_write():
            events.append("before_write")

        service = ItermTools(backend, before_write=before_write)
        await service.invoke(service.send, "session-1", "once")

        self.assertLess(events.index("catalogue"), events.index("before_write"))
        self.assertLess(events.index("before_write"), events.index("send"))
        self.assertEqual(backend.sent[0][1], "once")

    async def test_empty_allowlist_denies_targets_and_creation(self):
        backend = FakeBackend()
        service = ItermTools(backend, session_ids=[])

        with self.assertRaises(DomainError) as denied:
            await service.invoke(service.send, "session-1", "x")
        self.assertEqual(denied.exception.code, "SESSION_NOT_ALLOWED")
        with self.assertRaises(DomainError) as creation:
            await service.invoke(service.create, "window", None, None)
        self.assertEqual(
            creation.exception.code, "CREATION_DISABLED_WITH_SESSION_ALLOWLIST"
        )
        self.assertEqual(backend.sent, [])
        self.assertEqual(backend.created, [])

    async def test_write_hook_runs_before_rename_and_create(self):
        backend = FakeBackend()

        async def before_write():
            backend.events.append("before_write")

        service = ItermTools(backend, before_write=before_write)
        renamed = await service.invoke(service.rename_session, "session-1", "beta")
        self.assertEqual(renamed["name"], "beta")
        self.assertEqual(backend.renamed[0][1], "beta")
        self.assertLess(backend.events.index("before_write"), backend.events.index("rename"))

        backend.events.clear()
        created = await service.invoke(service.create, "window", None, "/bin/cat")
        self.assertEqual(created["session_id"], "session-new")
        self.assertEqual(backend.created[0][:3], ("window", None, "/bin/cat"))
        self.assertLess(backend.events.index("catalogue"), backend.events.index("before_write"))
        self.assertLess(backend.events.index("before_write"), backend.events.index("create"))

    async def test_create_tab_resolves_exact_window_and_passes_arguments(self):
        backend = FakeBackend()
        service = ItermTools(backend)

        created = await service.invoke(service.create, "tab", "window-1", "/bin/cat")

        self.assertEqual(created["window_id"], "window-new")
        self.assertEqual(backend.created[0][:3], ("tab", "window-1", "/bin/cat"))
        self.assertTrue(backend.created[0][3])
        self.assertNotEqual(backend.created[0][3], "alpha")
        backend.created.clear()
        with self.assertRaises(DomainError) as missing:
            await service.invoke(service.create, "tab", "missing-window", None)
        self.assertEqual(missing.exception.code, "WINDOW_NOT_FOUND")
        self.assertEqual(backend.created, [])

    async def test_invalid_commands_and_text_are_rejected_before_mutation(self):
        backend = FakeBackend()
        service = ItermTools(backend)

        for command in ("", "界" * 6000):
            with self.assertRaises(DomainError):
                await service.invoke(service.create, "window", None, command)
        for text in ("", "界" * 6000):
            with self.assertRaises(DomainError):
                await service.invoke(service.send, "session-1", text)
        self.assertEqual(backend.created, [])
        self.assertEqual(backend.sent, [])

    async def test_prewrite_refusal_blocks_send_rename_and_create(self):
        backend = FakeBackend()
        checks = 0

        async def reject_write():
            nonlocal checks
            checks += 1
            raise DomainError("PRECONDITION_FAILED")

        service = ItermTools(backend, before_write=reject_write)
        calls = (
            lambda: service.invoke(service.send, "session-1", "x"),
            lambda: service.invoke(service.rename_session, "session-1", "beta"),
            lambda: service.invoke(service.create, "window", None, None),
        )
        for call in calls:
            with self.assertRaises(DomainError) as refused:
                await call()
            self.assertEqual(refused.exception.code, "PRECONDITION_FAILED")
        self.assertEqual(checks, 3)
        self.assertEqual(backend.sent, [])
        self.assertEqual(backend.renamed, [])
        self.assertEqual(backend.created, [])

    async def test_concurrent_writes_are_serialized(self):
        backend = FakeBackend()
        entered = asyncio.Event()
        release = asyncio.Event()

        async def blocked_send(target, text):
            backend.events.append("send")
            entered.set()
            await release.wait()
            backend.sent.append((dict(target), text))

        backend.send = blocked_send
        service = ItermTools(backend)
        first = asyncio.create_task(service.invoke(service.send, "session-1", "a"))
        await entered.wait()
        second = asyncio.create_task(service.invoke(service.send, "session-1", "b"))
        await asyncio.sleep(0)
        self.assertEqual(backend.events.count("send"), 1)
        release.set()
        await asyncio.gather(first, second)
        self.assertEqual(backend.events.count("send"), 2)

    async def test_invalid_limits_and_key_never_write(self):
        backend = FakeBackend()
        service = ItermTools(backend)

        for text in ("", "界" * 6000):
            with self.assertRaises(DomainError):
                await service.invoke(service.send, "session-1", text)
        for lines in (0, 2001, True):
            with self.assertRaises(DomainError):
                await service.invoke(service.history, "session-1", lines)
        with self.assertRaises(DomainError) as invalid_key:
            await service.invoke(service.send_key, "session-1", "invented")
        self.assertEqual(invalid_key.exception.code, "INVALID_KEY")
        self.assertEqual(backend.sent, [])
        self.assertEqual(backend.events.count("history"), 0)


if __name__ == "__main__":
    unittest.main()
