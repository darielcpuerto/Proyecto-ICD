"""Pruebas del núcleo: extracción, política, contenido, relevancia y dedup.

Se ejecutan sin red: usan HTML construido a mano y directorios temporales.
"""

import json
import tempfile
import unittest
from pathlib import Path

from herramientas.recoleccion.nucleo import almacen, contenido, extraccion, politica
from herramientas.recoleccion.nucleo.config import Fuente
from herramientas.recoleccion.nucleo.relevancia import Lexico

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


def html_con_jsonld(datos: dict) -> str:
    return (
        "<html><head>"
        f'<script type="application/ld+json">{json.dumps(datos)}</script>'
        "</head><body></body></html>"
    )


class TestJSONLD(unittest.TestCase):
    def test_extrae_producto_de_schema_org(self):
        html = html_con_jsonld({
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Panel Solar 600W",
            "brand": {"@type": "Brand", "name": "SUNCAR"},
            "sku": "ZY600M10NHB",
            "offers": {"@type": "Offer", "price": "150.00", "priceCurrency": "CUP"},
        })
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
        self.assertEqual(r["url_origen"], "https://ejemplo.test/panel")
        self.assertEqual(r["fecha_consulta"], FECHA)
        self.assertIn("ld+json", r["ubicacion_evidencia"])

    def test_no_inventa_campos_ausentes(self):
        html = html_con_jsonld({"@type": "Product", "name": "Panel Solar 600W", "offers": {"price": "1"}})
        r = extraccion.extraer_json_ld(html, "u", FECHA, fuente_prueba())[0]
        self.assertIn("power_w", r["campos_ausentes"])
        self.assertNotIn("power_w", r["campos"])


class TestIncrustados(unittest.TestCase):
    def test_extrae_ofertas_de_next_data(self):
        payload = {"props": {"pageProps": {"initialOfertas": [
            {"id": 1, "nombre": "Kit 3kW Inversor + Bateria", "precio": 3140,
             "moneda": "USD", "potencia": "3KW", "is_active": True},
        ]}}}
        html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
        regs = extraccion.extraer_incrustados(html, "https://ejemplo.test/ofertas", FECHA, fuente_prueba())
        self.assertEqual(len(regs), 1)
        r = regs[0]
        self.assertEqual(r["campos"]["product_name"], "Kit 3kW Inversor + Bateria")
        self.assertEqual(r["campos"]["price"], 3140)
        self.assertEqual(r["campos"]["currency"], "USD")
        self.assertEqual(r["campos"]["power_w"], "3KW")
        self.assertIn("initialOfertas", r["ubicacion_evidencia"])
        self.assertIn("is_active", r["campos_adicionales"])

    def test_extrae_de_flight_stream_no_json(self):
        literal = ('prefijo '
                   '[{"nombre":"Kit 8kW Felicity","precio":6460,"moneda":"USD"},'
                   '{"nombre":"Bateria 5kWh","precio":500,"moneda":"USD"}] fin')
        js = json.dumps(literal)  # cadena JS válida para el regex
        html = f"<script>self.__next_f.push([1,{js}])</script>"
        regs = extraccion.extraer_incrustados(html, "https://ejemplo.test/ofertas", FECHA, fuente_prueba())
        titulos = sorted(r["campos"]["product_name"] for r in regs)
        self.assertEqual(titulos, ["Bateria 5kWh", "Kit 8kW Felicity"])

    def test_conserva_moneda_sin_convertir(self):
        payload = {"pageProps": {"ofertas": [
            {"nombre": "A", "precio": 10, "moneda": "USD"},
            {"nombre": "B", "precio": 20, "moneda": "USD"},
        ]}}
        html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
        regs = extraccion.extraer_incrustados(html, "u", FECHA, fuente_prueba())
        for r in regs:
            self.assertEqual(r["campos"]["currency"], "USD")


class TestPreciosTexto(unittest.TestCase):
    def test_detecta_precio_con_moneda(self):
        texto = "Oferta por 6.460 USD y otra por 5.960 USD."
        regs = extraccion.extraer_precios_texto(texto, "https://ejemplo.test/ofertas", FECHA, fuente_prueba())
        precios = {(r["campos"].get("price"), r["campos"].get("currency")) for r in regs}
        self.assertIn(("6.460", "USD"), precios)
        self.assertIn(("5.960", "USD"), precios)
        self.assertTrue(all(r["metodo_extraccion"] == "heuristica_texto" for r in regs))


class TestContenido(unittest.TestCase):
    def test_extrae_titulo_texto_y_enlaces(self):
        html = (
            "<html><head><title>Ofertas</title>"
            '<meta name="description" content="Panel solar"></head>'
            '<body><a href="/a">A</a><a href="https://otro.test/x">B</a>'
            '<img src="/i.png"><p>Texto visible</p></body></html>'
        )
        c = contenido.extraer(html, "https://ejemplo.test/")
        self.assertEqual(c.titulo, "Ofertas")
        self.assertEqual(c.descripcion, "Panel solar")
        self.assertIn("https://ejemplo.test/a", c.enlaces)
        self.assertIn("https://otro.test/x", c.enlaces)
        self.assertIn("Texto visible", c.texto)

    def test_es_imagen(self):
        self.assertTrue(contenido.es_imagen("https://x/a.jpg"))
        self.assertFalse(contenido.es_imagen("https://x/a.html"))


