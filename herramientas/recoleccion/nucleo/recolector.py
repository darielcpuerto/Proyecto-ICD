"""Orquestación de la recolección en dos fases.

1. **Descubrimiento** (``descubrir``): obtiene las semillas declaradas por el
   sitio, las conserva y recoge los enlaces del mismo dominio; puntúa su
   relevancia y los escribe en ``candidatos.jsonl`` (pendientes de aprobación).
2. **Recolección** (``recolectar``): descarga **solo** los candidatos aprobados
   (por archivo o por umbral) y los conserva.

En ambas fases se aplica la política de acceso, la deduplicación por contenido
y el límite de páginas por fuente. No se descargan imágenes ni se usa navegador:
el contenido se obtiene con HTTP y, cuando el sitio lo requiere, de sus *activos*
declarados (por ejemplo, el bundle JavaScript que contiene el catálogo).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .. import sitios
from ..sitios.base import Sitio, dominio_normalizado
from . import config as cfg
from . import politica, relevancia
from .almacen import Almacen, ahora_utc
from .contenido import Contenido, es_imagen, extraer as extraer_contenido
from .fetcher import Fetcher, Respuesta

EXTENSIONES_NO_CRAWLEABLES = (".pdf", ".zip", ".rar", ".doc", ".docx", ".xls", ".xlsx")


@dataclass
class Opciones:
    """Parámetros de ejecución de la recolección."""

    max_paginas: int = 250
    simular: bool = False
    urls_semilla: tuple[str, ...] = ()
    forzar: bool = False
    umbral_relevancia: int | None = None


@dataclass
class Resumen:
    """Recuento de lo recolectado en una ejecución."""

    paginas_ok: int = 0
    paginas_error: int = 0
    omitidas_robots: int = 0
    omitidas_por_dedup: int = 0
    omitidas_por_politica: int = 0
    candidatos: int = 0
    aprobadas: int = 0
    datos_estructurados: int = 0
    activos: int = 0
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

    # -- procesamiento de una página ------------------------------------
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

    def _guardar_activos(
        self, sitio: Sitio, carpeta: Path, html: str, url: str, rutas: list[str]
    ) -> dict[str, str]:
        """Obtiene y conserva los activos declarados por el sitio.

        Devuelve un mapa ``url_activo -> texto`` para que el sitio extraiga datos
        de ellos (por ejemplo, el bundle JavaScript que contiene el catálogo).
        """
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
        return mapa

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

    # -- fase 1: descubrimiento -----------------------------------------
    def descubrir(self, fuentes) -> Resumen:
        for fuente in fuentes:
            print(f"Fuente {fuente.descripcion()}")
            self._descubrir_fuente(fuente)
        return self.resumen

    def _descubrir_fuente(self, fuente: cfg.Fuente) -> None:
        sitio = sitios.para_fuente(fuente)
        carpeta = self.almacen.carpeta_fuente(fuente.id, fuente.nombre)

        if self.opciones.simular:
            # Sin peticiones de red: solo se anuncian semillas declaradas.
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
        # Todas las semillas se registran primero (origen "semilla") para que los
        # enlaces que coincidan con ellas no las reclasifiquen como enlace.
        semillas_unicas: list[str] = []
        for semilla in semillas:
            if semilla in vistos:
                continue
            vistos.add(semilla)
            semillas_unicas.append(semilla)
            candidatos.append(
                self._candidato(semilla, sitio, origen="semilla", previo=previos.get(semilla))
            )

        # Se conservan los candidatos descubiertos antes: sus enlaces dependen de
        # reprocesar las semillas, que en una segunda pasada se omiten por dedup.
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

            ok, contenido = self._procesar(
                fuente, sitio, semilla, decision, carpeta, indice
            )
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
            # Se puntúa por ruta/consulta, no por el host: así una marca del
            # lexicón (p. ej. "suncar") no coincide con el dominio del sitio.
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
            "origen": origen,
            "relevante": veredicto.relevante,
            "puntuacion": veredicto.puntuacion,
            "terminos": veredicto.terminos,
            "motivos": veredicto.motivos,
            "incluir": incluir,
        }

    # -- fase 2: recolección de aprobados -------------------------------
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

    # -- registro de manifiesto -----------------------------------------
    def _registro(
        self, fuente, url_solicitada, url_final, fecha, estado, content_type,
        ruta_crudo, ruta_texto, hash12, _contenido_hash_extra, advertencias, nivel, url_padre, decision,
        titulo="", descripcion="", registros_estructurados=0, activos: list[str] | None = None,
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

    def _metodo_obtencion(self) -> str:
        return "GET HTTP; robots.txt respetado" if self.fetcher.respetar_robots else "GET HTTP"


def recolectar(config, almacen, fetcher, opciones, fuentes, fase: str, aprobar_relevantes: bool = False) -> Resumen:
    recolector = Recolector(config, almacen, fetcher, opciones)
    if fase == "recolectar":
        return recolector.recolectar(fuentes, aprobar_relevantes)
    return recolector.descubrir(fuentes)
