"""Read-only readiness and capability diagnostics for the local runtime."""
from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import signal
import stat
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_PACKAGES = {"iterm2", "protobuf", "websockets"}
FORBIDDEN_PACKAGES = ("mcp", "fastmcp", "pydantic")
RUNTIME_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = RUNTIME_DIR.parent


def _version_from_project() -> str | None:
    current_section: str | None = None
    try:
        lines = (RUNTIME_DIR / "pyproject.toml").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        match = re.fullmatch(r"\s*\[([^]]+)\]\s*", line)
        if match:
            current_section = match.group(1)
            continue
        if current_section == "project":
            match = re.fullmatch(r'\s*version\s*=\s*"([^"]+)"\s*', line)
            if match:
                return match.group(1)
    return None


def _lock_info() -> tuple[str | None, dict[str, str], bool]:
    path = RUNTIME_DIR / "requirements.lock"
    try:
        content = path.read_bytes()
        text = content.decode("utf-8")
    except (OSError, UnicodeError):
        return None, {}, False
    packages: dict[str, str] = {}
    blocks = re.split(r"(?m)^(?=\S+==)", text)
    locked = True
    for block in blocks:
        match = re.match(r"^(\S+)==([^\s\\]+)", block)
        if not match:
            if block.strip():
                locked = False
            continue
        name = match.group(1).lower().replace("_", "-")
        packages[name] = match.group(2)
        if "--hash=sha256:" not in block:
            locked = False
    if set(packages) != EXPECTED_PACKAGES or packages.get("iterm2") != "2.30":
        locked = False
    return hashlib.sha256(content).hexdigest(), packages, locked


def _user_paths() -> dict[str, Path]:
    home = Path.home()
    data_home_raw = os.environ.get("XDG_DATA_HOME")
    state_home_raw = os.environ.get("XDG_STATE_HOME")
    data_home = Path(data_home_raw).expanduser() if data_home_raw else home / ".local/share"
    state_home = Path(state_home_raw).expanduser() if state_home_raw else home / ".local/state"
    if not data_home.is_absolute():
        data_home = home / ".local/share"
    if not state_home.is_absolute():
        state_home = home / ".local/state"
    # Resolve the configured base so symlinked XDG homes produce stable paths.
    data_root = data_home.resolve() / "goals-iterm-skill"
    state_root = state_home.resolve() / "goals-iterm-skill"
    return {
        "data_root": data_root,
        "runtimes": data_root / "runtimes",
        "state_root": state_root,
        "manifest": state_root / "runtime.json",
        "operations": state_root / "operations",
        "recovery": state_root / "recovery",
    }


def _add_check(
    checks: list[dict[str, Any]],
    check_id: str,
    status: str,
    summary: str,
    *,
    observed: Any = None,
    remediation: str | None = None,
    capabilities: list[str] | None = None,
) -> None:
    entry: dict[str, Any] = {"id": check_id, "status": status, "summary": summary}
    if observed is not None:
        entry["observed"] = observed
    if remediation:
        entry["remediation"] = remediation
    if capabilities:
        entry["capabilities"] = capabilities
    checks.append(entry)


def _run(command: list[str], *, timeout: float = 3.0) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _application_paths() -> list[Path]:
    candidates = [Path("/Applications/iTerm.app"), Path.home() / "Applications/iTerm.app"]
    mdfind = shutil.which("mdfind")
    if sys.platform == "darwin" and mdfind:
        result = _run([mdfind, 'kMDItemCFBundleIdentifier == "com.googlecode.iterm2"'], timeout=3.0)
        if result and result.returncode == 0:
            candidates.extend(Path(line.strip()) for line in result.stdout.splitlines() if line.strip().endswith(".app"))
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.expanduser())
        if key not in seen:
            seen.add(key)
            unique.append(candidate.expanduser())
    return unique


def _find_iterm() -> tuple[Path | None, str | None]:
    for app in _application_paths():
        info_path = app / "Contents/Info.plist"
        if not info_path.is_file():
            continue
        try:
            with info_path.open("rb") as stream:
                info = plistlib.load(stream)
        except (OSError, plistlib.InvalidFileException):
            continue
        if info.get("CFBundleIdentifier") not in (None, "com.googlecode.iterm2"):
            continue
        version = info.get("CFBundleShortVersionString") or info.get("CFBundleVersion")
        return app, str(version) if version is not None else "unknown"
    return None, None


