#!/bin/bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: bootstrap.sh --check | --apply

  --check  Inspect the interpreter, lock, manifest, and prepared runtime without
           changing files or downloading anything.
  --apply  Prepare an isolated Python 3.12 runtime from the hash-locked
           requirements and atomically activate it for this user.
EOF
}

MODE="${1:-}"
if [ "$#" -ne 1 ]; then
  usage >&2
  exit 2
fi
case "$MODE" in
  --check|--apply) ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

find_python3() {
  for candidate in python3 python3.12 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      candidate_path="$(command -v "$candidate")"
      if "$candidate_path" -I -c 'import sys; raise SystemExit(0 if sys.version_info.major == 3 else 1)' >/dev/null 2>&1; then
        printf '%s\n' "$candidate_path"
        return 0
      fi
    fi
  done
  return 1
}

HELPER_PYTHON=""
if HELPER_PYTHON="$(find_python3)"; then
  :
elif command -v uv >/dev/null 2>&1; then
  UV_PYTHON="$(uv python find 3.12 --no-python-downloads 2>/dev/null || true)"
  if [ -n "$UV_PYTHON" ]; then
    HELPER_PYTHON="$UV_PYTHON"
  elif [ "$MODE" = "--apply" ]; then
    echo "No Python 3.12 interpreter was found; asking uv to prepare one." >&2
    uv python install 3.12
    HELPER_PYTHON="$(uv python find 3.12)"
  fi
fi

if [ -z "$HELPER_PYTHON" ]; then
  if [ "$MODE" = "--check" ]; then
    echo "Python 3 is unavailable. Install Python 3 or uv, then rerun bootstrap.sh --check." >&2
  else
    echo "Python 3 is unavailable and uv could not prepare Python 3.12. Install uv or Python 3.12, then rerun bootstrap.sh --apply." >&2
  fi
  exit 1
fi

exec "$HELPER_PYTHON" -I - "$REPO_ROOT" "$MODE" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone


REPO_ROOT = Path(sys.argv[1]).resolve()
MODE = sys.argv[2]
RUNTIME_DIR = REPO_ROOT / "runtime"
PYPROJECT = RUNTIME_DIR / "pyproject.toml"
LOCK_FILE = RUNTIME_DIR / "requirements.lock"
EXPECTED_PACKAGES = {"iterm2", "protobuf", "websockets"}
BLOCKED_PACKAGES = {"mcp", "fastmcp", "pydantic"}
SCHEMA_VERSION = 1


def fail(message: str, code: int = 1) -> None:
    print(f"bootstrap: {message}", file=sys.stderr)
    raise SystemExit(code)


def section_value(text: str, section: str, key: str) -> str:
    current = None
    for line in text.splitlines():
        match = re.fullmatch(r"\s*\[([^]]+)\]\s*", line)
        if match:
            current = match.group(1)
            continue
        if current != section:
            continue
        match = re.fullmatch(rf'\s*{re.escape(key)}\s*=\s*"([^"]+)"\s*', line)
        if match:
            return match.group(1)
    raise ValueError(f"{key} not found in [{section}]")


def absolute_env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    path = Path(value).expanduser() if value else default
    if not path.is_absolute():
        fail(f"{name} must be an absolute path when set")
    return path.resolve()


def roots() -> tuple[Path, Path, Path, Path]:
    home = Path.home()
    data_home = absolute_env_path("XDG_DATA_HOME", home / ".local/share")
    state_home = absolute_env_path("XDG_STATE_HOME", home / ".local/state")
    data_root = data_home / "goals-iterm-skill"
    state_root = state_home / "goals-iterm-skill"
    return data_root, data_root / "runtimes", state_root, state_root / "runtime.json"


