#!/usr/bin/env bash
# Ejecuta la herramienta con el intérprete del entorno virtual de análisis de
# datos que vive dentro de proot-distro (Ubuntu): /root/DataScience/.venv.
# No crea ni modifica entornos virtuales.
#
# Uso:
#   herramientas/recoleccion/ejecutar.sh --listar
#   herramientas/recoleccion/ejecutar.sh --fuente OLP-001 --simular
set -euo pipefail

PROYECTO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${PYTHON:-/root/DataScience/.venv/bin/python}"

exec proot-distro login ubuntu -- env "PYTHONPATH=$PROYECTO" "$PYTHON" -m herramientas.recoleccion "$@"
