"""Name allocation and direct iTerm profile persistence tests."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from goals_iterm.backend_types import CaptureDTO
from goals_iterm.backends import ItermBackend
from goals_iterm.errors import DomainError
from goals_iterm.naming import NICKNAME_VARIABLE, NICKNAMES
from goals_iterm.service import DirectItermBackend, ItermTools


def row(session_id: str, name: str | None = None) -> dict:
    target = {
        "session_id": session_id,
        "session_epoch": f"epoch-{session_id}",
        "broker_epoch": "broker",
    }
    result = {
        "target": target,
        "window_id": "window-1",
        "tab_id": "tab-1",
    }
    if name is not None:
        result.update(name=name, title=name)
    return result


class NamedBackend:
    def __init__(self, rows: list[dict], *, fail_rename: bool = False):
        self.rows = rows
        self.connect = AsyncMock()
        self.close = AsyncMock()
        self.fail_rename = fail_rename
        self.rename_calls: list[tuple[str, str]] = []
        self.create_calls: list[tuple[str, str | None, str | None, str | None]] = []

    async def list_sessions(self):
        return [dict(item) for item in self.rows]

    async def rename(self, target, name):
        self.rename_calls.append((target["session_id"], name))
        if self.fail_rename:
            raise RuntimeError("simulated write failure")
        for item in self.rows:
            if item["target"]["session_id"] == target["session_id"]:
                item["name"] = name
                item["title"] = name
                return
        raise RuntimeError("missing target")

    async def create(self, kind, target_id=None, command=None, *, name):
        self.create_calls.append((kind, target_id, command, name))
        return {"session_id": "new", "window_id": "window", "tab_id": "tab"}


class NameServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_name_collision_checks_sessions_outside_allowlist(self):
        backend = NamedBackend([row("owned", "home"), row("other", "amber")])
        service = ItermTools(backend, session_ids=["owned"])

        with self.assertRaises(DomainError) as caught:
            await service.invoke(service.rename_session, "owned", "AMBER")

        self.assertEqual(caught.exception.code, "NICKNAME_IN_USE")
        self.assertEqual(backend.rename_calls, [])

    async def test_catalogue_reads_existing_names_without_writing(self):
        backend = NamedBackend([row("session")])
        before = [dict(item) for item in backend.rows]
        service = ItermTools(backend)

        listed = await service.invoke(service.catalogue)

        self.assertEqual(listed[0]["session_id"], "session")
        self.assertEqual(backend.rows, before)
        self.assertEqual(backend.rename_calls, [])

    async def test_random_renames_are_serialized_and_unique(self):
        backend = NamedBackend([row("session", "home"), row("other", "work")])
        service = ItermTools(backend)

        first, second = await asyncio.gather(
            service.invoke(service.rename_session, "other"),
            service.invoke(service.rename_session, "session"),
        )

        names = {first["name"], second["name"]}
        self.assertEqual(len(names), 2)
        self.assertTrue(names <= set(NICKNAMES))
        self.assertEqual(len(backend.rename_calls), 2)

    async def test_create_refuses_when_nickname_pool_is_exhausted(self):
        backend = NamedBackend(
            [row(f"session-{index}", name) for index, name in enumerate(NICKNAMES)]
        )
        service = ItermTools(backend)

        with self.assertRaises(DomainError) as caught:
            await service.invoke(service.create, "window", None, None)

        self.assertEqual(caught.exception.code, "NICKNAME_POOL_EXHAUSTED")
        self.assertEqual(backend.create_calls, [])

    async def test_create_passes_a_unique_generated_name_to_backend(self):
        backend = NamedBackend([row("external", "acorn")])
        service = ItermTools(backend)

        result = await service.invoke(service.create, "window", None, "/bin/cat")

        self.assertEqual(len(backend.create_calls), 1)
        self.assertEqual(backend.create_calls[0][:3], ("window", None, "/bin/cat"))
        self.assertEqual(backend.create_calls[0][3], result["name"])
        self.assertNotEqual(result["name"], "acorn")

    async def test_rename_failure_is_reported_and_never_retried(self):
        backend = NamedBackend([row("session", "home")], fail_rename=True)
        service = ItermTools(backend)

        with self.assertRaises(DomainError) as caught:
            await service.invoke(service.rename_session, "session", "ember")

        self.assertEqual(caught.exception.code, "ITERM_API_ERROR")
        self.assertEqual(backend.rename_calls, [("session", "ember")])

    async def test_persisted_name_is_visible_to_a_new_service(self):
        backend = NamedBackend([row("session", "home")])
        first_service = ItermTools(backend)

        renamed = await first_service.invoke(
            first_service.rename_session, "session", "ember"
        )
        second_service = ItermTools(backend)
        listed = await second_service.invoke(second_service.catalogue)

        self.assertEqual(renamed["name"], "ember")
        self.assertEqual(listed[0]["name"], "ember")


class FakeProfile:
    def __init__(self):
        self.values = {}

    def set_name(self, value):
        self.values["Name"] = json.dumps(value)

    def set_allow_title_setting(self, value):
        self.values["Allow Title Setting"] = str(value).lower()

    def set_title_components(self, value):
        self.values["Title Components"] = str(value[0])

    def set_use_custom_command(self, value):
        self.values["Use Custom Command"] = str(value)

    def set_command(self, value):
        self.values["Command"] = json.dumps(value)


class DirectBackendNameTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session = SimpleNamespace(
            session_id="created",
            async_set_variable=AsyncMock(),
            async_set_name=AsyncMock(),
            async_set_profile_properties=AsyncMock(),
            async_get_variable=AsyncMock(return_value="ember"),
        )
        self.tab = SimpleNamespace(tab_id="tab", current_session=self.session)
        self.window = SimpleNamespace(window_id="window", current_tab=self.tab)
        self.window.async_create_tab = AsyncMock(return_value=self.tab)
        self.window_factory = SimpleNamespace(async_create=AsyncMock(return_value=self.window))
        self.app = SimpleNamespace(
            terminal_windows=[self.window],
            get_session_by_id=lambda _session_id: self.session,
            async_refresh=AsyncMock(),
        )
        self.backend = DirectItermBackend(
            broker_epoch="broker", connection=object(), app=self.app
        )
        self.backend._iterm2 = SimpleNamespace(
            LocalWriteOnlyProfile=FakeProfile,
            Profile=SimpleNamespace(USE_CUSTOM_COMMAND_ENABLED="Yes"),
            TitleComponents=SimpleNamespace(SESSION_NAME=1),
            Window=self.window_factory,
        )

    async def test_creation_sets_name_and_command_in_one_profile_before_variable(self):
        result = await self.backend.create("window", command="/bin/cat", name="ember")

        profile = self.window_factory.async_create.await_args.kwargs[
            "profile_customizations"
        ]
        self.assertEqual(result["name"], "ember")
        self.assertEqual(profile.values["Name"], '"ember"')
        self.assertEqual(profile.values["Allow Title Setting"], "false")
        self.assertEqual(profile.values["Title Components"], "1")
        self.assertEqual(profile.values["Command"], '"/bin/cat"')
        self.session.async_set_variable.assert_awaited_once_with(
            NICKNAME_VARIABLE, "ember"
        )

    async def test_rename_variable_failure_after_profile_update_is_not_retried(self):
        self.session.async_set_variable.side_effect = RuntimeError("variable failed")

        with self.assertRaises(DomainError) as caught:
            await self.backend._apply_name(self.session, "ember")

        self.assertEqual(caught.exception.code, "NAME_PERSISTENCE_FAILED")
        self.session.async_set_profile_properties.assert_awaited_once()
        self.session.async_set_variable.assert_awaited_once_with(
            NICKNAME_VARIABLE, "ember"
        )

    async def test_catalogue_prefers_persisted_name_without_writing(self):
        target = {
            "session_id": "created",
            "session_epoch": "epoch",
            "broker_epoch": "broker",
        }
        base_rows = [{"target": target, "title": "Shell", "context_summary": None}]
        with patch.object(
            ItermBackend, "list_sessions", new=AsyncMock(return_value=base_rows)
        ):
            rows = await self.backend.list_sessions()

        self.assertEqual(rows[0]["name"], "ember")
        self.session.async_get_variable.assert_awaited_once_with(NICKNAME_VARIABLE)
        self.session.async_set_profile_properties.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
