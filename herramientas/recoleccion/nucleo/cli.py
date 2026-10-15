"""Interfaz de línea de comandos de la herramienta de recolección.

Flujo de dos fases:

    python -m herramientas.recoleccion --fuente OLP-004 --descubrir
    # revisar y aprobar archivos/recoleccion/OLP-004_suncar/candidatos.jsonl
    python -m herramientas.recoleccion --fuente OLP-004 --recolectar
    # o, sin editar el archivo:
    python -m herramientas.recoleccion --fuente OLP-004 --recolectar --aprobar-relevantes

Las semillas declaradas por cada sitio se consideran aprobadas y se recolectan
durante el descubrimiento. Los enlaces descubiertos solo se descargan si se
aprueban en ``candidatos.jsonl`` o con ``--aprobar-relevantes``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config as cfg
from .almacen import Almacen
from .fetcher import USER_AGENT_POR_DEFECTO, Fetcher
from .recolector import Opciones, recolectar

# Raíz del repositorio: .../proyecto/herramientas/recoleccion/nucleo/cli.py
RAIZ = Path(__file__).resolve().parents[3]
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

    fases = parser.add_argument_group("fases")
    fases.add_argument("--descubrir", action="store_true",
                       help="Fase 1: obtiene semillas, recolecta y escribe candidatos.jsonl (por defecto).")
    fases.add_argument("--recolectar", action="store_true",
                       help="Fase 2: descarga solo los candidatos aprobados.")
    fases.add_argument("--aprobar-relevantes", action="store_true",
                       help="En la fase 2, aprueba automáticamente los candidatos relevantes.")
    fases.add_argument("--umbral", type=int, default=None,
                       help="Umbral de puntuación de relevancia (por defecto: el del lexicón).")

    recoleccion = parser.add_argument_group("parámetros de recolección")
    recoleccion.add_argument("--max-paginas", type=int, default=250,
                             help="Máximo de páginas por fuente (por defecto 250).")
    recoleccion.add_argument("--simular", action="store_true",
                             help="No descarga nada; solo muestra qué se consultaría.")
    recoleccion.add_argument("--forzar", action="store_true",
                             help="Ignora la deduplicación: vuelve a solicitar URLs ya capturadas.")
    recoleccion.add_argument("--url", action="append", default=None,
                             help="URL semilla adicional o alternativa (repetible).")

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

    fase = "recolectar" if args.recolectar else "descubrir"
    almacen = Almacen(args.salida)
    fetcher = Fetcher(
        user_agent=args.user_agent,
        timeout=args.timeout,
        delay=args.delay,
        reintentos=args.reintentos,
        respetar_robots=not args.sin_robots,
    )
    opciones = Opciones(
        max_paginas=args.max_paginas,
        simular=args.simular,
        urls_semilla=tuple(args.url or ()),
        forzar=args.forzar,
        umbral_relevancia=args.umbral,
    )

    print(f"Fase: {fase}")
    print(f"Fuentes seleccionadas: {len(fuentes)}")
    print(f"Salida: {'(simulada)' if args.simular else almacen.raiz}")
    resumen = recolectar(
        config, almacen, fetcher, opciones, fuentes, fase,
        aprobar_relevantes=args.aprobar_relevantes,
    )

    print("\nResumen")
    print(f"  páginas recolectadas:   {resumen.paginas_ok}")
    print(f"  páginas con error:      {resumen.paginas_error}")
    print(f"  activos obtenidos:      {resumen.activos}")
    print(f"  datos estructurados:    {resumen.datos_estructurados}")
    print(f"  candidatos:             {resumen.candidatos}")
    print(f"  aprobadas:              {resumen.aprobadas}")
    print(f"  omitidas por dedup:     {resumen.omitidas_por_dedup}")
    print(f"  omitidas por robots:    {resumen.omitidas_robots}")
    print(f"  omitidas por política:  {resumen.omitidas_por_politica}")
    for linea in resumen.detalle:
        print(f"    - {linea}")
    if fase == "descubrir":
        print("\nSiguiente: revise candidatos.jsonl y ejecute --recolectar "
              "(o --recolectar --aprobar-relevantes).")
    return 0