def lock_details() -> tuple[str, str, dict[str, str]]:
    if not PYPROJECT.is_file() or not LOCK_FILE.is_file():
        fail("runtime/pyproject.toml or runtime/requirements.lock is missing")
    try:
        version = section_value(PYPROJECT.read_text(encoding="utf-8"), "project", "version")
    except (OSError, ValueError) as exc:
        fail(f"cannot read runtime version: {exc}")
    lock_bytes = LOCK_FILE.read_bytes()
    digest = hashlib.sha256(lock_bytes).hexdigest()
    package_versions: dict[str, str] = {}
    lock_text = lock_bytes.decode("utf-8")
    for line in lock_text.splitlines():
        match = re.match(r"^(\S+)==([^\s\\]+)", line)
        if match:
            package_versions[match.group(1).lower().replace("_", "-")] = match.group(2)
    if set(package_versions) != EXPECTED_PACKAGES:
        fail(
            "requirements.lock must pin exactly iterm2, protobuf, and websockets; "
            f"found {', '.join(sorted(package_versions)) or '(none)'}"
        )
    blocks = re.split(r"(?m)^(?=\S+==)", lock_text)
    for block in blocks:
        if block.strip() and "--hash=sha256:" not in block:
            fail(f"dependency {block.splitlines()[0]} is not hash locked")
    if package_versions.get("iterm2") != "2.30":
        fail("runtime dependency iterm2 must remain pinned to 2.30")
    return version, digest, package_versions


def run(command: list[str], *, timeout: int = 30, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE if quiet else None,
        stderr=subprocess.PIPE if quiet else None,
        timeout=timeout,
    )


def find_python312(uv: str | None) -> tuple[Path | None, str]:
    if uv:
        result = run([uv, "python", "find", "3.12", "--no-python-downloads"], timeout=15, quiet=True)
        candidate = result.stdout.strip() if result.returncode == 0 and result.stdout else ""
        if candidate:
            path = Path(candidate).expanduser()
            try:
                version = run(
                    [str(path), "-I", "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"],
                    timeout=5,
                    quiet=True,
                )
                if version.returncode == 0 and version.stdout.startswith("3.12."):
                    return path, version.stdout.strip()
            except (OSError, subprocess.TimeoutExpired):
                pass
    candidates: list[str] = []
    for name in ("python3.12", "python3"):
        found = shutil.which(name)
        if found and found not in candidates:
            candidates.append(found)
    for candidate in candidates:
        try:
            result = run(
                [candidate, "-I", "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"],
                timeout=5,
                quiet=True,
            )
            if result.returncode == 0 and result.stdout.startswith("3.12."):
                return Path(candidate), result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None, "not found"


def manifest_environment(manifest_path: Path) -> dict | None:
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    python_path = value.get("python_path")
    environment_path = value.get("environment_path")
    if not isinstance(python_path, str) or not isinstance(environment_path, str):
        return None
    return value


