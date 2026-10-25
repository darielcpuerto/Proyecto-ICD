"""Interfaz de línea de comandos de la herramienta de recolección.

Pasada única (recomendada)::

    python -m herramientas.recoleccion --todo
    python -m herramientas.recoleccion --fuente OLP-002 --todo \
        --objetivo-paginas 250 --max-intentos 500 --ventana-dias 30

Flujo anterior en dos fases (compatibilidad y auditoría)::

    python -m herramientas.recoleccion --fuente OLP-004 --descubrir
    # revisar archivos/recoleccion/OLP-004_suncar/candidatos.jsonl
    python -m herramientas.recoleccion --fuente OLP-004 --recolectar
    python -m herramientas.recoleccion --fuente OLP-004 --recolectar --aprobar-relevantes

En la pasada única solo se guardan páginas de oferta. Bembete busca hasta 250
anuncios de detalle únicos en una ventana de 30 días; SunCar e Infinity recogen
todas sus ofertas únicas.
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
        description="Recolecta contenido web de las fuentes declaradas en el catálogo.",
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
    fases.add_argument("--todo", "--una-pasada", dest="todo", action="store_true",
                       help="Pasada única secuencial: descubrir, clasificar, persistir y extraer.")
    fases.add_argument("--descubrir", action="store_true",
                       help="Fase 1 (anterior): obtiene semillas y escribe candidatos.jsonl.")
    fases.add_argument("--recolectar", action="store_true",
                       help="Fase 2 (anterior): descarga solo los candidatos aprobados.")
    fases.add_argument("--aprobar-relevantes", action="store_true",
                       help="En la fase 2, aprueba automáticamente los candidatos relevantes.")
    fases.add_argument("--umbral", type=int, default=None,
                       help="Umbral de puntuación de relevancia (por defecto: el del lexicón).")

    recoleccion = parser.add_argument_group("parámetros de recolección")
    recoleccion.add_argument("--objetivo-paginas", type=int, default=None,
                             help="Objetivo de anuncios/ofertas únicas (por defecto: el del sitio).")
    recoleccion.add_argument("--max-intentos", type=int, default=500,
                             help="Máximo de peticiones de página por fuente (0 = sin límite).")
    recoleccion.add_argument("--ventana-dias", type=int, default=30,
                             help="Máximo de sitemaps diarios a considerar (por defecto 30).")
    recoleccion.add_argument("--max-paginas", type=int, default=250,
                             help="Máximo de páginas por fuente en el flujo anterior (por defecto 250).")
    recoleccion.add_argument("--simular", action="store_true",
                             help="No descarga páginas; solo anuncia candidatos y objetivos.")
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
        config = cfg.cargar_configuracion(
            args.config if args.config.is_absolute() else RAIZ / args.config
        )
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

    if args.todo:
        fase = "todo"
    elif args.recolectar:
        fase = "recolectar"
    else:
        fase = "descubrir"

    almacen = Almacen(args.salida if args.salida.is_absolute() else RAIZ / args.salida)
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
        objetivo_paginas=args.objetivo_paginas,
        max_intentos=args.max_intentos,
        ventana_dias=args.ventana_dias,
    )

    print(f"Fase: {fase}")
    print(f"Fuentes seleccionadas: {len(fuentes)}")
    print(f"Salida: {'(simulada)' if args.simular else almacen.raiz}")
    resumen = recolectar(
        config, almacen, fetcher, opciones, fuentes, fase,
        aprobar_relevantes=args.aprobar_relevantes,
    )

    print("\nResumen")
    if fase == "todo":
        for fuente_id, cont in resumen.fuentes.items():
            print(f"  [{fuente_id}]")
            print(f"    candidatos:            {cont.candidatos_generados}")
            print(f"    intentos de red:       {cont.intentos_red}")
            print(f"    respuestas OK:         {cont.respuestas_ok}")
            print(f"    errores:               {cont.errores}")
            print(f"    páginas aceptadas:     {cont.paginas_aceptadas}")
            print(f"    páginas descartadas:   {cont.paginas_descartadas}")
            print(f"    registros aceptados:   {cont.registros_aceptados}")
            print(f"    registros descartados: {cont.registros_descartados}")
            print(f"    duplicados:            {cont.registros_duplicados}")
            print(f"    objetivo alcanzado:    {cont.objetivo_alcanzado} "
                  f"({cont.objetivo if cont.objetivo is not None else 'todas'})")
            print(f"    motivo de parada:      {cont.motivo_parada}")
    else:
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
