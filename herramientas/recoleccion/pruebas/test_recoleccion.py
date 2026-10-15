"""Pruebas de la extracción estructurada y de la política de sitios.

Se ejecutan sin red: usan fixtures locales y casos construidos a mano.
"""

import unittest
from pathlib import Path

from herramientas.recoleccion import extraccion, politica
from herramientas.recoleccion.config import Fuente

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FECHA = "2026-10-15T00:00:00+00:00"


def fuente_prueba() -> Fuente:
    return Fuente(
        id="T-001",
        nombre="Tienda de prueba",
        url="https://ejemplo.test",
        categoria="prueba",
        tipo="test",
        estado="verified",
        prioridad="alta",
        datos_esperados=(
            "product_name", "brand", "model", "power_w", "price", "currency",
        ),
    )


def leer(nombre: str) -> tuple[str, str]:
    html = (FIXTURES / nombre).read_text(encoding="utf-8")
    return html, html


class TestJSONLD(unittest.TestCase):
    def test_extrae_producto_de_schema_org(self):
        html, texto = leer("tienda_jsonld.html")
        regs = extraccion.extraer_json_ld(html, "https://ejemplo.test/panel", FECHA, fuente_prueba())
        self.assertEqual(len(regs), 1)
        r = regs[0]
        self.assertEqual(r["metodo_extraccion"], "json_ld")
        self.assertEqual(r["campos"]["product_name"], "Panel Solar 600W")
        self.assertEqual(r["campos"]["brand"], "SUNCAR")
        self.assertEqual(r["campos"]["model"], "ZY600M10NHB")
        self.assertEqual(r["campos"]["price"], "150.00")
        self.assertEqual(r["campos"]["currency"], "CUP")
        self.assertEqual(r["tipo_precio"], "anunciado")
        self.assertEqual(r["moneda"], "CUP")
        # Trazabilidad
        self.assertEqual(r["url_origen"], "https://ejemplo.test/panel")
        self.assertEqual(r["fecha_consulta"], FECHA)
        self.assertTrue(r["evidencia_cruda"])
        self.assertIn("ld+json", r["ubicacion_evidencia"])

    def test_no_inventa_campos_ausentes(self):
        html, _ = leer("tienda_jsonld.html")
        r = extraccion.extraer_json_ld(html, "https://ejemplo.test/panel", FECHA, fuente_prueba())[0]
        self.assertIn("power_w", r["campos_ausentes"])
        self.assertNotIn("power_w", r["campos"])


class TestIncrustados(unittest.TestCase):
    def test_extrae_ofertas_del_payload_rsc(self):
        html, _ = leer("tienda_incrustada.html")
        regs = extraccion.extraer_incrustados(html, "https://ejemplo.test/ofertas", FECHA, fuente_prueba())
        self.assertEqual(len(regs), 2)
        self.assertEqual(regs[0]["metodo_extraccion"], "datos_incrustados")
        self.assertEqual(regs[0]["campos"]["product_name"], "Kit 3kW Inversor + Bateria")
        self.assertEqual(regs[0]["campos"]["price"], 3140)
        self.assertEqual(regs[0]["campos"]["currency"], "USD")
        self.assertEqual(regs[0]["campos"]["power_w"], "3KW")
        self.assertIn("initialOfertas", regs[0]["ubicacion_evidencia"])
        # Los campos no objetivo se separan y no se pierden.
        self.assertIn("is_active", regs[0]["campos_adicionales"])
        self.assertIn("id", regs[0]["campos_adicionales"])
        self.assertNotIn("is_active", regs[0]["campos"])

    def test_extrae_de_flight_stream_no_json(self):
        # El payload de Next.js App Router no es JSON completo; debe localizarse
        # el literal JSON embebido dentro del flight stream.
        html, _ = leer("tienda_flight.html")
        regs = extraccion.extraer_incrustados(html, "https://ejemplo.test/ofertas", FECHA, fuente_prueba())
        self.assertEqual(len(regs), 2)
        self.assertEqual(regs[0]["campos"]["product_name"], "Kit 8kW Felicity")
        self.assertEqual(regs[0]["campos"]["price"], 6460)

    def test_conserva_moneda_sin_convertir(self):
        html, _ = leer("tienda_incrustada.html")
        regs = extraccion.extraer_incrustados(html, "https://ejemplo.test/ofertas", FECHA, fuente_prueba())
        for r in regs:
            self.assertEqual(r["campos"]["currency"], "USD")
            self.assertEqual(r["campos"]["price"], int(r["campos"]["price"]))


class TestPreciosTexto(unittest.TestCase):
    def test_detecta_precio_con_moneda(self):
        html, texto = leer("tienda_texto.html")
        regs = extraccion.extraer_precios_texto(texto, "https://ejemplo.test/ofertas", FECHA, fuente_prueba())
        precios = {(r["campos"].get("price"), r["campos"].get("currency")) for r in regs}
        self.assertIn(("6.460", "USD"), precios)
        self.assertIn(("5.960", "USD"), precios)
        self.assertTrue(all(r["metodo_extraccion"] == "heuristica_texto" for r in regs))
        self.assertTrue(any("verificar" in " ".join(r["advertencias"]) for r in regs))


