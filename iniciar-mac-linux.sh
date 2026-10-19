#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
for concilia_python in python3.12 python3 python; do
  if command -v "$concilia_python" >/dev/null 2>&1 && "$concilia_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)' >/dev/null 2>&1; then
    exec "$concilia_python" iniciar.py "$@"
  fi
done
if [ -x .venv/bin/python ] && .venv/bin/python -c 'import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize("P") == 8 else 1)' >/dev/null 2>&1; then
  exec .venv/bin/python iniciar.py "$@"
fi
printf '%s\n' 'Instale Python 3.12 de 64 bits e abra o inicializador novamente. A pasta data foi preservada.'
exit 1
