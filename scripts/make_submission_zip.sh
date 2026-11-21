#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python="${PYTHON:-python3}"
"$python" - "$root" "${1:-队伍名称}" "${2:-联系方式}" <<'PY'
from pathlib import Path
import re
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

root, team, contact = sys.argv[1:]
root = Path(root)
for label, field in (("team", team), ("contact", contact)):
    if not field.strip() or not re.fullmatch(r'[^/\\:+*?"<>|\x00-\x1f]{1,80}', field):
        sys.exit(f"Invalid {label}: use 1–80 characters without path or separator symbols.")
target = root / f"ClearBooks智能体+{team}+v1.0+{contact}.zip"
required = ("ppt", "project", "video", "codearts_proof", "readme")
files = [root / "README.md", root / "LICENSE"]
for name in (*required, "docs", "scripts"):
    folder = root / name
    members = [
        p for p in sorted(folder.rglob("*")) if p.is_file() and not p.is_symlink()
        and all(not part.startswith(".") and part != "__pycache__" for part in p.relative_to(root).parts)
        and not p.name.endswith((".pyc", ".sqlite3", ".sqlite3-wal", ".sqlite3-shm", ".sqlite3-journal", ".zip"))
    ]
    if name in required and not members:
        sys.exit(f"Missing required submission directory: {name}")
    files.extend(members)
with tempfile.NamedTemporaryFile(prefix=".submission-", suffix=".zip", dir=root) as handle:
    with ZipFile(handle, "w", ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, file.relative_to(root))
    size = Path(handle.name).stat().st_size
    if size > 200_000_000:
        sys.exit(f"Archive is {size:,} bytes; maximum is 200,000,000 bytes.")
    with ZipFile(handle.name) as archive:
        if archive.testzip() is not None:
            sys.exit("ZIP integrity check failed.")
    target.write_bytes(Path(handle.name).read_bytes())
print(f"{target.name}: {size:,} bytes, {len(files)} files; ZIP integrity OK")
print("Before submitting: verify the actual CodeArts evidence, updated deck/summary, and recorded video or link.")
PY