class TestRelevancia(unittest.TestCase):
    def _lexico(self, exigir_fuerte=True):
        fuertes = [
            {"termino": "panel solar", "peso": 3, "campo": "product_name"},
            {"termino": "inversor", "peso": 3, "campo": "product_name"},
        ]
        campos = [{"termino": "precio", "peso": 1, "campo": "price"}]
        return Lexico(umbral=3, fuertes=fuertes, campos=campos,
                      exclusiones=["alquiler"], exigir_fuerte=exigir_fuerte)

    def test_normaliza_guiones(self):
        v = self._lexico().evaluar(url="https://x/panel-solar-3kw")
        self.assertTrue(v.relevante)
        self.assertIn("panel solar", v.terminos)

    def test_exige_termino_fuerte(self):
        v = self._lexico().evaluar(texto="precio 5000 usd disponible")
        self.assertFalse(v.relevante)

    def test_exclusion(self):
        v = self._lexico().evaluar(texto="alquiler de panel solar")
        self.assertFalse(v.relevante)
        self.assertEqual(v.puntuacion, 0)


class TestPolitica(unittest.TestCase):
    def test_detecta_aviso_legal(self):
        texto = "# NOTICE: collection through automated means is prohibited except with written permission\nUser-agent: *\nAllow: /"
        aviso = politica.detectar_aviso(texto)
        self.assertIsNotNone(aviso)
        self.assertIn("prohibited", aviso.lower())

    def test_bloquea_si_robots_no_permite(self):
        d = politica.evaluar(fuente_prueba(), robots_permite=False, texto_robots="Disallow: /")
        self.assertFalse(d.puede_recolectar)

    def test_permite_con_override(self):
        texto = "# scraping is prohibited\nUser-agent: *\nAllow: /"
        override = {"recolectar": True, "motivo": "autorizado", "autorizado_por": "usuario"}
        d = politica.evaluar(fuente_prueba(), robots_permite=True, texto_robots=texto, override=override)
        self.assertTrue(d.puede_recolectar)
        self.assertEqual(d.autorizado_por, "usuario")

    def test_excluir_tiene_prioridad(self):
        override = {
            "excluir": True,
            "motivo": "protegido por un challenge de Cloudflare",
            "autorizado_por": "usuario",
        }
        d = politica.evaluar(fuente_prueba(), robots_permite=True,
                             texto_robots="User-agent: *\nAllow: /", override=override)
        self.assertFalse(d.puede_recolectar)
        self.assertEqual(d.motivo, "protegido por un challenge de Cloudflare")
        self.assertEqual(d.autorizado_por, "usuario")


class TestAlmacenDedup(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.almacen = almacen.Almacen(Path(self._tmp.name))
        self.carpeta = self.almacen.carpeta_fuente("T-001", "Tienda de prueba")

    def tearDown(self):
        self._tmp.cleanup()

    def test_crudo_estable_por_contenido(self):
        url = "https://ejemplo.test/oferta"
        contenido_bytes = b"<html>igual</html>"
        ruta1, h1, nuevo1 = self.almacen.guardar_crudo(self.carpeta, url, contenido_bytes)
        ruta2, h2, nuevo2 = self.almacen.guardar_crudo(self.carpeta, url, contenido_bytes)
        self.assertEqual(ruta1, ruta2)
        self.assertEqual(h1, h2)
        self.assertFalse(nuevo1)
        self.assertTrue(nuevo2)  # la segunda vez ya existía
        self.assertEqual(len(list((self.carpeta / "crudo").iterdir())), 1)

    def test_contenido_distinto_crea_archivo_distinto(self):
        ruta1, _, _ = self.almacen.guardar_crudo(self.carpeta, "https://x/a", b"<html>1</html>")
        ruta2, _, _ = self.almacen.guardar_crudo(self.carpeta, "https://x/a", b"<html>2</html>")
        self.assertNotEqual(ruta1, ruta2)

    def test_activo_estable_por_contenido(self):
        url = "https://ejemplo.test/assets/index-abc123.js"
        ruta1, h1, nuevo1 = self.almacen.guardar_activo(self.carpeta, url, b"var x=1;")
        ruta2, h2, nuevo2 = self.almacen.guardar_activo(self.carpeta, url, b"var x=1;")
        self.assertEqual(ruta1, ruta2)
        self.assertEqual(h1, h2)
        self.assertFalse(nuevo1)
        self.assertTrue(nuevo2)
        self.assertEqual(ruta1.suffix, ".js")
        self.assertEqual(ruta1.parent.name, "activos")

    def test_indice_reconstruye_desde_manifiesto(self):
        _, h, _ = self.almacen.guardar_crudo(self.carpeta, "https://x/a", b"<html>ok</html>")
        self.almacen.registrar(self.carpeta, {
            "url_solicitada": "https://x/a", "estado_http": 200,
            "error": None, "hash_contenido": h,
        })
        self.almacen.registrar(self.carpeta, {
            "url_solicitada": "https://x/error", "estado_http": 403,
            "error": None, "hash_contenido": None,
        })
        indice = self.almacen.cargar_indice(self.carpeta)
        self.assertTrue(indice.url_vista("https://x/a"))
        self.assertTrue(indice.hash_visto(h))
        # Una URL con error no se considera capturada, pero sí intentada.
        self.assertFalse(indice.url_vista("https://x/error"))
        self.assertTrue(indice.url_intentada("https://x/error"))

    def test_candidatos_ida_y_vuelta(self):
        candidatos = [{"url": "https://x/a", "relevante": True, "incluir": None}]
        self.almacen.escribir_candidatos(self.carpeta, candidatos)
        self.assertEqual(self.almacen.leer_candidatos(self.carpeta), candidatos)


if __name__ == "__main__":
    unittest.main()
