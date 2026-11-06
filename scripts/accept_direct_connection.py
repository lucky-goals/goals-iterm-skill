#!/usr/bin/env python3
"""Bounded, read-only direct iTerm connection acceptance spike.

The parent process launches one fresh Python process per cycle. Runtime mode
uses the prepared ``DirectItermBackend``; SDK mode retains the earlier direct
SDK baseline. Only counts, timings, and hashes of exact identity tuples are
written to the acceptance artifact. The runtime catalogue may observe titles
and shell metadata in memory, but this script never persists them or terminal
contents.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "docs" / "direct-connection-acceptance.json"
DEFAULT_CYCLES = 20
DEFAULT_OPERATION_TIMEOUT_SECONDS = 10.0
DEFAULT_CYCLE_TIMEOUT_SECONDS = 15.0
REQUIRED_RUNTIME_PYTHON = Path(
    "/Users/jwyuan/.local/share/goals-iterm-skill/runtimes/"
    "0.4.0.dev0-1575ad00cd7b8730/bin/python"
)
RUNTIME_CLOSE_TIMEOUT_SECONDS = 2.0


def _fingerprint(rows: list[tuple[str, str, str]], *, sessions_only: bool) -> str:
    if sessions_only:
        identities: list[Any] = sorted({session_id for _window, _tab, session_id in rows})
    else:
        identities = sorted(set(rows), key=lambda row: json.dumps(row, ensure_ascii=True))
    canonical = json.dumps(identities, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _run_sdk_worker(operation_timeout_seconds: float) -> dict[str, Any]:
    """Perform one SDK-owned connect/list/disconnect cycle."""
    import iterm2

    sdk_started = time.perf_counter()
    phase: dict[str, Any] = {"connected_at": None, "operation_started_at": None,
                             "operation_ended_at": None, "rows": [], "error": None}
    connection = iterm2.Connection()

    async def read_catalogue(conn: Any) -> None:
        phase["connected_at"] = time.perf_counter()
        phase["operation_started_at"] = time.perf_counter()

        async def get_catalogue() -> None:
            app = await iterm2.async_get_app(conn)
            if app is None:
                raise RuntimeError("app_unavailable")
            rows: list[tuple[str, str, str]] = []
            for window in app.windows:
                window_id = window.window_id
                for tab in window.tabs:
                    tab_id = tab.tab_id
                    for session in tab.sessions:
                        session_id = session.session_id
                        if not all(isinstance(value, str) and value for value in
                                   (window_id, tab_id, session_id)):
                            raise RuntimeError("catalogue_identity_missing")
                        rows.append((window_id, tab_id, session_id))
            phase["rows"] = rows

        try:
            await asyncio.wait_for(get_catalogue(), timeout=operation_timeout_seconds)
        except asyncio.TimeoutError:
            phase["error"] = "operation_timeout"
        except BaseException as exc:  # Record the class only; never raw SDK text.
            phase["error"] = type(exc).__name__
        finally:
            phase["operation_ended_at"] = time.perf_counter()

    sdk_error: str | None = None
    try:
        connection.run_until_complete(read_catalogue, retry=False)
    except BaseException as exc:  # Authentication/connect errors remain sanitized.
        sdk_error = type(exc).__name__

    sdk_returned = time.perf_counter()
    loop_cleanup = _close_owned_loop(connection)
    socket_check = _open_tcp_socket_count(os.getpid())
    child_count = _direct_child_count(os.getpid())

    connected_at = phase["connected_at"]
    operation_started_at = phase["operation_started_at"]
    operation_ended_at = phase["operation_ended_at"]
    connected = connected_at is not None
    complete = connected and operation_ended_at is not None and sdk_error is None and phase["error"] is None

    rows = phase["rows"] if isinstance(phase["rows"], list) else []
    identities = sorted({row[2] for row in rows})
    return {
        "status": "ok" if complete else "error",
        "error_class": phase["error"] or sdk_error,
        "connect_seconds": round(float(connected_at - sdk_started), 6) if connected else None,
        "operation_seconds": round(float(operation_ended_at - operation_started_at), 6)
        if operation_started_at is not None and operation_ended_at is not None else None,
        "disconnect_seconds": round(float(sdk_returned - operation_ended_at), 6)
        if operation_ended_at is not None else None,
        "session_count": len(identities),
        "duplicate_session_id_count": len(rows) - len(identities),
        "session_ids_sha256": _fingerprint(rows, sessions_only=True) if complete else None,
        "topology_sha256": _fingerprint(rows, sessions_only=False) if complete else None,
        "websocket_closed_after_sdk_return": _websocket_closed(connection),
        "pending_sdk_tasks_after_cleanup": loop_cleanup["pending_after"],
        "sdk_loop_closed": loop_cleanup["closed"],
        "open_tcp_socket_count_after_disconnect": socket_check,
        "direct_helper_child_count_after_disconnect": child_count,
    }


def _run_runtime_backend_worker(operation_timeout_seconds: float) -> dict[str, Any]:
    """Run one cycle through the prepared DirectItermBackend runtime."""
    from goals_iterm.service import DirectItermBackend

    phase: dict[str, Any] = {
        "connect_started_at": None,
        "connected_at": None,
        "operation_started_at": None,
        "operation_ended_at": None,
        "disconnect_started_at": None,
        "disconnected_at": None,
        "rows": [],
        "session_epoch_sha256": None,
        "broker_epoch_sha256": None,
        "error": None,
        "connect_error": None,
        "close_timed_out": None,
        "close_pending_task_count": None,
        "close_done_task_count": None,
        "backend_connection_released": False,
        "pending_tasks_after_backend_close": None,
        "websocket_closed_after_backend_close": None,
    }
    broker_epoch = uuid4().hex
    backend = DirectItermBackend(broker_epoch=broker_epoch)
    phase["broker_epoch_sha256"] = hashlib.sha256(broker_epoch.encode("utf-8")).hexdigest()

    async def one_cycle() -> None:
        phase["connect_started_at"] = time.perf_counter()
        try:
            await asyncio.wait_for(backend.connect(), timeout=operation_timeout_seconds)
            phase["connected_at"] = time.perf_counter()
        except asyncio.TimeoutError:
            phase["connect_error"] = "connect_timeout"
            phase["error"] = "connect_timeout"
        except BaseException as exc:
            phase["connect_error"] = type(exc).__name__
            phase["error"] = type(exc).__name__

        connection = backend._connection
        if phase["connected_at"] is not None:
            phase["operation_started_at"] = time.perf_counter()
            try:
                rows = await asyncio.wait_for(
                    backend.list_sessions(), timeout=operation_timeout_seconds
                )
                identities: list[tuple[str, str, str]] = []
                epochs: list[tuple[str, str]] = []
                for row in rows:
                    target = row.get("target") if isinstance(row, dict) else None
                    session_id = target.get("session_id") if isinstance(target, dict) else None
                    session_epoch = target.get("session_epoch") if isinstance(target, dict) else None
                    window_id = row.get("window_id")
                    tab_id = row.get("tab_id")
                    if not isinstance(session_id, str) or not session_id:
                        raise RuntimeError("catalogue_session_identity_missing")
                    if not isinstance(session_epoch, str) or not session_epoch:
                        raise RuntimeError("catalogue_session_epoch_missing")
                    identities.append((window_id, tab_id, session_id))
                    epochs.append((session_id, session_epoch))
                phase["rows"] = identities
                phase["session_epoch_sha256"] = _canonical_hash(sorted(epochs))
            except asyncio.TimeoutError:
                phase["error"] = "catalogue_timeout"
            except BaseException as exc:
                phase["error"] = type(exc).__name__
            finally:
                phase["operation_ended_at"] = time.perf_counter()

        phase["disconnect_started_at"] = time.perf_counter()
        try:
            close_result = await backend.close(timeout=RUNTIME_CLOSE_TIMEOUT_SECONDS)
            if close_result is not None:
                phase["close_timed_out"] = close_result.timed_out
                phase["close_pending_task_count"] = len(close_result.pending)
                phase["close_done_task_count"] = len(close_result.done)
                if close_result.timed_out or close_result.pending:
                    phase["error"] = phase["error"] or "bounded_close_timeout"
        except BaseException as exc:
            phase["error"] = phase["error"] or type(exc).__name__
        finally:
            phase["disconnected_at"] = time.perf_counter()
            phase["backend_connection_released"] = backend._connection is None
            current = asyncio.current_task()
            phase["pending_tasks_after_backend_close"] = len([
                task for task in asyncio.all_tasks()
                if task is not current and not task.done()
            ])
            phase["websocket_closed_after_backend_close"] = _websocket_closed(connection)

    runner = asyncio.Runner()
    loop = runner.get_loop()
    try:
        runner.run(one_cycle())
    except BaseException as exc:
        phase["error"] = phase["error"] or type(exc).__name__
    finally:
        try:
            runner.close()
        except BaseException as exc:
            phase["error"] = phase["error"] or type(exc).__name__

    socket_check = _open_tcp_socket_count(os.getpid())
    child_count = _direct_child_count(os.getpid())
    rows = phase["rows"] if isinstance(phase["rows"], list) else []
    identities = sorted({row[2] for row in rows})
    complete = (
        phase["connected_at"] is not None
        and phase["operation_ended_at"] is not None
        and phase["disconnected_at"] is not None
        and phase["error"] is None
    )
    return {
        "status": "ok" if complete else "error",
        "error_class": phase["error"],
        "connect_error_class": phase["connect_error"],
        "connect_seconds": _elapsed(phase["connect_started_at"], phase["connected_at"]),
        "operation_seconds": _elapsed(phase["operation_started_at"], phase["operation_ended_at"]),
        "disconnect_seconds": _elapsed(phase["disconnect_started_at"], phase["disconnected_at"]),
        "session_count": len(identities),
        "duplicate_session_id_count": len(rows) - len(identities),
        "session_ids_sha256": _fingerprint(rows, sessions_only=True) if complete else None,
        "topology_sha256": _fingerprint(rows, sessions_only=False) if complete else None,
        "session_epoch_sha256": phase["session_epoch_sha256"] if complete else None,
        "broker_epoch_sha256": phase["broker_epoch_sha256"],
        "websocket_closed_after_sdk_return": phase["websocket_closed_after_backend_close"],
        "pending_sdk_tasks_after_cleanup": phase["pending_tasks_after_backend_close"],
        "sdk_loop_closed": loop.is_closed(),
        "open_tcp_socket_count_after_disconnect": socket_check,
        "direct_helper_child_count_after_disconnect": child_count,
        "backend_connection_released": phase["backend_connection_released"],
        "bounded_close_timed_out": phase["close_timed_out"],
        "bounded_close_pending_task_count": phase["close_pending_task_count"],
        "bounded_close_completed_task_count": phase["close_done_task_count"],
    }


def _canonical_hash(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _elapsed(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    return round(float(end - start), 6)


def _websocket_closed(connection: Any) -> bool | None:
    websocket = getattr(connection, "websocket", None)
    if websocket is None:
        return None
    closed = getattr(websocket, "closed", None)
    if isinstance(closed, bool):
        return closed
    state = getattr(websocket, "state", None)
    state_name = getattr(state, "name", None)
    if isinstance(state_name, str):
        return state_name.casefold() == "closed"
    return None


def _close_owned_loop(connection: Any) -> dict[str, Any]:
    """Drain the cancelled SDK dispatcher and close its per-worker event loop."""
    loop = getattr(connection, "loop", None)
    if loop is None or loop.is_closed():
        return {"pending_after": None, "closed": bool(loop and loop.is_closed())}
    try:
        pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            async def drain() -> None:
                await asyncio.gather(*pending, return_exceptions=True)

            loop.run_until_complete(asyncio.wait_for(drain(), timeout=2.0))
        pending_after = len([task for task in asyncio.all_tasks(loop) if not task.done()])
    except BaseException:
        pending_after = -1
    try:
        loop.close()
    except BaseException:
        return {"pending_after": pending_after, "closed": False}
    return {"pending_after": pending_after, "closed": loop.is_closed()}


def _open_tcp_socket_count(pid: int) -> int | None:
    try:
        result = subprocess.run(
            ["lsof", "-nP", "-a", "-p", str(pid), "-iTCP"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return max(0, len(lines) - 1) if lines and lines[0].startswith("COMMAND") else len(lines)


def _direct_child_count(pid: int) -> int | None:
    probe: subprocess.Popen[str] | None = None
    try:
        probe = subprocess.Popen(
            ["ps", "-Ao", "pid=,ppid=,comm="],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, _stderr = probe.communicate(timeout=2.0)
    except (OSError, subprocess.TimeoutExpired):
        if probe is not None:
            probe.kill()
            probe.communicate()
        return None
    children = 0
    for line in stdout.splitlines():
        fields = line.split(None, 2)
        if len(fields) >= 2:
            try:
                child_pid, parent_pid = int(fields[0]), int(fields[1])
                if parent_pid == pid and child_pid != probe.pid:
                    children += 1
            except ValueError:
                continue
    return children


def _worker_main(args: argparse.Namespace) -> int:
    try:
        if args.mode == "runtime-backend":
            result = _run_runtime_backend_worker(args.operation_timeout_seconds)
        else:
            result = _run_sdk_worker(args.operation_timeout_seconds)
    except BaseException as exc:
        result = {"status": "error", "error_class": type(exc).__name__}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("status") == "ok" else 1


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * percentile + 0.5)))
    return round(ordered[index], 6)


def _summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "median": None, "p95_nearest_rank": None, "max": None}
    return {
        "min": round(min(values), 6),
        "median": round(statistics.median(values), 6),
        "p95_nearest_rank": _percentile(values, 0.95),
        "max": round(max(values), 6),
    }


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _dependency_metadata(mode: str) -> dict[str, Any]:
    installed = sorted(
        f"{distribution.metadata.get('Name', 'unknown')}=={distribution.version}"
        for distribution in importlib.metadata.distributions()
    )
    if mode != "runtime-backend":
        return {
            "runtime_source": "upstream cc-iterm-mcp .venv",
            "runtime_interpreter": sys.executable,
            "installed_distributions": installed,
        }

    lock_path = ROOT / "runtime" / "requirements.lock"
    lock_sha256 = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    pyvenv_path = Path(sys.prefix) / "pyvenv.cfg"
    pyvenv_cfg = {}
    if pyvenv_path.exists():
        for line in pyvenv_path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                pyvenv_cfg[key.strip()] = value.strip()
    return {
        "runtime_source": "prepared 0.4.0.dev0 runtime",
        "runtime_interpreter": sys.executable,
        "runtime_prefix": sys.prefix,
        "runtime_base_prefix": sys.base_prefix,
        "runtime_virtual_environment": pyvenv_cfg,
        "requirements_lock": "runtime/requirements.lock",
        "requirements_lock_sha256": lock_sha256,
        "locked_dependencies": {
            name: _distribution_version(name)
            for name in ("iterm2", "protobuf", "websockets")
        },
        "installed_distributions": installed,
        "mcp_distribution_installed": any(
            distribution.split("==", 1)[0].casefold() == "mcp"
            for distribution in installed
        ),
    }


def _previous_upstream_baseline() -> dict[str, Any] | None:
    if not OUTPUT_PATH.exists():
        return None
    try:
        previous = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    saved = previous.get("previous_upstream_sdk_baseline")
    if isinstance(saved, dict):
        return saved
    if previous.get("environment", {}).get("runtime_source") != "upstream cc-iterm-mcp .venv":
        return None
    return {
        "description": "Earlier SDK-direct baseline before the prepared runtime backend run.",
        "environment": previous.get("environment"),
        "cycles_completed": previous.get("method", {}).get("cycles_completed"),
        "timings_seconds": previous.get("timings_seconds"),
        "identity": {
            key: previous.get("identity", {}).get(key)
            for key in (
                "stable_session_id_hash_across_reconnects",
                "stable_topology_hash_across_reconnects",
                "session_ids_sha256",
                "topology_sha256",
                "distinct_session_counts",
                "guarantee_assessment",
            )
        },
        "leaks": previous.get("leaks"),
    }


def _write_acceptance(
    cycles: int, operation_timeout: float, cycle_timeout: float, mode: str
) -> dict[str, Any]:
    python = Path(sys.executable)
    if mode == "runtime-backend" and python != REQUIRED_RUNTIME_PYTHON:
        raise RuntimeError(
            "runtime-backend mode must be launched with "
            f"{REQUIRED_RUNTIME_PYTHON} (got {python})"
        )
    child_env = os.environ.copy()
    if mode == "runtime-backend":
        runtime_pythonpath = str(ROOT / "runtime")
        existing_pythonpath = child_env.get("PYTHONPATH")
        child_env["PYTHONPATH"] = (
            runtime_pythonpath + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
        )
    upstream_baseline = _previous_upstream_baseline()
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    session_epoch_hashes: list[str] = []
    broker_epoch_hashes: list[str] = []
    for number in range(1, cycles + 1):
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                [str(python), str(Path(__file__).resolve()), "--worker",
                 "--mode", mode,
                 "--operation-timeout-seconds", str(operation_timeout)],
                capture_output=True,
                text=True,
                timeout=cycle_timeout,
                check=False,
                env=child_env,
            )
            wall = round(time.perf_counter() - started, 6)
        except subprocess.TimeoutExpired:
            wall = round(time.perf_counter() - started, 6)
            rows.append({"cycle": number, "status": "timeout", "worker_wall_seconds": wall,
                         "error_class": "cycle_wall_timeout", "worker_exit_code": None,
                         "session_count": None, "session_ids_sha256": None,
                         "topology_sha256": None})
            failures.append("cycle_wall_timeout")
            break

        worker_result = _parse_worker_output(completed.stdout)
        if worker_result is None:
            worker_result = {"status": "error", "error_class": "worker_output_invalid"}
        session_epoch_hash = worker_result.pop("session_epoch_sha256", None)
        broker_epoch_hash = worker_result.pop("broker_epoch_sha256", None)
        if isinstance(session_epoch_hash, str):
            session_epoch_hashes.append(session_epoch_hash)
        if isinstance(broker_epoch_hash, str):
            broker_epoch_hashes.append(broker_epoch_hash)
        row = {"cycle": number, **worker_result,
               "worker_wall_seconds": wall,
               "worker_exit_code": completed.returncode}
        rows.append(row)
        if completed.returncode != 0 or worker_result.get("status") != "ok":
            failures.append(str(worker_result.get("error_class") or "worker_failed"))
            break

    successful = [row for row in rows if row.get("status") == "ok"]
    identity_hashes = [row.get("session_ids_sha256") for row in successful]
    topology_hashes = [row.get("topology_sha256") for row in successful]
    identity_stable = len(identity_hashes) == cycles and len(set(identity_hashes)) == 1
    topology_stable = len(topology_hashes) == cycles and len(set(topology_hashes)) == 1
    cleanup_ok = len(successful) == cycles and all(
        row.get("websocket_closed_after_sdk_return") is True
        and row.get("pending_sdk_tasks_after_cleanup") == 0
        and row.get("sdk_loop_closed") is True
        and row.get("open_tcp_socket_count_after_disconnect") == 0
        and row.get("direct_helper_child_count_after_disconnect") == 0
        and (
            mode != "runtime-backend"
            or (
                row.get("backend_connection_released") is True
                and row.get("bounded_close_timed_out") is False
                and row.get("bounded_close_pending_task_count") == 0
            )
        )
        and row.get("worker_exit_code") == 0
        for row in successful
    )
    session_epochs_changed = (
        len(session_epoch_hashes) == cycles and len(set(session_epoch_hashes)) == cycles
        if mode == "runtime-backend" else None
    )
    broker_epochs_changed = (
        len(broker_epoch_hashes) == cycles and len(set(broker_epoch_hashes)) == cycles
        if mode == "runtime-backend" else None
    )
    epoch_lifecycle_ok = (
        mode != "runtime-backend" or (session_epochs_changed and broker_epochs_changed)
    )

    def timings(key: str) -> list[float]:
        return [float(row[key]) for row in successful if isinstance(row.get(key), (int, float))]

    app_version = _read_iterm_app_version()
    sdk_version = _distribution_version("iterm2")
    dependency_metadata = _dependency_metadata(mode)

    acceptance: dict[str, Any] = {
        "schema_version": 1,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "result": "passed" if len(successful) == cycles and not failures
        and identity_stable and topology_stable and cleanup_ok and epoch_lifecycle_ok
        else "blocked_or_failed",
        "environment": {
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "sdk": "iterm2",
            "sdk_version": sdk_version,
            "iterm_app_version": app_version,
            **dependency_metadata,
        },
        "method": {
            "cycles_requested": cycles,
            "cycles_completed": len(successful),
            "process_isolated_one_shot": True,
            "retry": False,
            "cycle_wall_timeout_seconds": cycle_timeout,
            "catalogue_operation_timeout_seconds": operation_timeout,
            "operations": ["connect", "read-only session catalogue", "disconnect"],
            "session_titles_or_bodies_persisted": False,
            "runtime_list_sessions_reads_titles_in_memory": mode == "runtime-backend",
            "screen_or_history_read": False,
            "terminal_input_sent": False,
            "terminal_created_or_closed": False,
            "terminal_session_closed": False,
            "runtime_bounded_close_timeout_seconds": (
                RUNTIME_CLOSE_TIMEOUT_SECONDS if mode == "runtime-backend" else None
            ),
            "authorization_observation": (
                f"No consent-related wait or error was observed across {len(successful)} completed cycles; "
                "no UI was manipulated."
            ),
            "raw_session_ids_persisted": False,
            "session_id_hash": "sha256(sorted exact session_id values)",
            "topology_hash": "sha256(sorted exact window_id/tab_id/session_id tuples)",
            "runtime_connect_timeout_seconds": (
                operation_timeout if mode == "runtime-backend" else None
            ),
            "connection_path": (
                "goals_iterm.service.DirectItermBackend.connect() with bounded_sdk_authentication"
                if mode == "runtime-backend" else "iterm2.Connection.run_until_complete(coro, retry=False)"
            ),
            "catalogue_path": (
                "goals_iterm.service.DirectItermBackend.list_sessions()"
                if mode == "runtime-backend" else "iterm2.async_get_app() and SDK topology"
            ),
            "disconnect_path": (
                "ItermBackend.close(timeout=2.0); closes only the API connection"
                if mode == "runtime-backend" else "SDK websocket context exit and per-worker loop close"
            ),
            "event_loop_lifecycle": "asyncio.Runner, one per worker process"
            if mode == "runtime-backend" else "SDK run_until_complete plus explicit per-worker loop close",
        },
        "timings_seconds": {
            "connect": _summary(timings("connect_seconds")),
            "catalogue_operation": _summary(timings("operation_seconds")),
            "disconnect": _summary(timings("disconnect_seconds")),
            "worker_wall": _summary(timings("worker_wall_seconds")),
        },
        "identity": {
            "stable_session_id_hash_across_reconnects": identity_stable,
            "stable_topology_hash_across_reconnects": topology_stable,
            "session_epoch_fingerprint_changed_each_process": session_epochs_changed,
            "broker_epoch_fingerprint_changed_each_process": broker_epochs_changed,
            "distinct_session_counts": sorted({row["session_count"] for row in successful}),
            "duplicate_session_id_counts": sorted({row["duplicate_session_id_count"] for row in successful}),
            "session_ids_sha256": identity_hashes[-1] if identity_hashes else None,
            "topology_sha256": topology_hashes[-1] if topology_hashes else None,
            "guarantee_assessment": (
                "Stable across the observed one-shot reconnects on this running iTerm instance. "
                "Insufficient alone as a durable stale-target guarantee: app restart/session replacement "
                "was not exercised. Runtime epochs are process-local and changed across worker processes. Keep exact IDs plus "
                "ownership generation, current membership, and available process-start/TTY evidence; "
                "treat epochs as historical and revalidate immediately before every action."
            ),
        },
        "leaks": {
            "all_cleanup_checks_passed": cleanup_ok,
            "cycles_with_websocket_closed_after_disconnect": sum(
                row.get("websocket_closed_after_sdk_return") is True for row in successful),
            "cycles_with_sdk_loop_closed": sum(row.get("sdk_loop_closed") is True for row in successful),
            "cycles_with_zero_pending_sdk_tasks_after_cleanup": sum(
                row.get("pending_sdk_tasks_after_cleanup") == 0 for row in successful),
            "cycles_with_zero_open_tcp_sockets_after_disconnect": sum(
                row.get("open_tcp_socket_count_after_disconnect") == 0 for row in successful),
            "cycles_with_zero_helper_children_after_disconnect": sum(
                row.get("direct_helper_child_count_after_disconnect") == 0 for row in successful),
            "cycles_with_backend_connection_released": sum(
                row.get("backend_connection_released") is True for row in successful),
            "cycles_with_bounded_close_complete": sum(
                row.get("bounded_close_timed_out") is False
                and row.get("bounded_close_pending_task_count") == 0
                for row in successful),
            "worker_processes_reaped": len(successful) == len(rows),
        },
        "restart_test": {
            "performed": False,
            "limitation": "Live iTerm was not restarted because it contains existing user terminals.",
            "fixture_acceptance_recommendation": (
                "Use an SDK catalogue fixture to test app restart, session replacement, changed container "
                "membership, and normal CLI-to-shell transitions. A changed/reused ID or membership conflict "
                "must be rejected; a verified process transition within the same exact session should not "
                "be treated as takeover. Keep missing birth-identity evidence unknown."
            ),
        },
        "failures": failures,
        "cycles": rows,
        "sources": [
            "https://iterm2.com/python-api/",
            "https://iterm2.com/python-api/connection.html",
            "https://iterm2.com/documentation-preferences-general.html",
        ],
    }
    if upstream_baseline is not None:
        acceptance["previous_upstream_sdk_baseline"] = upstream_baseline
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(acceptance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return acceptance


def _parse_worker_output(stdout: str) -> dict[str, Any] | None:
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _read_iterm_app_version() -> str | None:
    try:
        result = subprocess.run(
            ["/usr/libexec/PlistBuddy", "-c", "Print :CFBundleShortVersionString",
             "/Applications/iTerm.app/Contents/Info.plist"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--mode", choices=("runtime-backend", "sdk-direct"),
                        default="runtime-backend")
    parser.add_argument("--cycles", type=int, default=DEFAULT_CYCLES)
    parser.add_argument("--operation-timeout-seconds", type=float,
                        default=DEFAULT_OPERATION_TIMEOUT_SECONDS)
    parser.add_argument("--cycle-timeout-seconds", type=float,
                        default=DEFAULT_CYCLE_TIMEOUT_SECONDS)
    args = parser.parse_args()
    if args.worker:
        return _worker_main(args)
    if args.cycles < 1 or args.cycles > 100:
        parser.error("--cycles must be between 1 and 100")
    if args.operation_timeout_seconds <= 0 or args.cycle_timeout_seconds <= 0:
        parser.error("timeouts must be positive")
    acceptance = _write_acceptance(
        args.cycles, args.operation_timeout_seconds, args.cycle_timeout_seconds, args.mode
    )
    print(json.dumps({
        "result": acceptance["result"],
        "cycles_completed": acceptance["method"]["cycles_completed"],
        "cycles_requested": args.cycles,
        "acceptance_file": str(OUTPUT_PATH),
        "failure_classes": acceptance["failures"],
    }, sort_keys=True))
    return 0 if acceptance["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
