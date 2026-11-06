from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
sys.path.insert(0, str(RUNTIME))

from goals_iterm import doctor  # noqa: E402


def _doctor_environment(monkeypatch, tmp_path, *, policy=None):
    state_home = tmp_path / "state-home"
    data_home = tmp_path / "data-home"
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    state_root = state_home / "goals-iterm-skill"
    state_root.mkdir(parents=True, mode=0o700)
    state_root.chmod(0o700)
    if policy is not None:
        policy_path = state_root / "policy.json"
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        policy_path.chmod(0o600)

    monkeypatch.setattr(
        doctor,
        "_dependency_status",
        lambda *_args: ("ok", "dependencies ready", {"dependencies": {"iterm2": "2.30"}}),
    )
    monkeypatch.setattr(
        doctor,
        "_manifest_status",
        lambda *_args: (
            "ok",
            "manifest matches",
            {"environment_path": "/prepared/runtime", "python_path": "/prepared/runtime/bin/python"},
            {},
        ),
    )
    monkeypatch.setattr(doctor, "_find_iterm", lambda: (Path("/Applications/iTerm.app"), "3.7.7"))
    monkeypatch.setattr(doctor, "_iterm_running", lambda: True)
    monkeypatch.setattr(
        doctor,
        "_private_directory_status",
        lambda path: ("ok", "private", {"path": str(path), "exists": True}),
    )
    monkeypatch.setattr(doctor, "_live_api_check", lambda _timeout: ("ok", "list succeeded", {"checked": True, "session_count": 2}))
    return state_root


