"""Transport-independent iTerm operations backed by the Python API."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
import importlib
import inspect
from typing import Any
from uuid import uuid4

from .backends import ItermBackend
from .errors import DomainError
from .naming import (
    NICKNAME_VARIABLE,
    choose_nickname,
    ensure_name_available,
    normalize_name,
)


KEYS: dict[str, str] = {
    "enter": "\r",
    "tab": "\t",
    "escape": "\x1b",
    "backspace": "\x7f",
    "up": "\x1b[A",
    "down": "\x1b[B",
    "right": "\x1b[C",
    "left": "\x1b[D",
    "ctrl_c": "\x03",
    "ctrl_d": "\x04",
    "ctrl_u": "\x15",
    "ctrl_l": "\x0c",
}

MAX_INPUT_BYTES = 16 * 1024
MAX_HISTORY_LINES = 2_000
OPERATION_TIMEOUT_SECONDS = 15


class DirectItermBackend(ItermBackend):
    async def connect(self):
        if self.connected or self._connection_factory is not None:
            return await super().connect()
        from .sdk_auth import bounded_sdk_authentication

        with bounded_sdk_authentication():
            return await super().connect()

    """iTerm API backend with native create and naming support."""

    def _sdk(self) -> Any:
        """Load the SDK lazily so fixture-only imports stay lightweight."""

        if self._iterm2 is None:
            self._iterm2 = importlib.import_module("iterm2")
        return self._iterm2

    def _profile_customizations(self, name: str, command: str | None = None) -> Any:
        """Build one write-only profile update for a session name.

        iTerm's create APIs reject ``command`` together with profile
        customizations. Putting command and name in the same profile object
        gives creation one RPC and avoids a create-then-rename window.
        """

        sdk = self._sdk()
        profile_type = getattr(sdk, "LocalWriteOnlyProfile", None)
        if profile_type is None:
            raise DomainError(
                "UNSUPPORTED_CAPABILITY",
                "iTerm profile customizations are unavailable",
            )
        profile = profile_type()
        profile.set_name(name)
        profile.set_allow_title_setting(False)
        title_components = getattr(sdk, "TitleComponents", None)
        profile_name_component = getattr(title_components, "SESSION_NAME", None)
        if profile_name_component is not None:
            profile.set_title_components([profile_name_component])
        if command is not None:
            profile_type_enum = getattr(sdk, "Profile", None)
            enabled = getattr(profile_type_enum, "USE_CUSTOM_COMMAND_ENABLED", "Yes")
            profile.set_use_custom_command(enabled)
            profile.set_command(command)
        return profile

    async def _persist_name_variable(self, session: Any, name: str) -> None:
        method = getattr(session, "async_set_variable", None)
        if method is None:
            raise DomainError(
                "UNSUPPORTED_CAPABILITY",
                "iTerm session variables are unavailable",
            )
        try:
            await method(NICKNAME_VARIABLE, name)
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError(
                "NAME_PERSISTENCE_FAILED",
                "iTerm session nickname variable could not be persisted",
            ) from exc

    async def _apply_name(self, session: Any, name: str) -> None:
        profile_method = getattr(session, "async_set_profile_properties", None)
        if profile_method is None:
            raise DomainError(
                "UNSUPPORTED_CAPABILITY", "iTerm session profile updates are unavailable"
            )
        try:
            await profile_method(self._profile_customizations(name))
            await session.async_set_name(name)
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError(
                "NAME_WRITE_FAILED", "iTerm session name could not be updated"
            ) from exc
        await self._persist_name_variable(session, name)

    async def _nickname_variable(self, session: Any) -> str | None:
        method = getattr(session, "async_get_variable", None)
        if method is None:
            return None
        try:
            value = await method(NICKNAME_VARIABLE)
        except Exception:
            return None
        if not isinstance(value, str):
            return None
        try:
            return normalize_name(value)
        except DomainError:
            return None

    async def list_sessions(self) -> list[dict[str, Any]]:
        """Add the persisted nickname to the base topology catalogue.

        Catalogue reads never assign names or update existing sessions. A
        missing or invalid user variable falls back to iTerm's current title.
        """

        # Title-only changes do not emit layout notifications, so cached
        # Session.name can remain stale after a successful rename.
        await self._app.async_refresh()
        rows = await super().list_sessions()
        get_session = getattr(self._app, "get_session_by_id", None)
        if get_session is None:
            return [dict(row, name=row.get("title")) for row in rows]
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            target = item.get("target")
            session_id = target.get("session_id") if isinstance(target, Mapping) else None
            session = get_session(session_id) if isinstance(session_id, str) else None
            nickname = await self._nickname_variable(session) if session is not None else None
            if nickname is not None:
                item["name"] = nickname
            elif isinstance(item.get("title"), str) and item["title"]:
                item["name"] = item["title"]
            result.append(item)
        return result

    async def rename(self, target: Any, name: str) -> None:
        _target, session = await self._session_for(target)
        await self._apply_name(session, normalize_name(name))

    async def create(
        self,
        kind: str,
        target_id: str | None = None,
        command: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Create through the SDK; never infer a destination from focus."""

        if name is None:
            raise DomainError("INVALID_ARGUMENT", "a session nickname is required")
        name = normalize_name(name)
        profile = self._profile_customizations(name, command)
        if kind == "window":
            window = await self._sdk().Window.async_create(
                self._connection, profile_customizations=profile
            )
            if window is None:
                raise DomainError("CREATE_FAILED", "iTerm window creation failed")
            session = window.current_tab.current_session
            await self._persist_name_variable(session, name)
            return {
                "window_id": window.window_id,
                "tab_id": window.current_tab.tab_id,
                "session_id": session.session_id,
                "name": name,
            }
        if kind == "tab":
            window = next(
                (w for w in self._app.terminal_windows if w.window_id == target_id),
                None,
            )
            if window is None:
                raise DomainError("WINDOW_NOT_FOUND", "the requested iTerm window is unavailable")
            tab = await window.async_create_tab(profile_customizations=profile)
            if tab is None:
                raise DomainError("CREATE_FAILED", "iTerm tab creation failed")
            session = tab.current_session
            await self._persist_name_variable(session, name)
            return {
                "window_id": window.window_id,
                "tab_id": tab.tab_id,
                "session_id": session.session_id,
                "name": name,
            }
        raise DomainError("INVALID_ARGUMENT", "kind must be 'window' or 'tab'")