def validate_environment(python_path: Path, package_versions: dict[str, str]) -> tuple[bool, str]:
    if not python_path.is_file() or not os.access(python_path, os.X_OK):
        return False, f"runtime interpreter is missing: {python_path}"
    code = r'''
import importlib.metadata as metadata
import importlib.util
import json
import sys
expected = json.loads(sys.argv[1])
if sys.version_info[:2] != (3, 12):
    raise SystemExit("prepared interpreter is not Python 3.12")
import iterm2
actual = {name: metadata.version(name) for name in expected}
blocked = [name for name in ("mcp", "fastmcp", "pydantic") if importlib.util.find_spec(name)]
if blocked:
    raise SystemExit("forbidden runtime imports present: " + ", ".join(blocked))
if actual != expected:
    raise SystemExit("installed dependency versions do not match the lock")
print(json.dumps({"python": sys.version.split()[0], "dependencies": actual}, sort_keys=True))
'''
    try:
        result = run(
            [str(python_path), "-I", "-c", code, json.dumps(package_versions)],
            timeout=15,
            quiet=True,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"could not inspect prepared runtime: {type(exc).__name__}"
    if result.returncode:
        detail = (result.stderr or result.stdout or "validation failed").strip().splitlines()[-1]
        return False, detail[:240]
    return True, result.stdout.strip()


def current_summary(
    manifest_path: Path,
    expected_environment: Path,
    expected_version: str,
    expected_digest: str,
    package_versions: dict[str, str],
) -> tuple[bool, str]:
    manifest = manifest_environment(manifest_path)
    if not manifest:
        return False, "runtime manifest is missing or invalid"
    if manifest.get("runtime_version") != expected_version:
        return False, "manifest points to a different runtime version"
    if manifest.get("lock_sha256") != expected_digest:
        return False, "manifest points to a different lock hash"
    environment = Path(str(manifest["environment_path"])).expanduser().absolute()
    python_path = Path(str(manifest["python_path"])).expanduser().absolute()
    try:
        expected_environment = expected_environment.absolute()
    except OSError:
        return False, "expected runtime path could not be resolved"
    if environment != expected_environment or python_path != (expected_environment / "bin/python").absolute():
        return False, "manifest paths do not match the versioned runtime location"
    ok, detail = validate_environment(python_path, package_versions)
    return ok, detail


def print_check(
    uv: str | None,
    python_path: Path | None,
    python_version: str,
    manifest_path: Path,
    runtime_version: str,
    digest: str,
    packages: dict[str, str],
    expected_environment: Path,
) -> int:
    print("Goals iTerm skill runtime preparation")
    print(f"  Platform: {platform.system()} {platform.machine()}")
    print(f"  Python 3.12: {python_version}{' (' + str(python_path) + ')' if python_path else ''}")
    print(f"  Installer: {'uv (' + uv + ')' if uv else 'pip fallback'}")
    print(f"  Runtime: {runtime_version}")
    print(f"  Lock SHA-256: {digest}")
    print(f"  Manifest: {manifest_path}")
    if python_path is None:
        print("  Result: BLOCKED — install Python 3.12 or uv, then run --apply")
        return 1
    ok, detail = current_summary(manifest_path, expected_environment, runtime_version, digest, packages)
    if ok:
        print("  Result: READY — " + detail)
        return 0
    print("  Result: NEEDS APPLY — " + detail)
    return 1


def ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
        fail(f"unsafe private directory (must be a real directory): {path}")
    if hasattr(os, "getuid") and details.st_uid != os.getuid():
        fail(f"unsafe private directory (not owned by this user): {path}")
    path.chmod(0o700)


def verify_locked_environment(python_path: Path, packages: dict[str, str]) -> dict:
    ok, detail = validate_environment(python_path, packages)
    if not ok:
        fail(f"prepared runtime validation failed: {detail}")
    try:
        return json.loads(detail)
    except json.JSONDecodeError:
        return {"python": "3.12", "dependencies": packages}


def atomic_manifest(path: Path, value: dict) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".runtime.", suffix=".json", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def apply(
    uv: str | None,
    helper_python: Path | None,
    data_root: Path,
    runtimes: Path,
    state_root: Path,
    manifest_path: Path,
    runtime_version: str,
    digest: str,
    packages: dict[str, str],
) -> int:
    try:
        import fcntl
    except ImportError:
        fail("this host does not provide the file-lock primitive required for safe installation")
    if sys.platform != "darwin":
        print(
            "bootstrap: preparing the runtime on this host, but iTerm control is supported only on macOS",
            file=sys.stderr,
        )
    if uv:
        interpreter_path, python_version = find_python312(uv)
        if interpreter_path is None:
            print("No Python 3.12 interpreter was found; asking uv to prepare one.", file=sys.stderr)
            result = run([uv, "python", "install", "3.12"], timeout=180)
            if result.returncode:
                fail("uv could not install Python 3.12; inspect the installer output and retry")
            interpreter_path, python_version = find_python312(uv)
    else:
        interpreter_path, python_version = find_python312(None)
    if interpreter_path is None:
        fail("Python 3.12 is required. Install uv or Python 3.12, then rerun --apply")

    ensure_private_directory(data_root)
    ensure_private_directory(runtimes)
    ensure_private_directory(state_root)
    lock_path = state_root / "bootstrap.lock"
    lock_flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    try:
        lock_fd = os.open(lock_path, lock_flags, 0o600)
    except OSError as exc:
        fail(f"cannot open the private installation lock: {type(exc).__name__}")
    lock_details = os.fstat(lock_fd)
    if not stat.S_ISREG(lock_details.st_mode) or (hasattr(os, "getuid") and lock_details.st_uid != os.getuid()):
        os.close(lock_fd)
        fail("installation lock is not a regular file owned by this user")
    os.fchmod(lock_fd, 0o600)
    deadline = time.monotonic() + 120
    while True:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                os.close(lock_fd)
                fail("another bootstrap is still running; retry after it finishes")
            time.sleep(0.2)

    env_key = f"{runtime_version}-{digest[:16]}"
    final_environment = runtimes / env_key
    final_python = final_environment / "bin/python"
    try:
        if final_environment.exists():
            ok, detail = validate_environment(final_python, packages)
            if not ok:
                fail(
                    f"runtime directory already exists but is invalid; it was retained: {detail}. "
                    "Use a new runtime version after reviewing the existing directory."
                )
            print(f"Reusing prepared runtime: {final_environment}")
        else:
            stage = runtimes / f".{env_key}.stage-{os.getpid()}-{int(time.time())}"
            stage_python = stage / "bin/python"
            try:
                stage.mkdir(mode=0o700)
                if uv:
                    result = run([uv, "venv", "--python", str(interpreter_path), str(stage)])
                    if result.returncode:
                        fail("uv could not create the isolated environment")
                    result = run(
                        [uv, "pip", "install", "--python", str(stage_python), "--require-hashes", "-r", str(LOCK_FILE)],
                        timeout=600,
                    )
                else:
                    result = run([str(interpreter_path), "-m", "venv", str(stage)], timeout=60)
                    if result.returncode:
                        fail("Python could not create the isolated environment")
                    result = run(
                        [
                            str(stage_python),
                            "-m",
                            "pip",
                            "install",
                            "--disable-pip-version-check",
                            "--no-input",
                            "--require-hashes",
                            "-r",
                            str(LOCK_FILE),
                        ],
                        timeout=600,
                    )
                if result.returncode:
                    fail("locked dependency installation failed; the active manifest was not changed")
                verify_locked_environment(stage_python, packages)
                os.replace(stage, final_environment)
            finally:
                if stage.exists():
                    shutil.rmtree(stage, ignore_errors=True)
        runtime_info = verify_locked_environment(final_python, packages)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "runtime_version": runtime_version,
            "lock_sha256": digest,
            "environment_path": str(final_environment),
            "python_path": str(final_python),
            "python_version": python_version,
            "dependencies": runtime_info["dependencies"],
            "installer": "uv" if uv else "pip",
            "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        atomic_manifest(manifest_path, manifest)
        print(f"Prepared runtime: {final_environment}")
        print(f"Activated manifest: {manifest_path}")
        print("The previous runtime directory, if any, was retained for rollback.")
        return 0
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def main() -> int:
    if sys.version_info.major != 3:
        fail("bootstrap helper requires Python 3")
    try:
        runtime_version, digest, packages = lock_details()
        data_root, runtimes, state_root, manifest_path = roots()
    except (OSError, UnicodeError) as exc:
        fail(f"cannot inspect runtime files or private paths: {exc}")
    uv = shutil.which("uv")
    interpreter_path, python_version = find_python312(uv)
    if MODE == "--check":
        expected_environment = runtimes / f"{runtime_version}-{digest[:16]}"
        return print_check(
            uv,
            interpreter_path,
            python_version,
            manifest_path,
            runtime_version,
            digest,
            packages,
            expected_environment,
        )
    return apply(
        uv,
        Path(sys.executable) if sys.version_info[:2] == (3, 12) else None,
        data_root,
        runtimes,
        state_root,
        manifest_path,
        runtime_version,
        digest,
        packages,
    )


if __name__ == "__main__":
    raise SystemExit(main())
PY
