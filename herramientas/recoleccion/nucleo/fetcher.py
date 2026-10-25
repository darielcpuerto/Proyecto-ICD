"""Obtención de recursos web respetando las restricciones del sitio.

El cliente HTTP aplica un retardo entre peticiones al mismo host, reintentos
limitados y, cuando se solicita, comprobación de `robots.txt`. No interpreta
los datos: entrega la respuesta cruda tal como la devuelve el servidor.
"""

from __future__ import annotations

import re
import time
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

USER_AGENT_POR_DEFECTO = (
    "Proyecto-ICD-UH/0.1 (recoleccion academica de oferta observada; "
    "contacto: estudiante)"
)


@dataclass
class Respuesta:
    """Respuesta cruda de una petición HTTP."""

    url_solicitada: str
    url_final: str
    estado_http: int
    content_type: str
    contenido: bytes
    encoding: str
    error: str | None = None
    advertencias: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.estado_http < 300

    def texto(self) -> str:
        """Decodifica el cuerpo con la codificación determinada al obtenerlo."""
        return self.contenido.decode(self.encoding or "utf-8", errors="replace")


def _codificacion_de_respuesta(resp) -> str:
    """Determina la codificación del cuerpo de una respuesta HTTP.

    Se respeta el ``charset`` declarado en ``Content-Type``. Si no lo hay, se
    prefiere UTF-8 (comprobándolo) en lugar del ISO-8859-1 que la biblioteca
    asigna por defecto a los tipos ``text/*``: esa suposición corrompe los
    acentos de recursos casi ASCII como un bundle JavaScript.
    """
    coincidencia = re.search(r"charset=([\w\-]+)", resp.headers.get("Content-Type", ""), re.I)
    if coincidencia:
        return coincidencia.group(1)
    try:
        resp.content.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return resp.apparent_encoding or "utf-8"


class Fetcher:
    """Cliente HTTP con cortesía hacia el servidor y soporte de robots.txt."""

    def __init__(
        self,
        user_agent: str = USER_AGENT_POR_DEFECTO,
        timeout: float = 30.0,
        delay: float = 2.0,
        reintentos: int = 2,
        respetar_robots: bool = True,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.delay = delay
        self.reintentos = reintentos
        self.respetar_robots = respetar_robots
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self._ultimo_acceso: dict[str, float] = {}
        self._robots: dict[str, tuple[urllib.robotparser.RobotFileParser | None, str | None]] = {}

    # -- robots.txt -----------------------------------------------------
    def _cargar_robots(self, url: str) -> tuple[urllib.robotparser.RobotFileParser | None, str | None]:
        partes = urlparse(url)
        base = f"{partes.scheme}://{partes.netloc}"
        if base in self._robots:
            return self._robots[base]

        parser: urllib.robotparser.RobotFileParser | None
        texto: str | None
        try:
            respuesta = self.session.get(base + "/robots.txt", timeout=self.timeout)
            if respuesta.status_code == 200:
                texto = respuesta.text
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(texto.splitlines())
            else:
                # Sin robots.txt (p. ej. 404) no hay reglas declaradas.
                parser, texto = None, None
        except requests.RequestException:
            # Si no se puede leer robots.txt se registra y se continúa.
            parser, texto = None, None

        self._robots[base] = (parser, texto)
        return parser, texto

    def _crawl_delay(self, url: str) -> float:
        """Retardo declarado en ``robots.txt`` para nuestro User-Agent.

        Se aplican los grupos ``Crawl-delay`` que coinciden con el agente del
        proyecto o con ``*``. Si hay varios, se toma el mayor; un grupo
        específico tiene prioridad sobre el genérico.
        """
        _, texto = self._cargar_robots(url)
        if not texto:
            return 0.0

        grupos: list[tuple[list[str], float | None]] = []
        agentes: list[str] = []
        retardo: float | None = None
        for linea in texto.splitlines():
            linea = linea.split("#", 1)[0].strip()
            if not linea or ":" not in linea:
                continue
            clave, _, valor = linea.partition(":")
            clave = clave.strip().lower()
            valor = valor.strip()
            if clave == "user-agent":
                if agentes:
                    grupos.append((agentes, retardo))
                agentes = [valor.lower()] if valor else []
                retardo = None
            elif clave == "crawl-delay" and agentes:
                try:
                    retardo = float(valor.replace(",", "."))
                except ValueError:
                    continue
        if agentes:
            grupos.append((agentes, retardo))

        agente = self.user_agent.lower()
        especificos: list[float] = []
        genericos: list[float] = []
        for nombres, valor in grupos:
            if valor is None:
                continue
            for nombre in nombres:
                if nombre == "*":
                    genericos.append(valor)
                elif nombre and (agente.startswith(nombre) or nombre in agente):
                    especificos.append(valor)
        return max(especificos or genericos or [0.0])

    def retardo_efectivo(self, url: str) -> float:
        """Retardo aplicado entre peticiones al host de ``url``."""
        return max(float(self.delay or 0.0), self._crawl_delay(url))

    def _robots_de(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        return self._cargar_robots(url)[0]

    def texto_robots(self, url: str) -> str | None:
        """Devuelve el contenido crudo de robots.txt (o None si no hay)."""
        return self._cargar_robots(url)[1]

    def permitido_por_robots(self, url: str) -> bool:
        if not self.respetar_robots:
            return True
        parser = self._robots_de(url)
        if parser is None:
            return True
        return parser.can_fetch(self.user_agent, url)

    # -- peticiones -----------------------------------------------------
    def _esperar_turno(self, url: str) -> None:
        host = urlparse(url).netloc
        ultimo = self._ultimo_acceso.get(host)
        if ultimo is not None:
            retardo = self.retardo_efectivo(url)
            transcurrido = time.monotonic() - ultimo
            if transcurrido < retardo:
                time.sleep(retardo - transcurrido)

    def obtener(self, url: str) -> Respuesta:
        """Descarga `url` y devuelve la respuesta cruda, sin transformarla."""
        if not self.permitido_por_robots(url):
            return Respuesta(
                url_solicitada=url,
                url_final=url,
                estado_http=0,
                content_type="",
                contenido=b"",
                encoding="utf-8",
                error="bloqueado_por_robots.txt",
            )

        self._esperar_turno(url)
        ultimo_error = "sin intentos"
        for intento in range(self.reintentos + 1):
            try:
                resp = self.session.get(
                    url,
                    timeout=self.timeout,
                    allow_redirects=True,
                )
                self._ultimo_acceso[urlparse(url).netloc] = time.monotonic()
                encoding = _codificacion_de_respuesta(resp)
                return Respuesta(
                    url_solicitada=url,
                    url_final=str(resp.url),
                    estado_http=resp.status_code,
                    content_type=resp.headers.get("Content-Type", ""),
                    contenido=resp.content,
                    encoding=encoding or "utf-8",
                )
            except requests.RequestException as exc:
                ultimo_error = f"{type(exc).__name__}: {exc}"
                if intento < self.reintentos:
                    time.sleep(self.delay * (intento + 1))

        return Respuesta(
            url_solicitada=url,
            url_final=url,
            estado_http=0,
            content_type="",
            contenido=b"",
            encoding="utf-8",
            error=ultimo_error,
        )
