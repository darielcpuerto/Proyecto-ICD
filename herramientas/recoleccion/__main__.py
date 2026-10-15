"""Punto de entrada: ``python -m herramientas.recoleccion``."""

from __future__ import annotations

from .nucleo.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
