"""Orquestación de la recolección.

Modos
-----
1. ``--todo`` / ``--una-pasada`` (recomendado): pipeline único por fuente::

       preflight → candidatos → prefiltro → obtención secuencial →
       clasificación de página → persistencia (solo aceptadas) → extracción →
       filtro de registros → deduplicación → contadores y reporte

   Solo cuenta y guarda páginas de oferta. Las páginas ``lista``, ``contexto``
   y ``navegacion`` no se descargan. Las descartadas dejan metadatos en
   ``descartes.jsonl`` sin conservar su contenido.

2. ``--descubrir`` y ``--recolectar``: flujo anterior en dos fases, se mantiene
   para auditoría y compatibilidad.

En todos los modos se aplica la política de acceso, la deduplicación por
contenido/identidad y el límite de páginas por fuente. No se descargan imágenes
ni se usa navegador.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .. import sitios
from ..sitios.base import (
    Candidato,
    EvidenciaPagina,
    OpcionesSitio,
    Sitio,
    TipoPagina,
    TIPOS_CONTABLES,
    dominio_normalizado,
)
from . import config as cfg
from . import extraccion, politica, relevancia
from .almacen import Almacen, ahora_utc, git_commit, hash_contenido
from .contenido import Contenido, es_imagen, extraer as extraer_contenido
from .fetcher import Fetcher, Respuesta
from .urls import canonicalizar

EXTENSIONES_NO_CRAWLEABLES = (".pdf", ".zip", ".rar", ".doc", ".docx", ".xls", ".xlsx")

#: En simulación se anuncia una muestra; no se recorre todo el universo.
LIMITE_MUESTRA_SIMULADA = 30

RAIZ_REPOSITORIO = Path(__file__).resolve().parents[3]


@dataclass
class Opciones:
    """Parámetros de ejecución de la recolección."""

    max_paginas: int = 250
    simular: bool = False
    urls_semilla: tuple[str, ...] = ()
    forzar: bool = False
    umbral_relevancia: int | None = None
    # -- pasada única ---------------------------------------------------
    objetivo_paginas: int | None = None
    max_intentos: int = 500
    ventana_dias: int = 30


@dataclass
class Contadores:
    """Contadores separados por fuente y por fase."""

    fuente_id: str
    fuente_nombre: str = ""
    candidatos_generados: int = 0
    candidatos_descartados_url: int = 0
    intentos_red: int = 0
    respuestas_ok: int = 0
    errores: int = 0
    omitidas_robots: int = 0
    omitidas_por_dedup: int = 0
    omitidas_por_politica: int = 0
    paginas_por_tipo: dict[str, int] = field(default_factory=dict)
    paginas_aceptadas: int = 0
    paginas_nuevas: int = 0
    paginas_descartadas: int = 0
    registros_extraidos: int = 0
    registros_aceptados: int = 0
    registros_descartados: int = 0
    registros_duplicados: int = 0
    activos: int = 0
    delay_efectivo: float = 0.0
    objetivo: int | None = None
    objetivo_alcanzado: bool = False
    motivo_parada: str = ""
    ventana_sitemaps: list[str] = field(default_factory=list)

    def contar_tipo(self, tipo: TipoPagina | None) -> None:
        clave = tipo.value if tipo else "desconocido"
        self.paginas_por_tipo[clave] = self.paginas_por_tipo.get(clave, 0) + 1

    def a_dict(self) -> dict:
        return {
            "fuente_id": self.fuente_id,
            "fuente_nombre": self.fuente_nombre,
            "candidatos_generados": self.candidatos_generados,
            "candidatos_descartados_url": self.candidatos_descartados_url,
            "intentos_red": self.intentos_red,
            "respuestas_ok": self.respuestas_ok,
            "errores": self.errores,
            "omitidas_robots": self.omitidas_robots,
            "omitidas_por_dedup": self.omitidas_por_dedup,
            "omitidas_por_politica": self.omitidas_por_politica,
            "paginas_por_tipo": dict(sorted(self.paginas_por_tipo.items())),
            "paginas_aceptadas": self.paginas_aceptadas,
            "paginas_nuevas": self.paginas_nuevas,
            "paginas_descartadas": self.paginas_descartadas,
            "registros_extraidos": self.registros_extraidos,
            "registros_aceptados": self.registros_aceptados,
            "registros_descartados": self.registros_descartados,
            "registros_duplicados": self.registros_duplicados,
            "activos": self.activos,
            "delay_efectivo": self.delay_efectivo,
            "objetivo": self.objetivo,
            "objetivo_alcanzado": self.objetivo_alcanzado,
            "motivo_parada": self.motivo_parada,
            "ventana_sitemaps": list(self.ventana_sitemaps),
        }


@dataclass
class Resumen:
    """Recuento de lo recolectado en una ejecución."""

    # Campos del flujo anterior (compatibilidad).
    paginas_ok: int = 0
    paginas_error: int = 0
    omitidas_robots: int = 0
    omitidas_por_dedup: int = 0
    omitidas_por_politica: int = 0
    candidatos: int = 0
    aprobadas: int = 0
    datos_estructurados: int = 0
    activos: int = 0
    # Campos de la pasada única.
    fuentes: dict[str, Contadores] = field(default_factory=dict)
    detalle: list[str] = field(default_factory=list)


class Recolector:
    def __init__(
        self,
        config: cfg.Configuracion,
        almacen: Almacen,
        fetcher: Fetcher,
        opciones: Opciones,
    ) -> None:
        self.config = config
        self.almacen = almacen
        self.fetcher = fetcher
        self.opciones = opciones
        self.resumen = Resumen()
        self.overrides = politica.cargar_overrides()
        self.lexico = relevancia.cargar_lexico()
        if self.opciones.umbral_relevancia is not None:
            self.lexico.umbral = self.opciones.umbral_relevancia

    # -- obtención ------------------------------------------------------
    def _obtener(self, url: str) -> Respuesta:
        return self.fetcher.obtener(url)

    def _obtener_activo(self, url: str) -> Respuesta:
        """Obtiene un activo (p. ej. el bundle JS) respetando robots.txt."""
        if not self.fetcher.permitido_por_robots(url):
            return Respuesta(url_solicitada=url, url_final=url, estado_http=0,
                             content_type="", contenido=b"", encoding="utf-8",
                             error="bloqueado_por_robots.txt")
        return self.fetcher.obtener(url)

    # -- utilidades ------------------------------------------------------
    @staticmethod
    def _crawleable(url: str) -> bool:
        ruta = urlparse(url).path.lower()
        return not es_imagen(url) and not ruta.endswith(EXTENSIONES_NO_CRAWLEABLES)

    def _mismo_sitio(self, url: str, dominio: str) -> bool:
        return dominio_normalizado(urlparse(url).netloc) == dominio

    def _evaluar_politica(self, fuente: cfg.Fuente) -> politica.Decision:
        robots_ok = self.fetcher.permitido_por_robots(fuente.url)
        texto_robots = self.fetcher.texto_robots(fuente.url)
        return politica.evaluar(fuente, robots_ok, texto_robots, self.overrides.get(fuente.id))

    def _texto(self, respuesta: Respuesta) -> str:
        return respuesta.texto()

    # -- pasada única ----------------------------------------------------
    def todo(self, fuentes) -> Resumen:
        for fuente in fuentes:
            print(f"Fuente {fuente.descripcion()}")
            self._todo_fuente(fuente)
        self._escribir_resumen()
        return self.resumen

    def _todo_fuente(self, fuente: cfg.Fuente) -> None:
        sitio = sitios.para_fuente(fuente)
        carpeta = self.almacen.carpeta_fuente(fuente.id, fuente.nombre)
        cont = Contadores(fuente_id=fuente.id, fuente_nombre=fuente.nombre)
        self.resumen.fuentes[fuente.id] = cont

        if not getattr(sitio, "automatico", True):
            cont.omitidas_por_politica += 1
            cont.motivo_parada = "sitio sin módulo propio; requiere revisión manual"
            self.resumen.detalle.append(
                f"{fuente.id} {fuente.nombre}: OMITIDA — {cont.motivo_parada}"
            )
            print(f"  omitida: {cont.motivo_parada}")
            return

        decision = self._evaluar_politica(fuente)
        if not decision.puede_recolectar:
            cont.omitidas_por_politica += 1
            cont.motivo_parada = decision.motivo
            self.resumen.detalle.append(
                f"{fuente.id} {fuente.nombre}: OMITIDA — {decision.motivo}"
            )
            print(f"  omitida: {decision.motivo}")
            return

        texto_robots = self.fetcher.texto_robots(fuente.url)
        cont.delay_efectivo = self.fetcher.retardo_efectivo(fuente.url)
        opciones_sitio = OpcionesSitio(
            ventana_dias=self.opciones.ventana_dias,
            objetivo_paginas=self.opciones.objetivo_paginas,
            max_intentos=self.opciones.max_intentos,
            simular=self.opciones.simular,
            urls_semilla=self.opciones.urls_semilla,
        )
        objetivo = sitio.objetivo(opciones_sitio)
        cont.objetivo = objetivo.objetivo

        indice = self.almacen.cargar_indice(carpeta)
        cont.paginas_aceptadas = len(indice.paginas_aceptadas)
        candidatos_registrados: list[dict] = []
        max_intentos = self.opciones.max_intentos

        if (
            objetivo.objetivo is not None
            and cont.paginas_aceptadas >= objetivo.objetivo
            and not self.opciones.forzar
        ):
            cont.objetivo_alcanzado = True
            cont.motivo_parada = (
                "objetivo ya alcanzado en una ejecución anterior; "
                "no se descargan páginas nuevas"
            )
            self.resumen.detalle.append(
                f"{fuente.id} {fuente.nombre}: {cont.paginas_aceptadas} página(s) "
                f"ya recolectadas; {cont.motivo_parada}"
            )
            print(f"  {cont.motivo_parada}")
            return

        try:
            lotes = sitio.lotes_candidatos(self.fetcher, texto_robots, opciones_sitio)
        except Exception as exc:  # el sitemap no debe tumbar la ejecución
            print(f"  error al generar candidatos: {type(exc).__name__}: {exc}")
            lotes = []
            cont.motivo_parada = f"error de descubrimiento: {exc}"

        print(f"  sitio: {sitio.nombre} | objetivo: {objetivo.objetivo or 'todas'} "
              f"({objetivo.unidad})")

        detener = False
        mostrados_simulados = 0
        for lote in lotes:
            if detener:
                break
            if lote:
                fecha_lote = lote[0].fecha_sitemap
                if fecha_lote and fecha_lote not in cont.ventana_sitemaps:
                    cont.ventana_sitemaps.append(fecha_lote)
            print(f"  lote: {lote[0].origen if lote else '(vacío)'} — {len(lote)} candidatos")
            for candidato in lote:
                if objetivo.objetivo is not None and cont.paginas_aceptadas >= objetivo.objetivo:
                    detener = True
                    break
                if max_intentos and cont.intentos_red >= max_intentos:
                    cont.motivo_parada = "límite de intentos alcanzado"
                    detener = True
                    break
                if (self.opciones.simular
                        and mostrados_simulados >= LIMITE_MUESTRA_SIMULADA):
                    cont.motivo_parada = (
                        f"simulación: muestra de {LIMITE_MUESTRA_SIMULADA} candidatos"
                    )
                    detener = True
                    break

                cont.candidatos_generados += 1
                registro_candidato = {
                    "url": candidato.url,
                    "url_canonica": candidato.url_canonica,
                    "origen": candidato.origen,
                    "tipo_esperado": candidato.tipo_esperado.value if candidato.tipo_esperado else None,
                    "fecha_sitemap": candidato.fecha_sitemap,
                    "incluido": False,
                    "motivo": "",
                }
                candidatos_registrados.append(registro_candidato)

                permitido, motivo = sitio.prefiltro(candidato.url)
                if not permitido:
                    cont.candidatos_descartados_url += 1
                    registro_candidato["motivo"] = motivo
                    self._descartar_pagina(
                        carpeta, fuente, cont, candidato.url,
                        candidato.tipo_esperado, motivo, None, 0, [],
                    )
                    continue

                tipo = candidato.tipo_esperado or sitio.tipo_por_url(candidato.url)
                if tipo is None:
                    tipo = TipoPagina.CONTEXTO
                if tipo in (TipoPagina.LISTA, TipoPagina.CONTEXTO, TipoPagina.NAVEGACION):
                    cont.candidatos_descartados_url += 1
                    motivo = f"página «{tipo.value}» no descargable en la pasada única"
                    registro_candidato["motivo"] = motivo
                    self._descartar_pagina(
                        carpeta, fuente, cont, candidato.url, tipo, motivo, None, 0, [],
                    )
                    continue

                if not self._crawleable(candidato.url):
                    cont.candidatos_descartados_url += 1
                    motivo = "URL no crawleable (imagen o archivo)"
                    registro_candidato["motivo"] = motivo
                    self._descartar_pagina(
                        carpeta, fuente, cont, candidato.url, tipo, motivo, None, 0, [],
                    )
                    continue

                if not self.opciones.forzar and indice.url_intentada(candidato.url):
                    cont.omitidas_por_dedup += 1
                    registro_candidato["motivo"] = "URL ya intentada (dedup)"
                    continue

                registro_candidato["incluido"] = True
                if self.opciones.simular:
                    print(f"  [simulado] {tipo.value}: {candidato.url}")
                    mostrados_simulados += 1
                    continue

                cont.intentos_red += 1
                self._procesar_todo(
                    fuente, sitio, candidato.url, tipo, decision, carpeta, indice, cont,
                )

        if not cont.motivo_parada:
            if objetivo.objetivo is None:
                cont.objetivo_alcanzado = True
                cont.motivo_parada = "sin objetivo: se procesaron todas las ofertas disponibles"
            elif cont.paginas_aceptadas >= objetivo.objetivo:
                cont.objetivo_alcanzado = True
                cont.motivo_parada = "objetivo alcanzado"
            else:
                cont.objetivo_alcanzado = False
                cont.motivo_parada = (
                    f"objetivo no alcanzado: {cont.paginas_aceptadas} de {objetivo.objetivo}"
                )

        self.almacen.escribir_candidatos(carpeta, candidatos_registrados)
        self.resumen.candidatos += len(candidatos_registrados)
        self.resumen.paginas_ok += cont.respuestas_ok
        self.resumen.paginas_error += cont.errores
        self.resumen.omitidas_robots += cont.omitidas_robots
        self.resumen.omitidas_por_dedup += cont.omitidas_por_dedup
        self.resumen.datos_estructurados += cont.registros_aceptados
        self.resumen.activos += cont.activos

        self.resumen.detalle.append(
            f"{fuente.id} {fuente.nombre}: {cont.paginas_aceptadas} página(s) de oferta, "
            f"{cont.registros_aceptados} registro(s), {cont.registros_duplicados} duplicado(s); "
            f"{cont.motivo_parada}"
        )
        print(
            f"  resultado: {cont.paginas_aceptadas} página(s), "
            f"{cont.registros_aceptados} registro(s), {cont.errores} error(es); "
            f"{cont.motivo_parada}"
        )

    def _procesar_todo(
        self,
        fuente: cfg.Fuente,
        sitio: Sitio,
        url: str,
        tipo: TipoPagina,
        decision: politica.Decision,
        carpeta: Path,
        indice,
        cont: Contadores,
    ) -> None:
        fecha = ahora_utc()
        respuesta = self._obtener(url)

        if respuesta.error == "bloqueado_por_robots.txt":
            cont.omitidas_robots += 1
            cont.omitidas_por_politica += 1
            self._descartar_pagina(
                carpeta, fuente, cont, url, tipo,
                "robots.txt no permite la consulta", None, 0, [],
            )
            self.almacen.registrar(carpeta, self._registro(
                fuente, url, respuesta.url_final, fecha, 0, "", None, None, None,
                None, ["robots.txt no permite la consulta"], 0, None, decision,
                tipo_pagina=tipo.value, aceptada=False, ids_oferta=[],
            ))
            return

        if not respuesta.ok:
            cont.errores += 1
            error = respuesta.error or f"HTTP {respuesta.estado_http}"
            transitorio = respuesta.estado_http == 0 or respuesta.estado_http >= 500
            if not transitorio:
                indice.anotar_intento(url)
            self._descartar_pagina(
                carpeta, fuente, cont, url, tipo, f"respuesta no exitosa: {error}",
                None, 0, [],
            )
            self.almacen.registrar(carpeta, self._registro(
                fuente, url, respuesta.url_final, fecha, respuesta.estado_http,
                respuesta.content_type, None, None, None, None, [error],
                0, None, decision, tipo_pagina=tipo.value, aceptada=False,
                error_transitorio=transitorio, ids_oferta=[],
            ))
            return

        cont.respuestas_ok += 1

        if "text/html" not in respuesta.content_type:
            hash12 = hash_contenido(respuesta.contenido)
            cont.paginas_descartadas += 1
            cont.contar_tipo(tipo)
            motivo = f"respuesta no HTML ({respuesta.content_type or 'sin content-type'})"
            self._descartar_pagina(
                carpeta, fuente, cont, url, tipo, motivo, hash12, 0, [],
            )
            indice.anotar(url, hash12)
            self.almacen.registrar(carpeta, self._registro(
                fuente, url, respuesta.url_final, fecha, respuesta.estado_http,
                respuesta.content_type, None, None, hash12, None, [motivo],
                0, None, decision, tipo_pagina=tipo.value, aceptada=False,
                ids_oferta=[],
            ))
            return

        html = self._texto(respuesta)
        contenido = extraer_contenido(html, respuesta.url_final)
        nombres = extraccion.nombres_estructurados(html)
        evidencia = EvidenciaPagina(
            titulo=contenido.titulo,
            descripcion=contenido.descripcion,
            encabezados=contenido.encabezados,
            nombres_estructurados=nombres,
            texto=contenido.texto,
        )
        veredicto = sitio.clasificar_pagina(url, tipo, evidencia, self.lexico)
        hash12 = hash_contenido(respuesta.contenido)

        if not veredicto.relevante:
            cont.paginas_descartadas += 1
            cont.contar_tipo(veredicto.tipo)
            motivo = "; ".join(veredicto.motivos) or "página no relevante"
            self._descartar_pagina(
                carpeta, fuente, cont, url, veredicto.tipo, motivo,
                hash12, veredicto.puntuacion, veredicto.terminos,
            )
            indice.anotar(url, hash12)
            self.almacen.registrar(carpeta, self._registro(
                fuente, url, respuesta.url_final, fecha, respuesta.estado_http,
                respuesta.content_type, None, None, hash12, None,
                [motivo] + list(decision.advertencias), 0, None, decision,
                titulo=contenido.titulo, descripcion=contenido.descripcion,
                tipo_pagina=veredicto.tipo.value, aceptada=False, ids_oferta=[],
            ))
            return

        # Página aceptada: solo ahora se conserva su contenido.
        ruta_crudo, hash12, _ = self.almacen.guardar_crudo(
            carpeta, url, respuesta.contenido
        )
        ruta_texto = self.almacen.guardar_texto(
            carpeta, url, hash12, contenido.texto
        )
        rutas_activos: list[str] = []
        mapa_activos = self._guardar_activos(
            sitio, carpeta, html, respuesta.url_final, rutas_activos, cont
        )
        registros = sitio.extraer(
            html, contenido.texto, respuesta.url_final, fecha, fuente,
            activos=mapa_activos,
        )
        cont.registros_extraidos += len(registros)

        aceptados, descartes = sitio.filtrar_registros(registros, self.lexico)
        cont.registros_descartados += len(descartes)
        for descarte in descartes:
            self._descartar_registro(
                carpeta, fuente, cont, descarte, respuesta.url_final, tipo, hash12, fecha,
            )

        # La identidad debe existir antes de deduplicar; si no, todas las
        # ofertas de una misma página colapsarían en la URL de la página.
        for registro in aceptados:
            registro["id_oferta"] = sitio.id_oferta(registro)

        nuevos, duplicados = self._deduplicar(aceptados, indice)
        cont.registros_duplicados += len(duplicados)
        for registro in duplicados:
            self._descartar_registro(
                carpeta, fuente, cont, {
                    "registro": registro,
                    "motivo": "oferta duplicada por id_oferta/contenido",
                    "puntuacion": 0,
                    "terminos": [],
                }, respuesta.url_final, tipo, hash12, fecha,
            )

        for registro in nuevos:
            registro["hash_contenido"] = hash12
            registro["tipo_pagina"] = sitio.tipo_pagina_registro(veredicto.tipo)
            registro["tipo_oferta"] = sitio.tipo_oferta(registro)
            registro["id_oferta"] = sitio.id_oferta(registro)
            registro["url_oferta"] = sitio.url_oferta(registro)
            registro["availability"] = (registro.get("campos") or {}).get(
                "availability"
            )

        self.almacen.registrar_datos(carpeta, nuevos)
        indice.anotar_ofertas(r["id_oferta"] for r in nuevos)
        cont.registros_aceptados += len(nuevos)
        if veredicto.cuenta and nuevos:
            cont.paginas_aceptadas += 1
            cont.paginas_nuevas += 1
        cont.contar_tipo(veredicto.tipo)

        advertencias = list(contenido.advertencias) + list(decision.advertencias)
        self.almacen.registrar(carpeta, self._registro(
            fuente, url, respuesta.url_final, fecha, respuesta.estado_http,
            respuesta.content_type,
            self.almacen.ruta_relativa(ruta_crudo, self.almacen.raiz),
            self.almacen.ruta_relativa(ruta_texto, self.almacen.raiz),
            hash12, None, advertencias, 0, None, decision,
            titulo=contenido.titulo, descripcion=contenido.descripcion,
            registros_estructurados=len(registros), activos=rutas_activos,
            tipo_pagina=veredicto.tipo.value, aceptada=True,
            ids_oferta=[r["id_oferta"] for r in nuevos],
            registros_aceptados=len(nuevos),
            registros_descartados=len(descartes) + len(duplicados),
            relevante_pagina=veredicto.relevante,
            puntuacion_pagina=veredicto.puntuacion,
        ))

    def _deduplicar(self, registros: list[dict], indice) -> tuple[list[dict], list[dict]]:
        """Dedup por ``id_oferta``; respaldo por contenido solo dentro de la página."""
        nuevos: list[dict] = []
        duplicados: list[dict] = []
        vistos_id: set[str] = set()
        vistos_contenido: set[tuple] = set()
        for registro in registros:
            identidad = registro.get("id_oferta") or canonicalizar(
                str(registro.get("url_origen") or "")
            )
            if identidad and (indice.oferta_vista(identidad) or identidad in vistos_id):
                duplicados.append(registro)
                continue
            campos = registro.get("campos") or {}
            contenido = (
                campos.get("product_name"),
                campos.get("price"),
                campos.get("currency"),
            )
            if contenido != (None, None, None) and contenido in vistos_contenido:
                duplicados.append(registro)
                continue
            if identidad:
                vistos_id.add(identidad)
            if contenido != (None, None, None):
                vistos_contenido.add(contenido)
            nuevos.append(registro)
        return nuevos, duplicados

    # -- descartes -------------------------------------------------------
    def _descartar_pagina(
        self,
        carpeta: Path,
        fuente: cfg.Fuente,
        cont: Contadores,
        url: str,
        tipo: TipoPagina | None,
        motivo: str,
        hash12: str | None,
        puntuacion: int,
        terminos: list[str],
    ) -> None:
        self.almacen.registrar_descartes(carpeta, [{
            "nivel": "pagina",
            "fuente_id": fuente.id,
            "url": url,
            "url_canonica": canonicalizar(url),
            "tipo_pagina": tipo.value if tipo else None,
            "id_oferta": None,
            "motivo": motivo,
            "puntuacion": puntuacion,
            "terminos": terminos,
            "hash_contenido": hash12,
            "fecha_consulta": ahora_utc(),
        }])

    def _descartar_registro(
        self,
        carpeta: Path,
        fuente: cfg.Fuente,
        cont: Contadores,
        descarte: dict,
        url: str,
        tipo: TipoPagina,
        hash12: str | None,
        fecha: str,
    ) -> None:
        registro = descarte.get("registro") or {}
        campos = registro.get("campos") or {}
        adicionales = registro.get("campos_adicionales") or {}
        self.almacen.registrar_descartes(carpeta, [{
            "nivel": "registro",
            "fuente_id": fuente.id,
            "url": registro.get("url_origen") or url,
            "url_canonica": canonicalizar(registro.get("url_origen") or url),
            "tipo_pagina": tipo.value,
            "id_oferta": (
                registro.get("id_oferta")
                or adicionales.get("id_oferta")
                or adicionales.get("id")
                or adicionales.get("id_catalogo")
            ),
            "product_name": campos.get("product_name"),
            "motivo": descarte.get("motivo", "registro rechazado"),
            "puntuacion": descarte.get("puntuacion", 0),
            "terminos": descarte.get("terminos", []),
            "hash_contenido": hash12,
            "fecha_consulta": fecha,
        }])

    # -- activos ---------------------------------------------------------
    def _guardar_activos(
        self, sitio: Sitio, carpeta: Path, html: str, url: str,
        rutas: list[str], cont: Contadores | None = None,
    ) -> dict[str, str]:
        """Obtiene y conserva los activos declarados por el sitio."""
        mapa: dict[str, str] = {}
        for declarado in sitio.activos(html, url):
            activo_url = urljoin(url, declarado)
            if not self._mismo_sitio(activo_url, sitio.dominio):
                continue
            respuesta = self._obtener_activo(activo_url)
            if not respuesta.ok:
                continue
            ruta, _, _ = self.almacen.guardar_activo(carpeta, activo_url, respuesta.contenido)
            rutas.append(self.almacen.ruta_relativa(ruta, self.almacen.raiz))
            mapa[activo_url] = respuesta.texto()
            self.resumen.activos += 1
            if cont is not None:
                cont.activos += 1
        return mapa

    # -- resumen ---------------------------------------------------------
    def _escribir_resumen(self) -> Path:
        nuevas = {fid: c.a_dict() for fid, c in self.resumen.fuentes.items()}
        # Al recolectar un subconjunto de fuentes, conservar los contadores de
        # las fuentes que no participaron en esta pasada.
        previas: dict[str, dict] = {}
        destino = self.almacen.raiz / "resumen.json"
        if destino.is_file():
            try:
                previas = json.loads(destino.read_text(encoding="utf-8")).get("fuentes") or {}
            except (json.JSONDecodeError, OSError):
                previas = {}
        fuentes = {
            fid: datos for fid, datos in previas.items() if fid not in nuevas
        }
        fuentes.update(nuevas)
        fuentes = dict(sorted(fuentes.items()))
        totales: dict[str, object] = {
            "candidatos_generados": sum(f.get("candidatos_generados", 0) for f in fuentes.values()),
            "intentos_red": sum(f.get("intentos_red", 0) for f in fuentes.values()),
            "errores": sum(f.get("errores", 0) for f in fuentes.values()),
            "paginas_aceptadas": sum(f.get("paginas_aceptadas", 0) for f in fuentes.values()),
            "paginas_descartadas": sum(f.get("paginas_descartadas", 0) for f in fuentes.values()),
            "registros_aceptados": sum(f.get("registros_aceptados", 0) for f in fuentes.values()),
            "registros_descartados": sum(f.get("registros_descartados", 0) for f in fuentes.values()),
            "registros_duplicados": sum(f.get("registros_duplicados", 0) for f in fuentes.values()),
            "objetivo_alcanzado": {
                fid: bool(f.get("objetivo_alcanzado")) for fid, f in fuentes.items()
            },
        }
        resumen = {
            "fecha": ahora_utc(),
            "fase": "todo",
            "configuracion": {
                "delay": self.fetcher.delay,
                "timeout": self.fetcher.timeout,
                "reintentos": self.fetcher.reintentos,
                "respetar_robots": self.fetcher.respetar_robots,
                "ventana_dias": self.opciones.ventana_dias,
                "max_intentos": self.opciones.max_intentos,
                "objetivo_paginas": self.opciones.objetivo_paginas,
                "max_paginas": self.opciones.max_paginas,
                "simular": self.opciones.simular,
                "forzar": self.opciones.forzar,
            },
            "git_commit": git_commit(RAIZ_REPOSITORIO),
            "lexico_hash": relevancia.hash_lexico(),
            "fuentes": fuentes,
            "totales": totales,
        }
        return self.almacen.escribir_resumen(resumen)

    # -- flujo anterior: descubrimiento ----------------------------------
    def descubrir(self, fuentes) -> Resumen:
        for fuente in fuentes:
            print(f"Fuente {fuente.descripcion()}")
            self._descubrir_fuente(fuente)
        return self.resumen

    def _descubrir_fuente(self, fuente: cfg.Fuente) -> None:
        sitio = sitios.para_fuente(fuente)
        carpeta = self.almacen.carpeta_fuente(fuente.id, fuente.nombre)

        if self.opciones.simular:
            semillas = self.opciones.urls_semilla or sitio.semillas_explicitas or (fuente.url,)
            for url in semillas:
                print(f"  [simulado] semilla {fuente.id} -> {url}")
            return

        decision = self._evaluar_politica(fuente)
        if not decision.puede_recolectar:
            self.resumen.omitidas_por_politica += 1
            self.resumen.detalle.append(f"{fuente.id} {fuente.nombre}: OMITIDA — {decision.motivo}")
            print(f"  omitida: {decision.motivo}")
            return

        texto_robots = self.fetcher.texto_robots(fuente.url)
        semillas = self.opciones.urls_semilla or sitio.semillas(self.fetcher, texto_robots) or (fuente.url,)

        indice = self.almacen.cargar_indice(carpeta)
        previos = {c["url"]: c for c in self.almacen.leer_candidatos(carpeta)}
        candidatos: list[dict] = []
        vistos: set[str] = set()

        print(f"  sitio: {sitio.nombre} | semillas: {len(semillas)}")
        semillas_unicas: list[str] = []
        for semilla in semillas:
            if semilla in vistos:
                continue
            vistos.add(semilla)
            semillas_unicas.append(semilla)
            candidatos.append(
                self._candidato(semilla, sitio, origen="semilla", previo=previos.get(semilla))
            )

        for url, candidato_previo in previos.items():
            if url in vistos:
                continue
            vistos.add(url)
            candidatos.append(candidato_previo)

        for semilla in semillas_unicas:
            if not self.opciones.forzar and indice.url_intentada(semilla):
                self.resumen.omitidas_por_dedup += 1
                print(f"  semilla ya recolectada (dedup): {semilla}")
                continue
            if self.resumen.paginas_ok >= self.opciones.max_paginas:
                print("  límite de páginas alcanzado durante el descubrimiento")
                break

            ok, contenido = self._procesar(fuente, sitio, semilla, decision, carpeta, indice)
            if not ok:
                continue
            for enlace in self._enlaces(contenido, sitio.dominio):
                if enlace in vistos:
                    continue
                vistos.add(enlace)
                candidatos.append(
                    self._candidato(enlace, sitio, origen="enlace", previo=previos.get(enlace))
                )

        self.almacen.escribir_candidatos(carpeta, candidatos)
        self.resumen.candidatos += len(candidatos)
        pendientes = sum(1 for c in candidatos if c.get("incluir") is None)
        self.resumen.detalle.append(
            f"{fuente.id} {fuente.nombre}: descubrimiento — {len(candidatos)} candidatos "
            f"({pendientes} por aprobar, {len(candidatos) - pendientes} semillas)"
        )
        print(f"  candidatos: {len(candidatos)} ({pendientes} por aprobar) -> candidatos.jsonl")

    def _candidato(self, url: str, sitio: Sitio, origen: str, previo: dict | None = None) -> dict:
        if origen == "semilla":
            veredicto = relevancia.Veredicto(
                True, self.lexico.umbral, [], ["semilla declarada por el sitio"]
            )
        else:
            partes = urlparse(url)
            camino = partes.path + (f"?{partes.query}" if partes.query else "")
            veredicto = self.lexico.evaluar(url=camino)
            if not veredicto.relevante and sitio.relevante_por_patron(url):
                veredicto = relevancia.Veredicto(
                    True, max(veredicto.puntuacion, self.lexico.umbral),
                    veredicto.terminos,
                    veredicto.motivos + ["patrón relevante declarado por el sitio"],
                )
        if previo and previo.get("incluir") is not None:
            incluir = previo["incluir"]
        else:
            incluir = True if origen == "semilla" else None
        return {
            "url": url,
            "url_canonica": canonicalizar(url),
            "origen": origen,
            "relevante": veredicto.relevante,
            "puntuacion": veredicto.puntuacion,
            "terminos": veredicto.terminos,
            "motivos": veredicto.motivos,
            "incluir": incluir,
        }

    # -- flujo anterior: recolección de aprobados ------------------------
    def recolectar(self, fuentes, aprobar_relevantes: bool = False) -> Resumen:
        for fuente in fuentes:
            print(f"Fuente {fuente.descripcion()}")
            self._recolectar_fuente(fuente, aprobar_relevantes)
        return self.resumen

    def _recolectar_fuente(self, fuente: cfg.Fuente, aprobar_relevantes: bool) -> None:
        sitio = sitios.para_fuente(fuente)
        carpeta = self.almacen.carpeta_fuente(fuente.id, fuente.nombre)

        decision = self._evaluar_politica(fuente)
        if not decision.puede_recolectar:
            self.resumen.omitidas_por_politica += 1
            self.resumen.detalle.append(f"{fuente.id} {fuente.nombre}: OMITIDA — {decision.motivo}")
            print(f"  omitida: {decision.motivo}")
            return

        candidatos = self.almacen.leer_candidatos(carpeta)
        if not candidatos:
            print("  sin candidatos; ejecute primero --descubrir")
            return

        aprobados = [
            c for c in candidatos
            if c.get("incluir") is True or (aprobar_relevantes and c.get("relevante") and c.get("incluir") is not False)
        ]
        self.resumen.aprobadas += len(aprobados)
        print(f"  aprobados para descargar: {len(aprobados)} de {len(candidatos)}")

        indice = self.almacen.cargar_indice(carpeta)

        procesadas = 0
        for candidato in aprobados:
            if procesadas >= self.opciones.max_paginas:
                print("  límite de páginas alcanzado")
                break
            url = candidato["url"]
            if self.opciones.simular:
                print(f"  [simulado] descargar {url}")
                continue
            if not self.opciones.forzar and indice.url_intentada(url):
                self.resumen.omitidas_por_dedup += 1
                continue
            procesadas += 1
            self._procesar(fuente, sitio, url, decision, carpeta, indice)

        self.resumen.detalle.append(
            f"{fuente.id} {fuente.nombre}: {procesadas} página(s) descargada(s) de {len(aprobados)} aprobadas"
        )

    # -- procesamiento del flujo anterior --------------------------------
    def _procesar(
        self,
        fuente: cfg.Fuente,
        sitio: Sitio,
        url: str,
        decision: politica.Decision,
        carpeta: Path,
        indice,
        nivel: int = 0,
        padre: str | None = None,
    ) -> tuple[bool, Contenido | None]:
        """Obtiene, conserva y analiza una URL. Devuelve (ok, contenido)."""
        fecha = ahora_utc()
        respuesta = self._obtener(url)

        if respuesta.error == "bloqueado_por_robots.txt":
            self.resumen.omitidas_robots += 1
            self.almacen.registrar(
                carpeta,
                self._registro(fuente, url, url, fecha, 0, "", None, None, None,
                               None, ["robots.txt no permite la consulta"], nivel, padre, decision),
            )
            return False, None

        if not respuesta.ok:
            self.resumen.paginas_error += 1
            self.almacen.registrar(
                carpeta,
                self._registro(fuente, url, respuesta.url_final, fecha, respuesta.estado_http,
                               respuesta.content_type, None, None, None, None,
                               [respuesta.error or "respuesta no exitosa"], nivel, padre, decision),
            )
            return False, None

        if "text/html" not in respuesta.content_type:
            ruta, hash12, _ = self.almacen.guardar_crudo(carpeta, url, respuesta.contenido)
            indice.anotar(url, hash12)
            self.resumen.paginas_ok += 1
            self.almacen.registrar(
                carpeta,
                self._registro(fuente, url, respuesta.url_final, fecha, respuesta.estado_http,
                               respuesta.content_type, self.almacen.ruta_relativa(ruta, self.almacen.raiz),
                               None, hash12, None, [], nivel, padre, decision),
            )
            return True, None

        html = respuesta.texto()
        contenido = extraer_contenido(html, respuesta.url_final)
        ruta_crudo, hash12, ya_existia = self.almacen.guardar_crudo(carpeta, url, respuesta.contenido)
        ruta_texto = None
        registros: list[dict] = []
        rutas_activos: list[str] = []
        if not (ya_existia and indice.hash_visto(hash12)):
            ruta_texto = self.almacen.guardar_texto(carpeta, url, hash12, contenido.texto)
            mapa_activos = self._guardar_activos(
                sitio, carpeta, html, respuesta.url_final, rutas_activos
            )
            registros = sitio.extraer(
                html, contenido.texto, respuesta.url_final, fecha, fuente, activos=mapa_activos
            )
            for registro in registros:
                registro["hash_contenido"] = hash12
                registro["relevancia"] = self._relevancia_registro(registro)
            self.almacen.registrar_datos(carpeta, registros)
            self.resumen.datos_estructurados += len(registros)

        indice.anotar(url, hash12)
        advertencias = list(contenido.advertencias) + list(decision.advertencias)
        if ya_existia:
            advertencias.append("contenido idéntico ya almacenado (deduplicado)")
        self.resumen.paginas_ok += 1
        self.almacen.registrar(
            carpeta,
            self._registro(
                fuente, url, respuesta.url_final, fecha, respuesta.estado_http,
                respuesta.content_type,
                self.almacen.ruta_relativa(ruta_crudo, self.almacen.raiz),
                self.almacen.ruta_relativa(ruta_texto, self.almacen.raiz) if ruta_texto else None,
                hash12, None, advertencias, nivel, padre, decision,
                titulo=contenido.titulo, descripcion=contenido.descripcion,
                registros_estructurados=len(registros), activos=rutas_activos,
            ),
        )
        return True, contenido

    def _relevancia_registro(self, registro: dict) -> dict:
        campos = registro.get("campos") or {}
        texto = " ".join([
            str(campos.get("product_name") or ""),
            str(campos.get("description") or ""),
            str(registro.get("evidencia_cruda") or ""),
        ])
        veredicto = self.lexico.evaluar(titulo=str(campos.get("product_name") or ""), texto=texto)
        return {
            "relevante": veredicto.relevante,
            "puntuacion": veredicto.puntuacion,
            "terminos": veredicto.terminos,
        }

    def _enlaces(self, contenido: Contenido | None, dominio: str) -> list[str]:
        if contenido is None:
            return []
        return [
            url for url in contenido.enlaces
            if self._mismo_sitio(url, dominio) and self._crawleable(url)
        ]

    # -- registro de manifiesto -----------------------------------------
    def _registro(
        self, fuente, url_solicitada, url_final, fecha, estado, content_type,
        ruta_crudo, ruta_texto, hash12, _contenido_hash_extra, advertencias, nivel, url_padre, decision,
        titulo="", descripcion="", registros_estructurados=0, activos: list[str] | None = None,
        **extra,
    ) -> dict:
        registro = {
            "fuente_id": fuente.id,
            "fuente_nombre": fuente.nombre,
            "categoria": fuente.categoria,
            "tipo": fuente.tipo,
            "estado_fuente": fuente.estado,
            "url_solicitada": url_solicitada,
            "url_canonica": canonicalizar(url_solicitada),
            "url_origen": url_final,
            "fecha_consulta": fecha,
            "estado_http": estado,
            "content_type": content_type,
            "nivel_profundidad": nivel,
            "url_padre": url_padre,
            "titulo": titulo,
            "descripcion_meta": descripcion,
            "ruta_crudo": ruta_crudo,
            "ruta_texto": ruta_texto,
            "hash_contenido": hash12,
            "registros_estructurados": registros_estructurados,
            "activos": activos or [],
            "datos_esperados": list(fuente.datos_esperados),
            "notas_fuente": fuente.notas,
            "advertencias": advertencias,
            "politica": {
                "puede_recolectar": decision.puede_recolectar,
                "motivo": decision.motivo,
                "aviso_legal": decision.aviso_legal,
                "autorizado_por": decision.autorizado_por,
            },
            "reglas_aplicadas": self.config.reglas_globales,
            "metodo_obtencion": self._metodo_obtencion(),
        }
        registro.update(extra)
        return registro

    def _metodo_obtencion(self) -> str:
        return "GET HTTP; robots.txt respetado" if self.fetcher.respetar_robots else "GET HTTP"


def recolectar(
    config, almacen, fetcher, opciones, fuentes, fase: str,
    aprobar_relevantes: bool = False,
) -> Resumen:
    recolector = Recolector(config, almacen, fetcher, opciones)
    if fase == "todo":
        return recolector.todo(fuentes)
    if fase == "recolectar":
        return recolector.recolectar(fuentes, aprobar_relevantes)
    return recolector.descubrir(fuentes)