class TestAdaptadores(unittest.TestCase):
    def test_adaptador_revolico_apollo_y_feed(self):
        from herramientas.recoleccion import extractores
        html, texto = leer("revolico_next_data.html")
        regs = extractores.extraer("revolico", html, texto, "https://ejemplo.test/search?q=panel", FECHA, fuente_prueba())
        titulos = sorted(r["campos"]["product_name"] for r in regs)
        # AdType:1 y el nodo de feed con el mismo título se deduplican.
        self.assertEqual(titulos, ["Bateria LiFePO4 5kWh", "Inversor 3kW", "Panel solar 500W"])
        self.assertTrue(all(r["metodo_extraccion"] == "adaptador_revolico" for r in regs))
        self.assertTrue(any("apollo:" in r["ubicacion_evidencia"] for r in regs))
        self.assertTrue(any("feed:" in r["ubicacion_evidencia"] for r in regs))

    def test_adaptador_bembete(self):
        from herramientas.recoleccion import extractores
        html, texto = leer("tienda_flight.html")
        regs = extractores.extraer("bembete", html, texto, "https://ejemplo.test/b/", FECHA, fuente_prueba())
        self.assertEqual(len(regs), 2)
        self.assertTrue(all(r["metodo_extraccion"] == "adaptador_bembete" for r in regs))

    def test_extraer_desconocido_devuelve_vacio(self):
        from herramientas.recoleccion import extractores
        self.assertEqual(extractores.extraer("desconocido", "<html></html>", "", "u", FECHA, fuente_prueba()), [])


class TestRenderizado(unittest.TestCase):
    def test_disponible_devuelve_bool(self):
        from herramientas.recoleccion import render
        self.assertIsInstance(render.disponible(), bool)

    def test_resolver_ejecutable_prioridad(self):
        import os
        from unittest import mock
        from herramientas.recoleccion import render
        self.assertEqual(render.resolver_ejecutable("/ruta/chrome"), "/ruta/chrome")
        with mock.patch.dict(os.environ, {"CHROMIUM_EXECUTABLE": "/otra/chrome"}):
            self.assertEqual(render.resolver_ejecutable(), "/otra/chrome")
            self.assertEqual(render.resolver_ejecutable("/explicita/chrome"), "/explicita/chrome")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(render.resolver_ejecutable(), render.EJECUTABLE_POR_DEFECTO)

    def test_argumentos_navegador(self):
        import os
        from unittest import mock
        from herramientas.recoleccion import render
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(render.argumentos_navegador(), list(render.ARGUMENTOS_BASE))
        with mock.patch.dict(os.environ, {"CHROMIUM_ARGS": "--disable-gpu --single-process"}):
            argumentos = render.argumentos_navegador()
            self.assertIn("--no-sandbox", argumentos)
            self.assertIn("--disable-gpu", argumentos)
            self.assertIn("--single-process", argumentos)

    def test_resumir_error_descarta_logs(self):
        from herramientas.recoleccion import render
        exc = RuntimeError(
            "BrowserContext.new_page: Target page, context or browser has been closed\n"
            "Browser logs:\n\n<launching> /opt/chromium/chrome --no-sandbox\n"
            "[pid=1][err] ERROR:dbus/bus.cc:405 Failed to connect to the bus"
        )
        resumen = render.resumir_error(exc)
        self.assertIn("Target page, context or browser has been closed", resumen)
        self.assertNotIn("Browser logs", resumen)
        self.assertNotIn("dbus", resumen)
        self.assertLess(len(resumen), 320)

    def test_error_si_no_instalado(self):
        from herramientas.recoleccion import render
        if render.disponible():
            self.skipTest("Playwright está instalado")
        with self.assertRaises(render.ErrorRenderizado):
            render.RenderizadorJS(user_agent="prueba")


class TestPolitica(unittest.TestCase):
    def test_detecta_aviso_legal(self):
        texto = "# NOTICE: collection through automated means is prohibited except with written permission\nUser-agent: *\nAllow: /"
        aviso = politica.detectar_aviso(texto)
        self.assertIsNotNone(aviso)
        self.assertIn("prohibited", aviso.lower())

    def test_sin_aviso(self):
        self.assertIsNone(politica.detectar_aviso("User-agent: *\nAllow: /"))

    def test_bloquea_si_robots_no_permite(self):
        d = politica.evaluar(fuente_prueba(), robots_permite=False, texto_robots="User-agent: *\nDisallow: /")
        self.assertFalse(d.puede_recolectar)

    def test_bloquea_si_hay_aviso_sin_override(self):
        texto = "# scraping is prohibited\nUser-agent: *\nAllow: /"
        d = politica.evaluar(fuente_prueba(), robots_permite=True, texto_robots=texto)
        self.assertFalse(d.puede_recolectar)
        self.assertIsNotNone(d.aviso_legal)

    def test_permite_con_override_registrado(self):
        texto = "# scraping is prohibited\nUser-agent: *\nAllow: /"
        override = {"recolectar": True, "motivo": "autorizado por el usuario", "autorizado_por": "usuario"}
        d = politica.evaluar(fuente_prueba(), robots_permite=True, texto_robots=texto, override=override)
        self.assertTrue(d.puede_recolectar)
        self.assertEqual(d.autorizado_por, "usuario")
        self.assertTrue(d.advertencias)


if __name__ == "__main__":
    unittest.main()
