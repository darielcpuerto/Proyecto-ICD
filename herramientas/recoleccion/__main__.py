"""Interfaz de línea de comandos de la herramienta de recolección.

Ejemplos:

    python -m herramientas.recoleccion --listar
    python -m herramientas.recoleccion --fuente OLP-001 --profundidad 1
    python -m herramientas.recoleccion --categoria oferta_local_privada --simular
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config as cfg
from .fetcher import USER_AGENT_POR_DEFECTO, Fetcher
from .recolector import Opciones, recolectar
from .storage import Almacen

# Raíz del repositorio: .../proyecto/herramientas/recoleccion/__main__.py
RAIZ = Path(__file__).resolve().parents[2]
CONFIG_POR_DEFECTO = RAIZ / "referencias" / "fuentes_internet.json"
SALIDA_POR_DEFECTO = RAIZ / "archivos" / "recoleccion"


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recoleccion",
        description="Recolecta y descarga contenido web de las fuentes declaradas en el catálogo.",
    )
    parser.add_argument("--config", type=Path, default=CONFIG_POR_DEFECTO,
                        help=f"Catálogo de fuentes (por defecto: {CONFIG_POR_DEFECTO}).")
    parser.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO,
                        help=f"Directorio de salida (por defecto: {SALIDA_POR_DEFECTO}).")
    parser.add_argument("--listar", action="store_true",
                        help="Muestra las fuentes del catálogo y termina.")

    filtros = parser.add_argument_group("filtros de fuentes")
    filtros.add_argument("--fuente", action="append", default=None,
                         help="ID o nombre de fuente (repetible).")
    filtros.add_argument("--categoria", action="append", default=None,
                         help="Categoría de fuente (repetible).")
    filtros.add_argument("--prioridad", action="append", default=None,
                         help="Prioridad de recolección (repetible).")
    filtros.add_argument("--estado", action="append", default=None,
                         help="Estado de verificación (repetible).")

    recoleccion = parser.add_argument_group("parámetros de recolección")
    recoleccion.add_argument("--profundidad", type=int, default=0,
                             help="Niveles de enlaces del mismo dominio a seguir (0 = solo la URL dada).")
    recoleccion.add_argument("--max-paginas", type=int, default=40,
                             help="Máximo de páginas por fuente.")
    recoleccion.add_argument("--max-imagenes", type=int, default=10,
                             help="Máximo de imágenes por página.")
    recoleccion.add_argument("--sin-imagenes", action="store_true",
                             help="No descargar imágenes.")
    recoleccion.add_argument("--simular", action="store_true",
                             help="No descarga nada; solo muestra qué se consultaría.")
    recoleccion.add_argument("--url", action="append", default=None,
                             help="URL semilla adicional o alternativa (repetible). Útil para validar una página concreta.")

    red = parser.add_argument_group("parámetros de red")
    red.add_argument("--delay", type=float, default=2.0,
                     help="Segundos de espera entre peticiones al mismo host.")
    red.add_argument("--timeout", type=float, default=30.0,
                     help="Tiempo máximo de espera por petición.")
    red.add_argument("--reintentos", type=int, default=2,
                     help="Reintentos por petición fallida.")
    red.add_argument("--sin-robots", action="store_true",
                     help="No comprobar robots.txt (no recomendado).")
    red.add_argument("--user-agent", default=USER_AGENT_POR_DEFECTO,
                     help="User-Agent de las peticiones.")
    red.add_argument("--render", action="store_true",
                     help="Renderizar con JavaScript (Playwright). Requiere Playwright instalado.")
    red.add_argument("--chromium", default=None,
                     help="Ruta del ejecutable de Chromium para Playwright "
                          "(por defecto: variable CHROMIUM_EXECUTABLE o /opt/chromium/chrome-linux-arm64/chrome).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)

    try:
        config = cfg.cargar_configuracion(args.config)
    except cfg.ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 2

    if args.listar:
        print(f"Catálogo: {config.ruta} (schema {config.schema_version})")
        for fuente in config.fuentes:
            print(f"  {fuente.descripcion()}")
            print(f"      {fuente.url}")
        return 0

    fuentes = cfg.filtrar(
        config,
        ids=args.fuente,
        categorias=args.categoria,
        prioridades=args.prioridad,
        estados=args.estado,
    )
    if not fuentes:
        print("Ninguna fuente coincide con los filtros indicados.", file=sys.stderr)
        return 1

    almacen = Almacen(args.salida)
    fetcher = Fetcher(
        user_agent=args.user_agent,
        timeout=args.timeout,
        delay=args.delay,
        reintentos=args.reintentos,
        respetar_robots=not args.sin_robots,
    )
    opciones = Opciones(
        profundidad=args.profundidad,
        max_paginas=args.max_paginas,
        descargar_imagenes=not args.sin_imagenes,
        max_imagenes_por_pagina=args.max_imagenes,
        simular=args.simular,
        urls_semilla=tuple(args.url or ()),
        renderizar=args.render,
        executable_chromium=args.chromium,
    )

    print(f"Fuentes seleccionadas: {len(fuentes)}")
    print(f"Salida: {'(simulada)' if args.simular else almacen.raiz}")
    resumen = recolectar(config, almacen, fetcher, opciones, fuentes)

    print("\nResumen")
    print(f"  páginas recolectadas: {resumen.paginas_ok}")
    print(f"  páginas con error:    {resumen.paginas_error}")
    print(f"  datos estructurados:  {resumen.datos_estructurados}")
    print(f"  imágenes descargadas: {resumen.imagenes}")
    print(f"  omitidas por robots:  {resumen.omitidas_robots}")
    print(f"  omitidas por política: {resumen.fuentes_omitidas_por_politica}")
    if resumen.paginas_renderizadas:
        print(f"  páginas renderizadas (JS): {resumen.paginas_renderizadas}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
