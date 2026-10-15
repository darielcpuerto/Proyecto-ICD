"""Renderizado de páginas con JavaScript mediante Playwright (opcional).

Este módulo permite obtener el HTML *ya renderizado* de páginas cuyo contenido
se construye en el cliente.

Configuración del navegador
---------------------------
No se usa el navegador que Playwright descarga con ``playwright install``;
se usa el ejecutable de Chromium ya presente en el sistema, indicado por
``executable_path``. La ruta se resuelve en este orden:

1. el argumento ``executable_path`` (opción ``--chromium`` de la línea de
   comandos);
2. la variable de entorno ``CHROMIUM_EXECUTABLE``;
3. el valor por defecto ``/opt/chromium/chrome-linux-arm64/chrome``.

Los argumentos del navegador son ``--no-sandbox`` y ``--disable-dev-shm-usage``
(necesarios en contenedores y en proot). Se pueden añadir más argumentos con la
variable de entorno ``CHROMIUM_ARGS`` (separados por espacios), por ejemplo:

    CHROMIUM_ARGS="--disable-gpu --single-process"

Playwright se importa de forma diferida: si no está instalado, ``disponible()``
devuelve ``False`` y ``RenderizadorJS`` lanza un error claro. Este módulo no
instala nada ni descarga navegadores.

Limitación conocida
-------------------
En este entorno (proot-distro sobre Android) Chromium *arranca* y abre el
puerto de DevTools, pero los procesos hijo (servicio de red / renderer) mueren
con ``SIGTRAP`` al crear la primera página, de modo que ``obtener()`` falla. En
ese caso ``utilizable()`` devuelve ``False`` y el recolector degrada a
obtención estática. Véase ``ENTORNO.md``.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import shlex
from pathlib import Path

from .fetcher import Respuesta

# Chromium emite mucho ruido (dbus/udev/GPU) por stderr en contenedores.
logging.getLogger("playwright").setLevel(logging.CRITICAL)

EJECUTABLE_POR_DEFECTO = "/opt/chromium/chrome-linux-arm64/chrome"

# Argumentos imprescindibles en contenedores/proot sin espacios de nombres.
ARGUMENTOS_BASE = ("--no-sandbox", "--disable-dev-shm-usage")

INSTRUCCIONES = (
    "Playwright no está instalado en el entorno virtual. Para el renderizado "
    "con JavaScript ejecuta, dentro del contenedor Ubuntu:\n"
    "    /root/DataScience/.venv/bin/pip install playwright\n"
    "El navegador se toma del ejecutable del sistema indicado por "
    "--chromium, la variable CHROMIUM_EXECUTABLE o "
    f"{EJECUTABLE_POR_DEFECTO}."
)


def disponible() -> bool:
    """Indica si el paquete `playwright` puede importarse."""
    return importlib.util.find_spec("playwright") is not None


def resolver_ejecutable(explicit: str | None = None) -> str:
    """Devuelve la ruta del ejecutable de Chromium según la prioridad definida."""
    return explicit or os.environ.get("CHROMIUM_EXECUTABLE") or EJECUTABLE_POR_DEFECTO


def argumentos_navegador() -> list[str]:
    """Argumentos de Chromium: los base más los de ``CHROMIUM_ARGS``."""
    extra = os.environ.get("CHROMIUM_ARGS", "")
    return list(ARGUMENTOS_BASE) + shlex.split(extra)


def resumir_error(exc: BaseException) -> str:
    """Resume una excepción de Playwright y descarta el volcado de logs.

    Los errores de Playwright (p. ej. ``TargetClosedError``) adjuntan todo el
    stderr del navegador tras la marca ``Browser logs:``. Ese volcado no aporta
    al registro de la recolección y es muy extenso, así que se elimina.
    """
    texto = str(exc)
    for marca in ("\nBrowser logs:", "Browser logs:"):
        if marca in texto:
            texto = texto.split(marca, 1)[0]
            break
    lineas = [linea.strip() for linea in texto.splitlines() if linea.strip()]
    resumen = lineas[0] if lineas else type(exc).__name__
    if len(resumen) > 300:
        resumen = resumen[:297] + "..."
    return resumen


class ErrorRenderizado(RuntimeError):
    """Error de configuración o uso del renderizador."""


class RenderizadorJS:
    """Obtiene el HTML renderizado de una URL usando un navegador headless."""

    def __init__(
        self,
        user_agent: str,
        timeout: float = 45.0,
        espera_ms: int = 2500,
        executable_path: str | None = None,
    ) -> None:
        if not disponible():
            raise ErrorRenderizado(INSTRUCCIONES)
        from playwright.sync_api import sync_playwright  # import diferido

        self.user_agent = user_agent
        self.timeout = timeout
        self.espera_ms = espera_ms
        self.executable_path = resolver_ejecutable(executable_path)
        if not Path(self.executable_path).is_file():
            raise ErrorRenderizado(
                f"No se encontró el ejecutable de Chromium: {self.executable_path}. "
                "Indícalo con --chromium o la variable CHROMIUM_EXECUTABLE."
            )

        self._inutilizable = False
        self._motivo_fallo: str | None = None
        try:
            self._playwright = sync_playwright().start()
            # --no-sandbox es necesario en entornos proot/Android sin namespaces.
            self._navegador = self._playwright.chromium.launch(
                headless=True,
                executable_path=self.executable_path,
                args=argumentos_navegador(),
            )
            self._contexto = self._navegador.new_context(user_agent=user_agent)
        except Exception as exc:  # noqa: BLE001
            self._cerrar_recursos()
            raise ErrorRenderizado(
                f"No se pudo iniciar Chromium ({self.executable_path}): "
                f"{type(exc).__name__}: {resumir_error(exc)}"
            ) from exc

    # -- estado ---------------------------------------------------------
    def utilizable(self) -> bool:
        """``False`` cuando el navegador se ha caído y no admite más páginas."""
        return not self._inutilizable

    def motivo_fallo(self) -> str | None:
        """Descripción del fallo que dejó inutilizable el renderizador."""
        return self._motivo_fallo

    # -- uso ------------------------------------------------------------
    def obtener(self, url: str) -> Respuesta:
        """Navega a `url` y devuelve el HTML renderizado."""
        if self._inutilizable:
            return self._respuesta_error(url, self._motivo_fallo or "renderizador no disponible")

        try:
            pagina = self._contexto.new_page()
        except Exception as exc:  # noqa: BLE001
            return self._respuesta_error(url, self._anotar_fallo(exc))

        try:
            respuesta = pagina.goto(url, timeout=self.timeout * 1000, wait_until="networkidle")
            try:
                pagina.wait_for_timeout(self.espera_ms)
            except Exception:  # noqa: BLE001
                pass
            html = pagina.content()
            return Respuesta(
                url_solicitada=url,
                url_final=pagina.url,
                estado_http=respuesta.status if respuesta else 0,
                content_type="text/html",
                contenido=html.encode("utf-8"),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            return self._respuesta_error(url, self._anotar_fallo(exc))
        finally:
            try:
                pagina.close()
            except Exception:  # noqa: BLE001
                pass

    # -- internos -------------------------------------------------------
    def _anotar_fallo(self, exc: Exception) -> str:
        detalle = f"{type(exc).__name__}: {resumir_error(exc)}".strip()
        # Si el navegador ya no está conectado, no tiene sentido seguir
        # intentando: se marca como inutilizable para que el recolector
        # degrade a la obtención estática.
        if isinstance(exc, _TargetClosedError) or not self._navegador.is_connected():
            self._inutilizable = True
            self._motivo_fallo = (
                "el navegador Chromium cerró sus procesos (posible SIGTRAP del "
                "servicio de red/renderer bajo proot); se continúa con la "
                f"obtención estática [{detalle}]"
            )
            return self._motivo_fallo
        return f"renderizado: {detalle}"

    @staticmethod
    def _respuesta_error(url: str, error: str) -> Respuesta:
        if not error.startswith(("renderizado", "el navegador")):
            error = f"renderizado: {error}"
        return Respuesta(
            url_solicitada=url, url_final=url, estado_http=0,
            content_type="", contenido=b"", encoding="utf-8",
            error=error,
        )

    def cerrar(self) -> None:
        self._cerrar_recursos()

    def _cerrar_recursos(self) -> None:
        for recurso in (getattr(self, "_contexto", None), getattr(self, "_navegador", None)):
            try:
                recurso.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            self._playwright.stop()
        except Exception:  # noqa: BLE001
            pass


# Import perezoso de la excepción de Playwright para no obligar a tenerlo instalado.
try:  # pragma: no cover - depende del entorno
    from playwright._impl._errors import TargetClosedError as _TargetClosedError
except Exception:  # noqa: BLE001
    class _TargetClosedError(Exception):  # type: ignore[no-redef]
        """Sustituto cuando Playwright no está instalado."""
