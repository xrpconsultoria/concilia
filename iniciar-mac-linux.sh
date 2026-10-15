#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -c 'import sys; assert sys.version_info >= (3,12), "Instale Python 3.12 ou posterior"'
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir -r requirements.txt
printf '%s
' 'Abra no navegador o endereço mostrado em Running on. Mantenha este terminal aberto; Ctrl+C encerra o aplicativo.'
exec .venv/bin/python app.py
