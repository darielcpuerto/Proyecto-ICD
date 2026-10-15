"""Orquestación de la recolección para una o varias fuentes.

Recorre cada fuente partiendo de sus URLs semilla, sigue únicamente enlaces del
mismo dominio hasta la profundidad indicada y guarda cada observación con su
procedencia. Además de conservar el contenido crudo y su texto derivado, aplica
la extracción estructurada (`extraccion.py`) y guarda los registros en
`datos.jsonl`.

Antes de recolectar una fuente aplica la política de acceso (`politica.py`),
que combina robots.txt, avisos legales y excepciones registradas.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from . import config as cfg
from . import adaptadores, extraccion, extractores, politica, render
from .extractor import es_imagen, extraer
from .fetcher import Fetcher, Respuesta
from .storage import Almacen, ahora_utc


@dataclass
class Opciones:
    """Parámetros de ejecución de la recolección."""

    profundidad: int = 0
    max_paginas: int = 40
    descargar_imagenes: bool = True
    max_imagenes_por_pagina: int = 10
    simular: bool = False
    urls_semilla: tuple[str, ...] = ()
    renderizar: bool = False
    executable_chromium: str | None = None


@dataclass
class Resumen:
    """Recuento de lo recolectado en una ejecución."""

    paginas_ok: int = 0
    paginas_error: int = 0
    imagenes: int = 0
    omitidas_robots: int = 0
    datos_estructurados: int = 0
    fuentes_omitidas_por_politica: int = 0
    paginas_renderizadas: int = 0
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
        self.adaptadores = adaptadores.cargar()
        self._renderizador: render.RenderizadorJS | None = None
        self._renderizado_deshabilitado = False
        self._obtenido_con_js = False
        self._aviso_renderizado = False

    # -- renderizado opcional -------------------------------------------
    def _obtener_renderizador(self) -> "render.RenderizadorJS | None":
        if self._renderizado_deshabilitado:
            return None
        if self._renderizador is not None:
            if self._renderizador.utilizable():
                return self._renderizador
            self._renderizador = None
            self._renderizado_deshabilitado = True
            return None
        if not render.disponible():
            print("  aviso: " + render.INSTRUCCIONES)
            return None
        try:
            self._renderizador = render.RenderizadorJS(
                user_agent=self.fetcher.user_agent,
                executable_path=self.opciones.executable_chromium,
            )
        except render.ErrorRenderizado as exc:
            print(f"  aviso: no se pudo iniciar el renderizador: {exc}")
            return None
        return self._renderizador

    def _avisar_caida_renderizado(self, motivo: str | None) -> None:
        if not self._aviso_renderizado:
            print(f"  aviso: el renderizado con JavaScript se detuvo: {motivo}")
            print("  aviso: se continúa con la obtención estática para las páginas restantes.")
            self._aviso_renderizado = True

    def _obtener(self, url: str, usar_js: bool):
        self._obtenido_con_js = False
        if usar_js:
            if not self.fetcher.permitido_por_robots(url):
                return Respuesta(url_solicitada=url, url_final=url, estado_http=0,
                                 content_type="", contenido=b"", encoding="utf-8",
                                 error="bloqueado_por_robots.txt")
            renderizador = self._obtener_renderizador()
            if renderizador is not None:
                respuesta = renderizador.obtener(url)
                if respuesta.ok:
                    self._obtenido_con_js = True
                    return respuesta
                if not renderizador.utilizable():
                    self._avisar_caida_renderizado(renderizador.motivo_fallo())
                    renderizador.cerrar()
                    self._renderizador = None
                    self._renderizado_deshabilitado = True
                    return self.fetcher.obtener(url)
                return respuesta
        return self.fetcher.obtener(url)

    def cerrar(self) -> None:
        if self._renderizador is not None:
            self._renderizador.cerrar()
            self._renderizador = None

    # -- internos -------------------------------------------------------
    @staticmethod
    def _mismo_dominio(url: str, netloc: str) -> bool:
        return urlparse(url).netloc == netloc

    @staticmethod
    def _crawleable(url: str) -> bool:
        return not es_imagen(url) and not urlparse(url).path.lower().endswith(
            (".pdf", ".zip", ".rar", ".doc", ".docx", ".xls", ".xlsx")
        )

    def _evaluar_politica(self, fuente: cfg.Fuente) -> politica.Decision:
        robots_ok = self.fetcher.permitido_por_robots(fuente.url)
        texto_robots = self.fetcher.texto_robots(fuente.url)
        return politica.evaluar(fuente, robots_ok, texto_robots, self.overrides.get(fuente.id))

    def _descargar_imagenes(self, carpeta: Path, contenido, url: str, fecha: str) -> list[str]:
        guardadas: list[str] = []
        for imagen_url in contenido.imagenes[: self.opciones.max_imagenes_por_pagina]:
            if self.opciones.simular:
                continue
            respuesta = self.fetcher.obtener(imagen_url)
            if respuesta.ok and "image" in respuesta.content_type:
                ruta = self.almacen.guardar_imagen(
                    carpeta, imagen_url, fecha, respuesta.contenido, respuesta.content_type
                )
                guardadas.append(self.almacen.ruta_relativa(ruta, self.almacen.raiz))
                self.resumen.imagenes += 1
        return guardadas

    # -- recolección ----------------------------------------------------
    def recolectar_fuente(self, fuente: cfg.Fuente) -> None:
        semillas = self.opciones.urls_semilla or (fuente.url,)

        if self.opciones.simular:
            # En modo simulado no se realizan peticiones de red.
            for url in semillas:
                print(f"  [simulado] {fuente.id} -> {url} (nivel 0)")
            self.resumen.detalle.append(f"{fuente.id} {fuente.nombre}: simulado")
            return

        decision = self._evaluar_politica(fuente)
        if not decision.puede_recolectar:
            self.resumen.fuentes_omitidas_por_politica += 1
            self.resumen.detalle.append(
                f"{fuente.id} {fuente.nombre}: OMITIDA — {decision.motivo}"
            )
            print(f"  omitida: {decision.motivo}")
            return

        semillas = self.opciones.urls_semilla
        if not semillas:
            texto_robots = self.fetcher.texto_robots(fuente.url)
            semillas = adaptadores.semillas_para(
                fuente, self.fetcher, texto_robots, self.adaptadores
            ) or (fuente.url,)
        print(f"  semillas: {len(semillas)}")

        adaptador = adaptadores.obtener(fuente.id, self.adaptadores) or {}
        usar_js = self.opciones.renderizar or bool(adaptador.get("requiere_js"))
        if adaptador.get("requiere_js") and not render.disponible():
            print("  aviso: la fuente requiere JavaScript y Playwright no está disponible; "
                  "se usará la obtención estática.")
            usar_js = False

        carpeta = self.almacen.carpeta_fuente(fuente.id, fuente.nombre)
        netloc = urlparse(semillas[0]).netloc

        pendientes: deque[tuple[str, int, str | None]] = deque(
            (url, 0, None) for url in semillas
        )
        visitadas: set[str] = set()
        paginas = 0

        while pendientes and paginas < self.opciones.max_paginas:
            url, nivel, padre = pendientes.popleft()
            if url in visitadas:
                continue
            visitadas.add(url)
            paginas += 1

            fecha = ahora_utc()

            respuesta = self._obtener(url, usar_js)
            if self._obtenido_con_js and respuesta.ok:
                self.resumen.paginas_renderizadas += 1

            if respuesta.error == "bloqueado_por_robots.txt":
                self.resumen.omitidas_robots += 1
                self.almacen.registrar(
                    carpeta,
                    self._registro(fuente, url, url, fecha, 0, "", None, None,
                                   ["robots.txt no permite la consulta"], [], nivel, padre, decision),
                )
                continue

            if not respuesta.ok:
                self.resumen.paginas_error += 1
                self.almacen.registrar(
                    carpeta,
                    self._registro(fuente, url, respuesta.url_final, fecha, respuesta.estado_http,
                                   respuesta.content_type, None, None,
                                   [respuesta.error or "respuesta no exitosa"], [], nivel, padre, decision),
                )
                continue

            if "text/html" not in respuesta.content_type:
                ruta = self.almacen.guardar_crudo(carpeta, url, fecha, respuesta.contenido)
                self.resumen.paginas_ok += 1
                self.almacen.registrar(
                    carpeta,
                    self._registro(fuente, url, respuesta.url_final, fecha, respuesta.estado_http,
                                   respuesta.content_type, self.almacen.ruta_relativa(ruta, self.almacen.raiz),
                                   None, [], [], nivel, padre, decision),
                )
                continue

            html = respuesta.texto()
            contenido = extraer(html, respuesta.url_final)
            ruta_crudo = self.almacen.guardar_crudo(carpeta, url, fecha, respuesta.contenido)
            ruta_texto = self.almacen.guardar_texto(carpeta, url, fecha, contenido.texto)
            imagenes = self._descargar_imagenes(carpeta, contenido, url, fecha) if self.opciones.descargar_imagenes else []

            if adaptador.get("extractor"):
                registros = extractores.extraer(
                    adaptador["extractor"], html, contenido.texto, respuesta.url_final, fecha, fuente
                )
            else:
                registros = extraccion.extraer(html, contenido.texto, respuesta.url_final, fecha, fuente)
            self.almacen.registrar_datos(carpeta, registros)
            self.resumen.datos_estructurados += len(registros)

            advertencias = list(contenido.advertencias) + list(decision.advertencias)
            if self._obtenido_con_js:
                advertencias.append("contenido obtenido mediante renderizado JavaScript (Playwright)")
            self.resumen.paginas_ok += 1
            self.almacen.registrar(
                carpeta,
                self._registro(
                    fuente, url, respuesta.url_final, fecha, respuesta.estado_http, respuesta.content_type,
                    self.almacen.ruta_relativa(ruta_crudo, self.almacen.raiz),
                    self.almacen.ruta_relativa(ruta_texto, self.almacen.raiz),
                    advertencias, imagenes, nivel, padre, decision,
                    titulo=contenido.titulo, descripcion=contenido.descripcion,
                    registros_estructurados=len(registros),
                ),
            )

            if nivel < self.opciones.profundidad:
                self._encolar_enlaces(pendientes, respuesta.url_final, nivel, netloc, contenido.enlaces)

        self.resumen.detalle.append(
            f"{fuente.id} {fuente.nombre}: {paginas} página(s) procesada(s)"
        )

    def _encolar_enlaces(self, pendientes, url, nivel, netloc, enlaces) -> None:
        for enlace in enlaces:
            if self._mismo_dominio(enlace, netloc) and self._crawleable(enlace):
                pendientes.append((enlace, nivel + 1, url))

    def _metodo_obtencion(self) -> str:
        metodo = "GET HTTP; robots.txt respetado" if self.fetcher.respetar_robots else "GET HTTP"
        if self._obtenido_con_js:
            metodo += " + renderizado JS (Playwright)"
        return metodo

    def _registro(
        self, fuente, url_solicitada, url_final, fecha, estado, content_type,
        ruta_crudo, ruta_texto, advertencias, imagenes, nivel, url_padre, decision,
        titulo="", descripcion="", registros_estructurados=0,
    ) -> dict:
        return {
            "fuente_id": fuente.id,
            "fuente_nombre": fuente.nombre,
            "categoria": fuente.categoria,
            "tipo": fuente.tipo,
            "estado_fuente": fuente.estado,
            "url_solicitada": url_solicitada,
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
            "imagenes_descargadas": imagenes,
            "registros_estructurados": registros_estructurados,
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


def recolectar(config: cfg.Configuracion, almacen: Almacen, fetcher: Fetcher, opciones: Opciones, fuentes) -> Resumen:
    recolector = Recolector(config, almacen, fetcher, opciones)
    try:
        for fuente in fuentes:
            print(f"Fuente {fuente.descripcion()}")
            recolector.recolectar_fuente(fuente)
    finally:
        recolector.cerrar()
    return recolector.resumen