def test_bootstrap_check_does_not_create_private_state(tmp_path):
    data_home = tmp_path / "data"
    state_home = tmp_path / "state"
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(data_home)
    env["XDG_STATE_HOME"] = str(state_home)
    result = subprocess.run(
        [str(ROOT / "scripts/bootstrap.sh"), "--check"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 1
    assert "NEEDS APPLY" in result.stdout or "BLOCKED" in result.stdout
    assert not data_home.exists()
    assert not state_home.exists()


def test_bootstrap_check_prohibits_uv_python_downloads(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    python_command = fake_bin / "python3"
    python_command.symlink_to(sys.executable)
    uv_log = tmp_path / "uv-args.txt"
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$GOALS_TEST_UV_LOG"\n'
        'if [ "$1" = "python" ] && [ "$2" = "find" ]; then echo "$GOALS_TEST_PYTHON"; exit 0; fi\n'
        'exit 2\n',
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
    env["GOALS_TEST_UV_LOG"] = str(uv_log)
    env["GOALS_TEST_PYTHON"] = sys.executable
    env["XDG_DATA_HOME"] = str(tmp_path / "data")
    env["XDG_STATE_HOME"] = str(tmp_path / "state")

    result = subprocess.run(
        [str(ROOT / "scripts/bootstrap.sh"), "--check"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 1
    assert "python find 3.12 --no-python-downloads" in uv_log.read_text(encoding="utf-8")
    assert "python install" not in uv_log.read_text(encoding="utf-8")


def test_bootstrap_check_rejects_unknown_arguments_without_mutation(tmp_path):
    result = subprocess.run(
        [str(ROOT / "scripts/bootstrap.sh"), "--force"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 2
    assert "Usage:" in result.stderr


def test_bootstrap_install_failure_keeps_previous_manifest_and_runtime(tmp_path):
    real_uv = shutil.which("uv")
    python312 = shutil.which("python3.12")
    if not real_uv or not python312:
        pytest.skip("rollback test requires uv and an existing Python 3.12 interpreter")

    checkout = tmp_path / "checkout"
    scripts = checkout / "scripts"
    runtime = checkout / "runtime"
    scripts.mkdir(parents=True)
    runtime.mkdir()
    shutil.copy2(ROOT / "scripts/bootstrap.sh", scripts / "bootstrap.sh")
    shutil.copy2(ROOT / "runtime/requirements.lock", runtime / "requirements.lock")
    project = (ROOT / "runtime/pyproject.toml").read_text(encoding="utf-8")
    project = project.replace('version = "0.4.0.dev0"', 'version = "0.4.1.dev0"')
    (runtime / "pyproject.toml").write_text(project, encoding="utf-8")

    data_home = tmp_path / "data-home"
    state_home = tmp_path / "state-home"
    old_env = data_home / "goals-iterm-skill" / "runtimes" / "0.4.0.dev0-1575ad00cd7b8730"
    old_env.mkdir(parents=True, mode=0o700)
    marker = old_env / "previous-runtime-marker"
    marker.write_text("retained", encoding="utf-8")
    state_root = state_home / "goals-iterm-skill"
    state_root.mkdir(parents=True, mode=0o700)
    manifest_path = state_root / "runtime.json"
    original_manifest = {
        "schema_version": 1,
        "runtime_version": "0.4.0.dev0",
        "lock_sha256": "1575ad00cd7b8730011a8bf76039c9f26a981321e4be24bf68ea378e7281df71",
        "environment_path": str(old_env),
        "python_path": str(old_env / "bin/python"),
    }
    manifest_bytes = (json.dumps(original_manifest, sort_keys=True, indent=2) + "\n").encode()
    manifest_path.write_bytes(manifest_bytes)
    manifest_path.chmod(0o600)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_shim = fake_bin / "uv"
    uv_shim.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "python" ] && [ "$2" = "find" ]; then echo "$GOALS_TEST_PYTHON"; exit 0; fi\n'
        'if [ "$1" = "venv" ]; then exec "$GOALS_TEST_REAL_UV" "$@"; fi\n'
        'if [ "$1" = "pip" ]; then echo "simulated offline cache miss" >&2; exit 1; fi\n'
        'echo "unexpected uv command" >&2; exit 2\n',
        encoding="utf-8",
    )
    uv_shim.chmod(0o755)
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(data_home)
    env["XDG_STATE_HOME"] = str(state_home)
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
    env["GOALS_TEST_PYTHON"] = python312
    env["GOALS_TEST_REAL_UV"] = real_uv
    result = subprocess.run(
        [str(scripts / "bootstrap.sh"), "--apply"],
        cwd=checkout,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1
    assert "locked dependency installation failed" in result.stderr
    assert manifest_path.read_bytes() == manifest_bytes
    assert marker.read_text(encoding="utf-8") == "retained"
    assert not (old_env.parent / "0.4.1.dev0-1575ad00cd7b8730").exists()
    assert not list(old_env.parent.glob(".0.4.1.dev0-*.stage-*"))


def test_doctor_is_read_only_and_reports_safe_default_policy(monkeypatch, tmp_path):
    state_root = _doctor_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(doctor, "_live_api_check", lambda _timeout: pytest.fail("unexpected live API call"))

    report = doctor.collect_doctor_report()

    assert report["schema_version"] == 1
    assert report["status"] == "manual_action_required"
    assert report["policy"] == {
        "configured": False,
        "read_only": True,
        "scope": "all_sessions",
        "session_id_count": None,
    }
    assert report["capabilities"]["send_text"] == "blocked"
    assert report["capabilities"]["list_sessions"] == "manual_action_required"
    assert not (state_root / "runtime.json").exists()
    assert not (state_root / "operations").exists()


def test_doctor_live_flag_reports_only_read_only_catalogue(monkeypatch, tmp_path):
    _doctor_environment(monkeypatch, tmp_path)

    report = doctor.collect_doctor_report(live_api_check=True)
    check = next(item for item in report["checks"] if item["id"] == "iterm_api")

    assert check["status"] == "ok"
    assert check["observed"] == {
        "checked": True,
        "session_count": 2,
    }


def test_doctor_reports_configured_write_policy_without_session_ids(monkeypatch, tmp_path):
    state_root = _doctor_environment(
        monkeypatch,
        tmp_path,
        policy={"schema_version": 1, "read_only": False, "session_ids": ["private-session-id"]},
    )
    report = doctor.collect_doctor_report(live_api_check=True)

    assert report["policy"] == {
        "configured": True,
        "read_only": False,
        "scope": "allowlist",
        "session_id_count": 1,
    }
    assert "private-session-id" not in json.dumps(report)
    assert report["capabilities"]["send_text"] == "available"
    assert stat.S_IMODE((state_root / "policy.json").stat().st_mode) == 0o600


def test_doctor_blocks_invalid_policy(monkeypatch, tmp_path):
    state_root = _doctor_environment(monkeypatch, tmp_path)
    policy_path = state_root / "policy.json"
    policy_path.write_text("{\"schema_version\": 1}", encoding="utf-8")
    policy_path.chmod(0o600)

    report = doctor.collect_doctor_report(live_api_check=True)

    policy_check = next(item for item in report["checks"] if item["id"] == "installation_policy")
    assert policy_check["status"] == "blocked"
    assert report["capabilities"]["send_text"] == "blocked"


def test_private_directory_check_rejects_group_access(tmp_path):
    directory = tmp_path / "shared"
    directory.mkdir(mode=0o755)
    directory.chmod(0o755)

    status, _summary, observed = doctor._private_directory_status(directory)

    assert status == "blocked"
    assert observed["mode"] == "0o755"


def test_doctor_blocks_world_readable_runtime_manifest(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state-home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data-home"))
    paths = doctor._user_paths()
    paths["state_root"].mkdir(parents=True, mode=0o700)
    paths["state_root"].chmod(0o700)
    digest, _packages, _valid = doctor._lock_info()
    version = doctor._version_from_project()
    manifest = {
        "schema_version": 1,
        "runtime_version": version,
        "lock_sha256": digest,
        "environment_path": str(paths["runtimes"] / f"{version}-{digest[:16]}"),
        "python_path": str(paths["runtimes"] / f"{version}-{digest[:16]}" / "bin/python"),
    }
    paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
    paths["manifest"].chmod(0o644)

    status, summary, _observed, _loaded = doctor._manifest_status(paths, version, digest)

    assert status == "blocked"
    assert "accessible to group or other users" in summary


def test_doctor_blocks_non_312_interpreter(monkeypatch):
    monkeypatch.setattr(doctor.sys, "version_info", (3, 14, 0))

    status, summary, observed = doctor._dependency_status({"iterm2": "2.30"}, lock_valid=True)

    assert status == "blocked"
    assert "Python 3.12" in summary
    assert "python_version" in observed