def _iterm_running() -> bool:
    ps = shutil.which("ps")
    if not ps:
        return False
    result = _run([ps, "-A", "-o", "comm="], timeout=3.0)
    if result is None or result.returncode != 0:
        return False
    for line in result.stdout.splitlines():
        executable = Path(line.strip()).name.lower()
        if executable in {"iterm2", "iterm2-3.5", "iterm2-3.6", "iterm2-3.7"}:
            return True
    return False


def _private_directory_status(path: Path) -> tuple[str, str, dict[str, Any]]:
    try:
        details = path.lstat()
    except FileNotFoundError:
        return "blocked", "Private state directory has not been prepared", {"path": str(path), "exists": False}
    except OSError as exc:
        return "blocked", "Private state directory could not be inspected", {"path": str(path), "error": type(exc).__name__}
    observed = {"path": str(path), "mode": oct(stat.S_IMODE(details.st_mode)), "exists": True}
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
        return "blocked", "Private state path is not a real directory", observed
    if hasattr(os, "getuid") and details.st_uid != os.getuid():
        observed["owned_by_current_user"] = False
        return "blocked", "Private state directory is owned by another user", observed
    observed["owned_by_current_user"] = True
    if stat.S_IMODE(details.st_mode) & 0o077:
        return "blocked", "Private state directory is accessible to group or other users", observed
    return "ok", "Private state directory is user-only", observed


def _manifest_status(
    paths: dict[str, Path], runtime_version: str | None, lock_digest: str | None
) -> tuple[str, str, dict[str, Any], dict[str, Any] | None]:
    manifest_path = paths["manifest"]
    try:
        details = manifest_path.lstat()
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
            return "blocked", "Runtime manifest is not a regular file", {"path": str(manifest_path)}, None
        if hasattr(os, "getuid") and details.st_uid != os.getuid():
            return "blocked", "Runtime manifest is owned by another user", {"path": str(manifest_path)}, None
        if stat.S_IMODE(details.st_mode) & 0o077:
            return "blocked", "Runtime manifest is accessible to group or other users", {
                "path": str(manifest_path), "mode": oct(stat.S_IMODE(details.st_mode))
            }, None
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "blocked", "Prepared runtime manifest is missing", {"path": str(manifest_path), "exists": False}, None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return "blocked", "Prepared runtime manifest is unreadable or corrupt", {
            "path": str(manifest_path), "error": type(exc).__name__
        }, None
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        return "blocked", "Prepared runtime manifest has an unsupported schema", {"path": str(manifest_path)}, None
    if value.get("runtime_version") != runtime_version or value.get("lock_sha256") != lock_digest:
        return "blocked", "Prepared runtime does not match this source and dependency lock", {
            "runtime_version": value.get("runtime_version"), "lock_sha256": value.get("lock_sha256")
        }, value
    expected_environment = paths["runtimes"] / f"{runtime_version}-{(lock_digest or '')[:16]}"
    try:
        environment = Path(str(value.get("environment_path", ""))).expanduser().absolute()
        python_path = Path(str(value.get("python_path", ""))).expanduser().absolute()
    except (TypeError, OSError):
        return "blocked", "Prepared runtime manifest has invalid paths", {}, value
    if environment != expected_environment.absolute() or python_path != (expected_environment / "bin/python").absolute():
        return "blocked", "Prepared runtime manifest points outside the locked runtime", {
            "environment_path": str(environment), "python_path": str(python_path)
        }, value
    if not python_path.is_file() or not os.access(python_path, os.X_OK):
        return "blocked", "Prepared Python interpreter is missing", {"python_path": str(python_path)}, value
    observed = {
        "runtime_version": runtime_version,
        "lock_sha256": lock_digest,
        "environment_path": str(environment),
        "python_path": str(python_path),
        "python_version": value.get("python_version"),
    }
    return "ok", "Prepared runtime manifest matches this source", observed, value


