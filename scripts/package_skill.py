#!/usr/bin/env python3
"""Build a portable skill archive without environments, state, or credentials."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import zipfile


def package(root: Path, destination: Path) -> Path:
    files = [root / name for name in ("SKILL.md", "LICENSE", "CONTRIBUTING.md", "SECURITY.md", "README.md", "README.zh-CN.md", "README.zh-TW.md", "README.ja.md")]
    for directory, pattern in (("agents", "*.yaml"), ("references", "*.md"), ("runtime/goals_iterm", "*.py")):
        files.extend(sorted((root / directory).glob(pattern)))
    files.extend(root / "scripts" / name for name in ("bootstrap.sh", "itermctl", "session_registry.py"))
    files.extend(root / "runtime" / name for name in ("pyproject.toml", "requirements.lock", "UPSTREAM.md", "LICENSE"))
    missing = [str(path.relative_to(root)) for path in files if not path.is_file() or path.is_symlink()]
    if missing:
        raise ValueError("Missing or symlinked package resources: " + ", ".join(missing))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            entry = zipfile.ZipInfo("goals-iterm-skill/" + path.relative_to(root).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = (0o100755 if path.name in {"bootstrap.sh", "itermctl", "session_registry.py"} else 0o100644) << 16
            archive.writestr(entry, path.read_bytes())
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix + ".sha256").write_text(f"{digest}  {destination.name}\n")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(package(Path(__file__).resolve().parents[1], args.output.resolve()))


if __name__ == "__main__":
    main()