BeforeWrite = Callable[[], Awaitable[None]]


class ItermTools:
    """Async operation service returning plain Python dictionaries.

    ``before_write`` is an optional integration hook called immediately
    before each service-owned terminal mutation, after the service has
    resolved the fresh target identity. The host can use it to recheck task
    ownership and observation state. The callback receives no terminal input
    text or command body.
    """

    def __init__(
        self,
        backend: Any = None,
        *,
        session_ids: list[str] | None = None,
        closing_backend: Any = None,
        recovery_store: Any = None,
        before_write: BeforeWrite | None = None,
    ) -> None:
        self.backend = (
            backend if backend is not None else DirectItermBackend(broker_epoch=str(uuid4()))
        )
        # An explicitly supplied empty allowlist authorizes no sessions.
        self.allowed = set(session_ids) if session_ids is not None else None
        self.lock = asyncio.Lock()
        self._closing_backend = closing_backend
        self._recovery_store = recovery_store
        self.before_write = before_write

    async def _before_write(self) -> None:
        hook = self.before_write
        if hook is None:
            return
        result = hook()
        if inspect.isawaitable(result):
            await result

    async def _before_close_write(self, _session_ids: list[str]) -> None:
        """Adapt the host boundary hook to ClosingBackend's session-aware API."""

        await self._before_write()

    async def invoke(self, operation: Callable[..., Awaitable[Any]], *args: Any) -> Any:
        """Connect once and serialize one operation; never replay failures."""

        async with self.lock:
            connected = False
            try:
                async with asyncio.timeout(OPERATION_TIMEOUT_SECONDS):
                    await self.backend.connect()
                    connected = True
                    return await operation(*args)
            except DomainError:
                raise
            except TimeoutError as exc:
                code = "ITERM_API_ERROR" if connected else "BACKEND_UNAVAILABLE"
                raise DomainError(
                    code,
                    "iTerm operation timed out; a write outcome may be unknown",
                ) from exc
            except Exception as exc:
                code = "ITERM_API_ERROR" if connected else "BACKEND_UNAVAILABLE"
                raise DomainError(
                    code,
                    "iTerm operation failed; a write outcome may be unknown",
                ) from exc

    async def invoke_close(self, kind: str, **kwargs: Any) -> dict[str, Any]:
        """Run the bounded close service and return its payload dictionary."""

        from .closing import CloseService
        from .closing_backend import ClosingBackend

        async with self.lock:
            operation_name = "clean_all_sessions" if kind == "all" else f"close_{kind}"
            force = kwargs.get("force", False)
            dry_run = kwargs.get("dry_run", False)
            if type(force) is not bool or type(dry_run) is not bool:
                raise DomainError("INVALID_ARGUMENT", "force and dry_run must be booleans")
            try:
                async with asyncio.timeout(OPERATION_TIMEOUT_SECONDS):
                    await self.backend.connect()
            except Exception:
                return {
                    "operation": operation_name,
                    "status": "refused",
                    "code": "BACKEND_UNAVAILABLE",
                    "force": force,
                    "dry_run": dry_run,
                    "target": None,
                    "blocking_sessions": [],
                    "close_attempted": False,
                    "closed_sessions": [],
                    "failed_sessions": [],
                    "unknown_sessions": [],
                    "skipped_sessions": [],
                    "recovery_record_id": None,
                    "recovery_record_path": None,
                }

            adapter = self._closing_backend
            if adapter is None:
                adapter = ClosingBackend(
                    self.backend,
                    allowed=self.allowed,
                    before_write=(self._before_close_write if self.before_write else None),
                )
                self._closing_backend = adapter
            return await CloseService(
                adapter, allowed=self.allowed, store=self._recovery_store
            ).run(kind, **kwargs)

    async def _all_rows(self) -> list[dict[str, Any]]:
        rows = await self.backend.list_sessions()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            target = item.get("target")
            if not isinstance(target, Mapping) or not isinstance(
                target.get("session_id"), str
            ):
                raise DomainError("BACKEND_UNAVAILABLE", "iTerm session target is malformed")
            item["session_id"] = target["session_id"]
            if not isinstance(item.get("name"), str) or not item["name"]:
                for key in ("nickname", "title", "context_summary"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        item["name"] = value
                        break
            if not isinstance(item.get("name"), str) or not item["name"]:
                item["name"] = f"session-{target['session_id'][:8]}"
            result.append(item)
        return result

    async def inspect_sessions(
        self,
        session_id: str | None = None,
        nickname: str | None = None,
    ) -> dict[str, Any]:
        """Return advisory, read-only cleanup evidence for visible sessions."""

        if session_id is not None and nickname is not None:
            raise DomainError("SELECTOR_CONFLICT", "select a session ID or nickname, not both")
        if session_id is not None and not isinstance(session_id, str):
            raise DomainError("INVALID_SELECTOR", "session_id must be a string")
        rows = await self._all_rows()
        visible = [
            row for row in rows if self.allowed is None or row["session_id"] in self.allowed
        ]
        if session_id is not None:
            selected = [await self._target_row(session_id, rows)]
        elif nickname is not None:
            if not isinstance(nickname, str) or not nickname.strip():
                raise DomainError("INVALID_SELECTOR", "nickname must be a non-empty string")
            wanted = nickname.strip().casefold()
            matches = [
                row
                for row in visible
                if isinstance(row.get("name"), str)
                and row["name"].strip().casefold() == wanted
            ]
            if len(matches) > 1:
                raise DomainError("AMBIGUOUS_SELECTOR", "nickname matches multiple sessions")
            if not matches:
                raise DomainError("SESSION_NOT_FOUND", "no visible session matches the nickname")
            selected = matches
        else:
            selected = visible

        from .closing_backend import ClosingBackend

        adapter = self._closing_backend
        if adapter is None:
            adapter = ClosingBackend(self.backend, allowed=self.allowed)
            self._closing_backend = adapter
        probe_method = getattr(adapter, "probe", None)
        diagnostics: list[dict[str, Any]] = []
        for row in selected:
            if not callable(probe_method):
                probe = {
                    "state": "unknown",
                    "reason": "probe_unavailable",
                    "identity": None,
                    "cli_sessions": [],
                    "blocked_code": "PROBE_UNAVAILABLE",
                }
                detail = ClosingBackend.diagnostic(row, probe)
                detail["probe_error"] = "PROBE_UNAVAILABLE"
                diagnostics.append(detail)
                continue
            try:
                value = probe_method(row)
                probe = await value if inspect.isawaitable(value) else value
            except asyncio.CancelledError:
                raise
            except Exception:
                # Do not expose adapter exceptions, paths, argv or terminal
                # content through this advisory inspection operation.
                probe = {
                    "state": "unknown",
                    "reason": "probe_unavailable",
                    "identity": None,
                    "cli_sessions": [],
                    "blocked_code": "PROBE_UNAVAILABLE",
                }
                detail = ClosingBackend.diagnostic(row, probe)
                detail["probe_error"] = "PROBE_UNAVAILABLE"
                diagnostics.append(detail)
                continue
            diagnostics.append(ClosingBackend.diagnostic(row, probe))
        return {
            "sessions": diagnostics,
            "observation": (
                "Advisory read-only evidence only; it is not authorization, "
                "business completion, or a close/exit commitment. Re-probe "
                "immediately before any lifecycle write."
            ),
        }

    async def catalogue(self) -> list[dict[str, Any]]:
        rows = await self._all_rows()
        return [
            row for row in rows if self.allowed is None or row["session_id"] in self.allowed
        ]

    @staticmethod
    def _row_names(row: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for key in ("name", "nickname", "title"):
            value = row.get(key)
            if isinstance(value, str) and value:
                values.append(value)
        return values

    async def _target_row(
        self, session_id: str, rows: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not isinstance(session_id, str) or not session_id or session_id in {"active", "all"}:
            raise DomainError(
                "INVALID_SELECTOR",
                "use an exact session_id returned by list_sessions",
            )
        if self.allowed is not None and session_id not in self.allowed:
            raise DomainError("SESSION_NOT_ALLOWED", "session is outside the configured allowlist")
        for row in rows:
            if row["session_id"] == session_id:
                return row
        raise DomainError("SESSION_NOT_FOUND", "session does not exist")

    async def target(self, session_id: str) -> Mapping[str, str]:
        row = await self._target_row(session_id, await self._all_rows())
        return row["target"]

    async def screen(self, session_id: str) -> dict[str, Any]:
        result = await self.backend.capture(await self.target(session_id))
        return {
            "session_id": session_id,
            "screen": dict(result.screen),
            "captured_at": result.captured_at,
            "truncated": result.truncated,
        }

    async def history(self, session_id: str, lines: int = 100) -> dict[str, Any]:
        if isinstance(lines, bool) or not isinstance(lines, int) or not 1 <= lines <= MAX_HISTORY_LINES:
            raise DomainError("INVALID_ARGUMENT", "lines must be between 1 and 2000")
        result = await self.backend.history(await self.target(session_id), lines)
        return {
            "session_id": session_id,
            "lines": [
                {"position": line.position, "text": line.text, "wrapped": line.wrapped}
                for line in result.history_lines
            ],
            "source_bounds": result.history_source_bounds,
            "truncated": result.truncated,
        }

    @staticmethod
    def _validate_text(text: str, *, label: str = "text") -> None:
        if not isinstance(text, str):
            raise DomainError("INVALID_ARGUMENT", f"{label} must be a string")
        try:
            byte_count = len(text.encode("utf-8", errors="strict"))
        except UnicodeEncodeError as exc:
            raise DomainError("INVALID_ARGUMENT", f"{label} is not valid Unicode") from exc
        if not 1 <= byte_count <= MAX_INPUT_BYTES:
            raise DomainError(
                "INVALID_ARGUMENT", f"{label} must contain 1 to 16384 UTF-8 bytes"
            )

    async def send(self, session_id: str, text: str) -> dict[str, Any]:
        self._validate_text(text)
        target = await self.target(session_id)
        await self._before_write()
        await self.backend.send(target, text)
        return {
            "session_id": session_id,
            "api_acknowledged": True,
            "task_completion": "unknown",
        }

    async def send_key(self, session_id: str, key: str) -> dict[str, Any]:
        if not isinstance(key, str) or key not in KEYS:
            raise DomainError("INVALID_KEY", "key is not in the supported key set")
        target = await self.target(session_id)
        await self._before_write()
        await self.backend.send(target, KEYS[key])
        return {
            "session_id": session_id,
            "api_acknowledged": True,
            "task_completion": "unknown",
        }

    async def rename_session(self, session_id: str, name: str | None = None) -> dict[str, Any]:
        """Rename an allowed session or allocate one unused catalogue name."""

        rows = await self._all_rows()
        target_row = await self._target_row(session_id, rows)
        occupied = [
            value
            for row in rows
            if row["session_id"] != session_id
            for value in self._row_names(row)
        ]
        selected = choose_nickname(occupied) if name is None else ensure_name_available(name, occupied)
        rename = getattr(self.backend, "rename", None)
        if rename is None:
            raise DomainError("UNSUPPORTED_CAPABILITY", "iTerm session naming is unavailable")
        await self._before_write()
        await rename(target_row["target"], selected)
        return {
            "session_id": session_id,
            "name": selected,
            "api_acknowledged": True,
            "task_completion": "unknown",
        }

    async def _create_backend(
        self, kind: str, target_id: str | None, command: str | None, name: str
    ) -> dict[str, Any]:
        result = await self.backend.create(kind, target_id, command, name=name)
        if not isinstance(result, dict):
            raise DomainError("BACKEND_UNAVAILABLE", "iTerm creation result is malformed")
        result = dict(result)
        result["name"] = name
        return result

    async def create(
        self, kind: str, target_id: str | None = None, command: str | None = None
    ) -> dict[str, Any]:
        # A restricted launch controls only its listed sessions. Creating a
        # new window/tab would broaden that operator-supplied access scope.
        if self.allowed is not None:
            raise DomainError(
                "CREATION_DISABLED_WITH_SESSION_ALLOWLIST",
                "creation is disabled when a session allowlist is configured",
            )
        if kind not in {"window", "tab"}:
            raise DomainError("INVALID_ARGUMENT", "kind must be 'window' or 'tab'")
        if command is not None:
            self._validate_text(command, label="command")
        rows = await self._all_rows()
        if kind == "tab":
            if not isinstance(target_id, str) or not target_id:
                raise DomainError("INVALID_ARGUMENT", "window_id must be a non-empty string")
            if not any(row.get("window_id") == target_id for row in rows):
                raise DomainError("WINDOW_NOT_FOUND", "window_id is not in the current catalogue")
        occupied = [value for row in rows for value in self._row_names(row)]
        name = choose_nickname(occupied)
        await self._before_write()
        return await self._create_backend(kind, target_id, command, name)

    async def close(self, timeout: float | None = 2.0) -> Any:
        """Close the service-owned iTerm API connection, never a session."""

        return await self.backend.close(timeout=timeout)


__all__ = [
    "DirectItermBackend",
    "ItermTools",
    "KEYS",
    "MAX_HISTORY_LINES",
    "MAX_INPUT_BYTES",
    "OPERATION_TIMEOUT_SECONDS",
]
