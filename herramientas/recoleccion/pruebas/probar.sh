#!/usr/bin/env bash
# Ejecuta las pruebas de la herramienta con el intérprete del entorno virtual
# del proyecto de análisis de datos (dentro de proot-distro Ubuntu).
set -euo pipefail

PROYECTO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PYTHON="${PYTHON:-/root/DataScience/.venv/bin/python}"

exec proot-distro login ubuntu -- env "PYTHONPATH=$PROYECTO" "$PYTHON" -m unittest discover -s "$PROYECTO/herramientas/recoleccion/pruebas" -t "$PROYECTO" -v "$@"
