#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python="${PYTHON:-python3}"
"$python" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10 or later is required"'
"$python" -m venv "$root/.venv"
requirements=requirements.txt
if [[ "${1:-}" == "--dev" ]]; then requirements=requirements-dev.txt; fi
"$root/.venv/bin/python" -m pip install -r "$root/project/$requirements"
printf 'Run: cd "%s/project" && ../.venv/bin/python -m clearbooks serve\n' "$root"