def _dependency_status(expected_packages: dict[str, str], lock_valid: bool) -> tuple[str, str, dict[str, Any]]:
    observed: dict[str, Any] = {"python_version": platform.python_version(), "dependencies": {}}
    if sys.version_info[:2] != (3, 12):
        return "blocked", "The active interpreter is not Python 3.12", observed
    if not lock_valid:
        return "blocked", "Runtime lock is missing, incomplete, or not hash-locked", observed
    actual: dict[str, str] = {}
    missing: list[str] = []
    mismatched: dict[str, dict[str, str | None]] = {}
    for package, expected in expected_packages.items():
        try:
            actual[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            missing.append(package)
            continue
        if actual[package] != expected:
            mismatched[package] = {"expected": expected, "actual": actual[package]}
    forbidden = [name for name in FORBIDDEN_PACKAGES if importlib.util.find_spec(name) is not None]
    observed["dependencies"] = actual
    observed["forbidden_packages"] = forbidden
    if missing:
        observed["missing"] = missing
        return "blocked", "A required runtime dependency is missing", observed
    if mismatched:
        observed["mismatched"] = mismatched
        return "blocked", "Installed dependency versions do not match the lock", observed
    if forbidden:
        return "blocked", "The runtime contains packages reserved for the former MCP service", observed
    try:
        import iterm2  # noqa: F401
    except Exception as exc:
        observed["import_error"] = type(exc).__name__
        return "blocked", "The pinned iTerm2 SDK cannot be imported", observed
    return "ok", "Python 3.12 and the minimal hash-locked SDK dependencies are ready", observed


_LIVE_CHECK_SCRIPT = r'''
import json
import iterm2
from goals_iterm.sdk_auth import bounded_sdk_authentication

async def check(connection):
    app = await iterm2.async_get_app(connection)
    if app is None:
        raise RuntimeError("app unavailable")
    session_ids = [
        session.session_id
        for window in app.windows
        for tab in window.tabs
        for session in tab.sessions
    ]
    print("GOALS_ITERM_DOCTOR_RESULT=" + json.dumps({
        "session_count": len(session_ids)
    }, separators=(",", ":")))

with bounded_sdk_authentication(timeout=float(__import__("os").environ["GOALS_ITERM_DOCTOR_AUTH_TIMEOUT"])):
    iterm2.run_until_complete(check, retry=False)
'''


def _live_api_check(timeout_seconds: float) -> tuple[str, str, dict[str, Any]]:
    if sys.platform != "darwin":
        return "blocked", "The iTerm2 Python API is available only on macOS", {"checked": True}
    timeout = max(0.5, min(float(timeout_seconds), 60.0))
    auth_timeout = max(0.25, timeout * 0.7)
    environment = os.environ.copy()
    environment["GOALS_ITERM_DOCTOR_AUTH_TIMEOUT"] = str(auth_timeout)
    environment["PYTHONPATH"] = str(RUNTIME_DIR)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        process = subprocess.Popen(
            [sys.executable, "-P", "-c", _LIVE_CHECK_SCRIPT],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
            start_new_session=True,
        )
    except OSError as exc:
        return "blocked", "Could not start the read-only iTerm API check", {"checked": True, "error": type(exc).__name__}
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
        try:
            stdout, stderr = process.communicate(timeout=2.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
            stdout, stderr = process.communicate()
        return "manual_action_required", "The read-only API check timed out; authorization may need a manual response", {
            "checked": True, "timed_out": True, "timeout_seconds": timeout
        }
    for line in stdout.splitlines():
        if line.startswith("GOALS_ITERM_DOCTOR_RESULT="):
            try:
                result = json.loads(line.partition("=")[2])
            except json.JSONDecodeError:
                break
            return "ok", "Read-only iTerm session listing succeeded", {
                "checked": True,
                "session_count": result.get("session_count"),
                "write_operations": 0,
                "screen_or_history_reads": 0,
            }
    lowered = (stderr + "\n" + stdout).lower()
    if any(term in lowered for term in ("automation", "osascript", "not permitted", "not authorized", "authorization", "cookie")):
        return "manual_action_required", "iTerm authorization needs a manual check", {
            "checked": True, "exit_code": process.returncode
        }
    return "blocked", "iTerm API connection failed; check that iTerm is running, its Python API is enabled, and macOS permits Automation", {
        "checked": True, "exit_code": process.returncode
    }


def _capability_status(
    *,
    platform_status: str,
    dependency_status: str,
    app_status: str,
    api_status: str,
    state_status: str,
    process_status: str,
    policy_status: str,
    write_policy_enabled: bool,
    write: bool = False,
    process_evidence: bool = False,
) -> str:
    if "blocked" in (platform_status, dependency_status, app_status, api_status):
        return "blocked"
    if write and state_status != "ok":
        return "blocked"
    if write and (policy_status == "blocked" or not write_policy_enabled):
        return "blocked"
    if process_evidence and process_status == "blocked":
        return "blocked"
    if "manual_action_required" in (platform_status, dependency_status, app_status, api_status):
        return "manual_action_required"
    if process_evidence and process_status == "degraded":
        return "degraded"
    if app_status == "degraded":
        return "degraded"
    return "available"


def collect_doctor_report(
    *, live_api_check: bool = False, timeout_seconds: float = 8.0
) -> dict[str, Any]:
    """Return checks and capability consequences without changing user state.

    ``live_api_check`` opts into a short, read-only list-sessions API call. The
    iTerm SDK may request macOS Automation permission; this function never
    approves that request or changes iTerm settings.
    """
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        timeout_seconds = 8.0
    timeout_seconds = max(0.5, min(float(timeout_seconds), 60.0))
    checks: list[dict[str, Any]] = []
    runtime_version = _version_from_project()
    lock_digest, expected_packages, lock_valid = _lock_info()
    paths = _user_paths()

    if sys.platform == "darwin":
        if platform.machine().lower() in {"arm64", "aarch64"}:
            platform_status = "ok"
            platform_summary = "macOS arm64 is the verified initial platform"
        elif platform.machine().lower() in {"x86_64", "amd64"}:
            platform_status = "manual_action_required"
            platform_summary = "macOS Intel can prepare this lock, but platform compatibility has not been verified"
        else:
            platform_status = "blocked"
            platform_summary = "This macOS architecture is not currently supported"
    else:
        platform_status = "blocked"
        platform_summary = "iTerm control requires local macOS access"
    _add_check(
        checks,
        "platform",
        platform_status,
        platform_summary,
        observed={"system": platform.system(), "platform": sys.platform, "machine": platform.machine()},
        remediation="Run this skill on the Mac that is running iTerm2." if platform_status == "blocked" else None,
        capabilities=["all iTerm operations"],
    )

    dependency_status, dependency_summary, dependency_observed = _dependency_status(expected_packages, lock_valid)
    _add_check(
        checks,
        "runtime_dependencies",
        dependency_status,
        dependency_summary,
        observed=dependency_observed,
        remediation="Run scripts/bootstrap.sh --apply from this skill checkout." if dependency_status == "blocked" else None,
        capabilities=["all iTerm operations"],
    )

    runtime_status, runtime_summary, runtime_observed, _manifest = _manifest_status(paths, runtime_version, lock_digest)
    _add_check(
        checks,
        "runtime_manifest",
        runtime_status,
        runtime_summary,
        observed=runtime_observed,
        remediation="Run scripts/bootstrap.sh --apply from this skill checkout." if runtime_status == "blocked" else None,
        capabilities=["prepared runtime", "all iTerm operations"],
    )

    uv = shutil.which("uv")
    uv_version = None
    if uv:
        result = _run([uv, "--version"], timeout=3.0)
        if result and result.returncode == 0:
            uv_version = result.stdout.strip()
    _add_check(
        checks,
        "uv",
        "ok" if uv else "degraded",
        "uv is available for future runtime upgrades" if uv else "uv is absent; the prepared runtime remains usable",
        observed={"path": uv, "version": uv_version},
        remediation="Install uv only if you want it for future Python/runtime preparation." if not uv else None,
        capabilities=["runtime preparation"],
    )

    app_path, app_version = _find_iterm() if sys.platform == "darwin" else (None, None)
    app_status = "ok" if app_path else "blocked"
    _add_check(
        checks,
        "iterm_installed",
        app_status,
        "iTerm2 is installed" if app_path else "iTerm2 was not found in standard or indexed application locations",
        observed={"path": str(app_path) if app_path else None, "version": app_version},
        remediation="Install iTerm2 on this Mac." if not app_path else None,
        capabilities=["all iTerm operations"],
    )

    app_running = _iterm_running() if sys.platform == "darwin" else False
    running_status = "ok" if app_running else "degraded"
    _add_check(
        checks,
        "iterm_running",
        running_status,
        "iTerm2 is running" if app_running else "iTerm2 is not currently running",
        observed={"running": app_running},
        remediation="Open iTerm2 before using terminal operations." if not app_running else None,
        capabilities=["live API operations"],
    )

    data_status, data_summary, data_observed = _private_directory_status(paths["data_root"])
    state_status, state_summary, state_observed = _private_directory_status(paths["state_root"])
    _add_check(
        checks,
        "private_data",
        data_status,
        data_summary,
        observed=data_observed,
        remediation="Run scripts/bootstrap.sh --apply to create private runtime storage." if data_status == "blocked" else None,
        capabilities=["prepared runtime"],
    )
    _add_check(
        checks,
        "private_state",
        state_status,
        state_summary,
        observed=state_observed,
        remediation="Run scripts/bootstrap.sh --apply to create private state storage." if state_status == "blocked" else None,
        capabilities=["writes", "closing", "recovery receipts"],
    )
    for directory_id in ("operations", "recovery"):
        directory_status, directory_summary, directory_observed = _private_directory_status(paths[directory_id])
        # These directories are created lazily by the runtime. Their absence is
        # safe before the first operation; an existing unsafe directory is not.
        if directory_status == "blocked" and directory_observed.get("exists") is False:
            directory_status = "ok"
            directory_summary = "Private state subdirectory will be created on first use"
        _add_check(
            checks,
            f"private_{directory_id}",
            directory_status,
            directory_summary,
            observed=directory_observed,
            remediation="Check ownership and permissions of the private state directory." if directory_status == "blocked" else None,
            capabilities=["writes", "closing"],
        )

    try:
        from .policy import load_policy

        installed_policy = load_policy(state_dir=paths["state_root"])
        policy_observed = {
            "configured": installed_policy.configured,
            "read_only": installed_policy.read_only,
            "scope": "allowlist" if installed_policy.session_ids is not None else "all_sessions",
            "session_id_count": len(installed_policy.session_ids) if installed_policy.session_ids is not None else None,
        }
        write_policy_enabled = installed_policy.configured and not installed_policy.read_only
        if not installed_policy.configured:
            policy_status = "degraded"
            policy_summary = "No write policy is configured; the safe default is read-only"
        elif installed_policy.read_only:
            policy_status = "degraded"
            policy_summary = "Installed policy is read-only"
        else:
            policy_status = "ok"
            policy_summary = "Installed policy permits writes subject to each operation's other preconditions"
    except Exception as exc:
        installed_policy = None
        policy_status = "blocked"
        write_policy_enabled = False
        policy_summary = "Installation policy is invalid or unsafe"
        policy_observed = {"error_code": getattr(exc, "code", "POLICY_INVALID")}
    _add_check(
        checks,
        "installation_policy",
        policy_status,
        policy_summary,
        observed=policy_observed,
        remediation=(
            "Review the private policy file; configure itermctl policy configure only when writes are explicitly authorized."
            if policy_status != "ok"
            else None
        ),
        capabilities=["send_text", "send_keys", "rename_session", "create_window", "create_tab", "closing"],
    )

    ps_path = shutil.which("ps")
    lsof_path = shutil.which("lsof")
    if ps_path and lsof_path:
        process_status = "ok"
        process_summary = "ps and lsof are available for process and socket evidence"
    elif ps_path or lsof_path:
        process_status = "degraded"
        process_summary = "One process evidence provider is missing"
    else:
        process_status = "blocked"
        process_summary = "ps and lsof are unavailable"
    _add_check(
        checks,
        "process_evidence_tools",
        process_status,
        process_summary,
        observed={"ps": ps_path, "lsof": lsof_path},
        remediation="Install or expose ps and lsof in PATH for process inspection and recovery." if process_status != "ok" else None,
        capabilities=["process inspection", "CLI recovery", "safe closure"],
    )

    if live_api_check:
        api_status, api_summary, api_observed = _live_api_check(timeout_seconds)
    else:
        api_status = "manual_action_required"
        api_summary = "Live iTerm API reachability was not checked"
        api_observed = {"checked": False, "read_only_check_available": True}
    _add_check(
        checks,
        "iterm_api",
        api_status,
        api_summary,
        observed=api_observed,
        remediation=(
            "Run itermctl doctor --live-api-check; enable iTerm2's Python API and answer any macOS Automation prompt manually."
            if api_status in {"manual_action_required", "blocked"}
            else None
        ),
        capabilities=["list_sessions", "inspect_sessions", "read_screen", "read_history", "writes"],
    )

    shell_status = "degraded"
    _add_check(
        checks,
        "shell_integration",
        shell_status,
        "Shell Integration and prompt evidence are assessed per session at runtime",
        observed={"checked": False},
        remediation="Use per-session inspection to see whether stronger prompt/activity evidence is available.",
        capabilities=["activity and shell-state evidence"],
    )

    cli_names = ("claude", "codex", "cursor", "kiro", "agy", "agent")
    available_clis = {name: shutil.which(name) for name in cli_names if shutil.which(name)}
    _add_check(
        checks,
        "coding_cli",
        "degraded",
        "Coding CLIs are task-specific; executable presence does not verify login or recovery support",
        observed={"available_executables": available_clis},
        remediation="Before a task, verify the selected CLI's login, launch, resume, and exit behavior in its terminal environment.",
        capabilities=["task-specific launch and recovery"],
    )

    effective_app_status = app_status if app_status == "blocked" else ("ok" if app_running else "degraded")
    capabilities: dict[str, str] = {}
    for operation in (
        "list_sessions", "inspect_sessions", "read_screen", "read_history", "send_text",
        "send_keys", "rename_session", "create_window", "create_tab", "close_session",
        "close_tab", "close_window", "clean_all_sessions",
    ):
        is_write = operation not in {"list_sessions", "inspect_sessions", "read_screen", "read_history"}
        needs_process = operation in {"inspect_sessions", "close_session", "close_tab", "close_window", "clean_all_sessions"}
        capabilities[operation] = _capability_status(
            platform_status=platform_status,
            dependency_status="blocked" if dependency_status == "blocked" or runtime_status == "blocked" else dependency_status,
            app_status=effective_app_status,
            api_status=api_status,
            state_status=state_status,
            process_status=process_status,
            policy_status=policy_status,
            write_policy_enabled=write_policy_enabled,
            write=is_write,
            process_evidence=needs_process,
        )
    capabilities["live_api_check"] = "available" if api_status == "ok" else api_status
    capabilities["process_inspection"] = "available" if process_status == "ok" else process_status
    capabilities["cli_recovery"] = "blocked" if process_status != "ok" else "degraded"
    capabilities["safe_closure"] = "blocked" if process_status != "ok" or state_status != "ok" else capabilities["close_session"]
    capabilities["writes"] = "blocked" if not write_policy_enabled or state_status != "ok" else "available" if api_status == "ok" else api_status
    capabilities["shell_integration_evidence"] = shell_status

    status_order = {"ok": 0, "degraded": 1, "manual_action_required": 2, "blocked": 3}
    report_status = max((check["status"] for check in checks), key=lambda status: status_order.get(status, 3), default="ok")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "status": report_status,
        "host": {
            "system": platform.system(),
            "platform": sys.platform,
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "python_path": sys.executable,
        },
        "runtime": {
            "runtime_version": runtime_version,
            "lock_sha256": lock_digest,
            "environment_path": runtime_observed.get("environment_path"),
            "python_path": runtime_observed.get("python_path"),
            "manifest_path": str(paths["manifest"]),
            "dependencies": dependency_observed.get("dependencies", {}),
        },
        "checks": checks,
        "capabilities": capabilities,
        "policy": policy_observed,
    }
