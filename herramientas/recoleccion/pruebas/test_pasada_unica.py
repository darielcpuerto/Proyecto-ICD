"""Pruebas de la pasada única: relevancia por campos, tipos de página,
objetivo, deduplicación, idempotencia y secuencialidad.

Se ejecutan sin red: usan HTML y respuestas construidas a mano.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from herramientas.recoleccion import sitios
from herramientas.recoleccion.nucleo import relevancia, sitemap
from herramientas.recoleccion.nucleo.almacen import Almacen
from herramientas.recoleccion.nucleo.config import cargar_configuracion
from herramientas.recoleccion.nucleo.fetcher import Respuesta
from herramientas.recoleccion.nucleo.recolector import Opciones, Recolector, recolectar
from herramientas.recoleccion.nucleo.urls import canonicalizar
from herramientas.recoleccion.sitios.base import (
    Candidato,
    EvidenciaPagina,
    Sitio,
    TipoPagina,
)

RAIZ = Path(__file__).resolve().parents[3]
FECHA = "2026-10-25T00:00:00+00:00"


def lexico() -> relevancia.Lexico:
    return relevancia.cargar_lexico()


class FakeFetcher:
    """Fetcher en memoria; registra el orden y detecta solapamiento."""

    def __init__(self, paginas=None, robots="User-agent: *\nAllow: /", delay=0.0) -> None:
        self.paginas = paginas or {}
        self.robots = robots
        self.delay = delay
        self.timeout = 1.0
        self.reintentos = 0
        self.respetar_robots = True
        self.peticiones: list[str] = []
        self._en_curso = 0
        self.max_en_curso = 0

    def permitido_por_robots(self, url: str) -> bool:
        return True

    def texto_robots(self, url: str) -> str:
        return self.robots

    def retardo_efectivo(self, url: str) -> float:
        return self.delay

    def obtener(self, url: str) -> Respuesta:
        self.peticiones.append(url)
        self._en_curso += 1
        self.max_en_curso = max(self.max_en_curso, self._en_curso)
        self._en_curso -= 1
        cuerpo = self.paginas.get(url)
        if cuerpo is None:
            return Respuesta(url, url, 404, "text/html", b"", "utf-8")
        return Respuesta(
            url, url, 200, "text/html; charset=utf-8",
            cuerpo.encode("utf-8"), "utf-8",
        )


class SitioFalso(Sitio):
    id = "T-900"
    nombre = "Sitio falso"
    dominio = "falso.test"
    automatico = True
    objetivo_paginas = None

    def __init__(self, total: int, prefiltro_negativo: bool = False) -> None:
        self.total = total
        self.prefiltro_negativo = prefiltro_negativo

    def lotes_candidatos(self, fetcher, texto_robots, opciones):
        return [[
            Candidato(
                url=f"https://falso.test/detalle/{i}",
                tipo_esperado=TipoPagina.DETALLE,
                origen="prueba",
            )
            for i in range(self.total)
        ]]

    def tipo_por_url(self, url):
        return TipoPagina.DETALLE

    def prefiltro(self, url):
        if self.prefiltro_negativo and int(url.rsplit("/", 1)[-1]) % 5 == 0:
            return False, "descartado por prefiltro de prueba"
        return True, ""

    def clasificar_pagina(self, url, tipo_esperado, evidencia, lexico):
        return super().clasificar_pagina(url, tipo_esperado, evidencia, lexico)

    def extraer(self, html, texto, url, fecha, fuente, activos=None):
        indice = url.rsplit("/", 1)[-1]
        return [{
            "fuente_id": fuente.id,
            "fuente_nombre": fuente.nombre,
            "url_origen": url,
            "fecha_consulta": fecha,
            "metodo_extraccion": "prueba",
            "ubicacion_evidencia": "fixture",
            "campos": {
                "product_name": f"Panel Solar {indice}",
                "price": int(indice),
                "currency": "USD",
            },
            "campos_adicionales": {"id_oferta": f"ID-{indice}"},
            "claves_origen": {},
            "campos_presentes": ["product_name", "price", "currency"],
            "campos_ausentes": [],
            "moneda": "USD",
            "tipo_precio": "anunciado",
            "evidencia_cruda": "",
            "advertencias": [],
        }]


def pagina(indice: int) -> str:
    return (
        f"<html><head><title>Panel Solar {indice}</title></head>"
        f"<body><h1>Panel Solar {indice}</h1></body></html>"
    )


class TestCanonicalizacion(unittest.TestCase):
    def test_normaliza_host_porcentajes_y_barra(self):
        a = "https://WWW.Ejemplo.test/b/c-Electrodom%C3%A9sticos/"
        b = "https://ejemplo.test/b/c-Electrodomésticos"
        self.assertEqual(canonicalizar(a), canonicalizar(b))

    def test_quita_fragmento_y_ordena_consulta(self):
        a = "https://x.test/o?b=2&a=1#frag"
        b = "https://x.test/o?a=1&b=2"
        self.assertEqual(canonicalizar(a), canonicalizar(b))


class TestCrawlDelay(unittest.TestCase):
    def test_usa_el_mayor_entre_delay_y_robots(self):
        from herramientas.recoleccion.nucleo.fetcher import Fetcher

        fetcher = Fetcher(delay=1.0)
        fetcher._robots["https://sitio.test"] = (
            None,
            "User-agent: *\nCrawl-delay: 2\n\n"
            "User-agent: Proyecto-ICD-UH\nCrawl-delay: 5\n",
        )
        self.assertEqual(fetcher.retardo_efectivo("https://sitio.test/a"), 5.0)

    def test_sin_crawl_delay_conserva_el_delay_configurado(self):
        from herramientas.recoleccion.nucleo.fetcher import Fetcher

        fetcher = Fetcher(delay=2.0)
        fetcher._robots["https://sitio.test"] = (None, "User-agent: *\nAllow: /")
        self.assertEqual(fetcher.retardo_efectivo("https://sitio.test/a"), 2.0)


class TestRelevanciaPorCampos(unittest.TestCase):
    def setUp(self):
        self.lex = lexico()

    def test_termino_fuerte_en_nombre(self):
        for nombre in ("Panel Solar 600W", "Inversor Growatt 5kW", "Batería de Litio 48V"):
            with self.subTest(nombre=nombre):
                self.assertTrue(
                    self.lex.evaluar_registro({"product_name": nombre}).relevante
                )

    def test_negativos_reales(self):
        falsos = (
            "Casa con paneles solares",
            "Apartamento con energía solar",
            "Batería para celular",
            "Batería de golf 12V",
            "Placa de cocina eléctrica",
            "Power Bank Batería Portátil",
            "Triciclo con baterías de gel",
            "Patineta MAF con batería de litio",
            "Scooter eléctrico con batería extraíble",
            "Batería de carro 12V 60Ah",
            "Batería para automóvil sellada",
            "Bicicleta eléctrica nueva de litio",
            "Moto eléctrica de litio 3000W",
        )
        for nombre in falsos:
            with self.subTest(nombre=nombre):
                self.assertFalse(
                    self.lex.evaluar_registro({"product_name": nombre}).relevante
                )

    def test_bateria_solar_sigue_siendo_relevante(self):
        for nombre in (
            "Batería LiFePO4 12V 100Ah para panel solar",
            "Batería de litio 48V 100Ah",
            "Inversor híbrido con batería de litio",
        ):
            with self.subTest(nombre=nombre):
                self.assertTrue(
                    self.lex.evaluar_registro({"product_name": nombre}).relevante
                )

    def test_descripcion_con_otro_producto_no_excluye(self):
        v = self.lex.evaluar_registro({
            "product_name": "Kit de paneles solares y baterías",
            "description": "También tenemos bicicleta eléctrica y baterías",
            "category": "Electrónica",
        })
        self.assertTrue(v.relevante)

    def test_categoria_vehiculos_no_es_solar(self):
        v = self.lex.evaluar_registro({
            "product_name": "Vedca N1 nueva con batería",
            "category": "Vehículos",
        })
        self.assertFalse(v.relevante)

    def test_solar_solo_en_categoria_no_cuenta_en_nombre(self):
        v = self.lex.evaluar_registro({
            "product_name": "Lámpara solar para exteriores",
            "category": "Electrónica",
        })
        self.assertFalse(v.relevante)
        self.assertIn("sin término fuerte", " ".join(v.motivos))

    def test_solar_en_categoria_si_cuenta(self):
        v = self.lex.evaluar_registro({
            "product_name": "Artículo de temporada",
            "category": "Energía Solar",
        })
        self.assertTrue(v.relevante)


class TestPaginas(unittest.TestCase):
    def setUp(self):
        self.lex = lexico()
        self.bembete = sitios.obtener("OLP-002")

    def test_tipos_por_url(self):
        self.assertEqual(
            self.bembete.tipo_por_url("https://bembete.com/detalles/x-1"),
            TipoPagina.DETALLE,
        )
        self.assertEqual(
            self.bembete.tipo_por_url("https://bembete.com/b/c-Electronica/"),
            TipoPagina.LISTA,
        )
        self.assertEqual(
            self.bembete.tipo_por_url("https://bembete.com/art/algo"),
            TipoPagina.CONTEXTO,
        )

    def test_objetivo_bembete_250_en_30_dias(self):
        self.assertEqual(self.bembete.objetivo_paginas, 250)
        opciones = Opciones()
        self.assertEqual(opciones.ventana_dias, 30)
        self.assertEqual(opciones.max_intentos, 500)

    def test_prefiltro_de_slug(self):
        ok, _ = self.bembete.prefiltro(
            "https://bembete.com/detalles/inversor-bifasico-must-6kw-1/"
        )
        self.assertTrue(ok)
        for slug in (
            "lampara-solar-300w-1",
            "triciclo-con-baterias-de-gel-1",
            "bateria-para-celular-1",
            "patineta-electrica-con-bateria-1",
            "bateria-de-carro-12v-1",
            "bicicleta-electrica-nueva-de-litio-1",
            "moto-electrica-de-litio-1",
            "casa-con-paneles-solares-1",
        ):
            with self.subTest(slug=slug):
                ok, motivo = self.bembete.prefiltro(
                    f"https://bembete.com/detalles/{slug}/"
                )
                self.assertFalse(ok)
                self.assertTrue(motivo)

    def test_clasificacion_de_detalle(self):
        relevante = self.bembete.clasificar_pagina(
            "https://bembete.com/detalles/inversor-1",
            TipoPagina.DETALLE,
            EvidenciaPagina(titulo="Inversor Bifásico Must 6kW"),
            self.lex,
        )
        self.assertTrue(relevante.relevante)
        falsa = self.bembete.clasificar_pagina(
            "https://bembete.com/detalles/casa-1",
            TipoPagina.DETALLE,
            EvidenciaPagina(titulo="Casa con paneles solares"),
            self.lex,
        )
        self.assertFalse(falsa.relevante)


class TestSitemapDiario(unittest.TestCase):
    def test_selecciona_dias_recientes_y_filtra_detalles(self):
        indice = (
            "<sitemapindex>"
            "<loc>https://bembete.com/sitemap-posts/2026-10-23.xml</loc>"
            "<loc>https://bembete.com/sitemap-posts/2026-10-25.xml</loc>"
            "<loc>https://bembete.com/sitemap-posts/2026-10-24.xml</loc>"
            "</sitemapindex>"
        )
        diario = (
            "<urlset>"
            "<loc>https://bembete.com/detalles/panel-solar-1/</loc>"
            "<loc>https://bembete.com/b/c-Ferreteria/</loc>"
            "<loc>https://bembete.com/detalles/inversor-2/</loc>"
            "</urlset>"
        )

        class F(FakeFetcher):
            def obtener(self, url):
                self.peticiones.append(url)
                cuerpo = indice if "sitemap-index" in url else diario
                return Respuesta(url, url, 200, "application/xml",
                                 cuerpo.encode("utf-8"), "utf-8")

        fetcher = F()
        diarios = sitemap.sitemaps_diarios(
            fetcher, "Sitemap: https://bembete.com/sitemap-index.xml",
            "https://bembete.com", ventana_dias=2,
        )
        self.assertEqual([f.isoformat() for _, f in diarios], ["2026-10-25", "2026-10-24"])
        urls = sitemap.urls_de_sitemap_diario(fetcher, diarios[0][0], ("/detalles/",))
        self.assertEqual(
            urls,
            [
                "https://bembete.com/detalles/panel-solar-1/",
                "https://bembete.com/detalles/inversor-2/",
            ],
        )


class TestSunCarEInfinity(unittest.TestCase):
    def test_suncar_solo_ofertas_y_dedup_por_id(self):
        suncar = sitios.obtener("OLP-004")
        self.assertEqual(
            suncar.tipo_por_url("https://suncarsrl.com/tienda"),
            TipoPagina.CONTEXTO,
        )
        self.assertEqual(
            suncar.tipo_por_url("https://suncarsrl.com/ofertas"),
            TipoPagina.DATOS,
        )
        registros = []
        for i in range(33):
            registros.append({
                "campos": {"product_name": f"Oferta {i % 14}", "price": i},
                "campos_adicionales": {"id": f"OF-{i % 14:03d}"},
                "id_oferta": f"OF-{i % 14:03d}",
                "url_origen": "https://suncarsrl.com/ofertas",
            })
        aceptados, _ = suncar.filtrar_registros(registros, lexico())
        self.assertEqual(len(aceptados), 33)

        with tempfile.TemporaryDirectory() as tmp:
            recolector = Recolector(
                cargar_configuracion(RAIZ / "referencias" / "fuentes_internet.json"),
                Almacen(Path(tmp)), FakeFetcher(), Opciones(),
            )
            from herramientas.recoleccion.nucleo.almacen import IndiceFuente
            nuevos, duplicados = recolector._deduplicar(aceptados, IndiceFuente())
        self.assertEqual(len(nuevos), 14)
        self.assertEqual(len(duplicados), 19)

    def test_infinity_dedup_por_id_catalogo(self):
        infinity = sitios.obtener("OLP-005")
        registros = []
        for i in range(26):
            registros.append({
                "campos": {"product_name": f"Producto {i}"},
                "campos_adicionales": {"id_catalogo": f"cat-{i}"},
                "id_oferta": f"cat-{i}",
                "url_origen": "https://infinitysolarcuba.com/",
                "ubicacion_evidencia": (
                    f"bundle[0] ({'producto' if i < 17 else 'accesorio'})"
                ),
            })
        aceptados, _ = infinity.filtrar_registros(registros, lexico())
        self.assertEqual(len(aceptados), 26)
        self.assertEqual(
            sum(1 for r in aceptados if infinity.tipo_oferta(r) == "producto"), 17
        )
        self.assertEqual(
            sum(1 for r in aceptados if infinity.tipo_oferta(r) == "accesorio"), 9
        )


class TestRecolectorPasadaUnica(unittest.TestCase):
    def _fuente(self):
        from herramientas.recoleccion.nucleo.config import Fuente
        return Fuente(
            id="T-900", nombre="Sitio falso", url="https://falso.test",
            categoria="prueba", tipo="test", estado="verified", prioridad="alta",
            datos_esperados=("product_name", "price", "currency"),
        )

    def _ejecutar(self, total, objetivo, salida, prefiltro_negativo=False):
        sitio = SitioFalso(total, prefiltro_negativo)
        paginas = {f"https://falso.test/detalle/{i}": pagina(i) for i in range(total)}
        fetcher = FakeFetcher(paginas)
        with patch.dict(sitios.REGISTRO, {"T-900": sitio}):
            resumen = recolectar(
                cargar_configuracion(RAIZ / "referencias" / "fuentes_internet.json"),
                Almacen(Path(salida)), fetcher, Opciones(
                    objetivo_paginas=objetivo,
                    max_intentos=0,
                    simular=False,
                ),
                (self._fuente(),), "todo",
            )
        return resumen, fetcher

    def test_120_candidatos_para_en_100(self):
        with tempfile.TemporaryDirectory() as tmp:
            resumen, fetcher = self._ejecutar(120, 100, tmp)
            cont = resumen.fuentes["T-900"]
            self.assertEqual(cont.paginas_aceptadas, 100)
            self.assertEqual(len(fetcher.peticiones), 100)
            self.assertTrue(cont.objetivo_alcanzado)
            self.assertEqual(fetcher.max_en_curso, 1)

    def test_80_candidatos_reporta_objetivo_no_alcanzado(self):
        with tempfile.TemporaryDirectory() as tmp:
            resumen, _ = self._ejecutar(80, 100, tmp)
            cont = resumen.fuentes["T-900"]
            self.assertEqual(cont.paginas_aceptadas, 80)
            self.assertFalse(cont.objetivo_alcanzado)
            self.assertIn("80 de 100", cont.motivo_parada)

    def test_idempotencia_segunda_pasada(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._ejecutar(10, 100, tmp)
            datos = next(Path(tmp).glob("*/datos.jsonl"))
            lineas = len(datos.read_text(encoding="utf-8").splitlines())
            crudos = len(list(next(Path(tmp).glob("*/crudo")).iterdir()))

            resumen, fetcher = self._ejecutar(10, 100, tmp)
            cont = resumen.fuentes["T-900"]
            self.assertEqual(len(fetcher.peticiones), 0)
            self.assertEqual(cont.omitidas_por_dedup, 10)
            self.assertEqual(
                len(datos.read_text(encoding="utf-8").splitlines()), lineas
            )
            self.assertEqual(
                len(list(next(Path(tmp).glob("*/crudo")).iterdir())), crudos
            )

    def test_descartes_de_pagina_sin_contenido(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._ejecutar(10, 100, tmp, prefiltro_negativo=True)
            descartes = list(Path(tmp).glob("*/descartes.jsonl"))
            self.assertTrue(descartes)
            registros = [
                json.loads(linea)
                for linea in descartes[0].read_text(encoding="utf-8").splitlines()
            ]
            self.assertTrue(any(d["nivel"] == "pagina" for d in registros))
            pagina_descartada = next(d for d in registros if d["nivel"] == "pagina")
            self.assertIn("prefiltro", pagina_descartada["motivo"])
            self.assertNotIn("html", pagina_descartada)

    def test_resumen_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._ejecutar(5, 100, tmp)
            datos = json.loads((Path(tmp) / "resumen.json").read_text(encoding="utf-8"))
            self.assertEqual(datos["fase"], "todo")
            self.assertIn("T-900", datos["fuentes"])
            self.assertIn("lexico_hash", datos)
            self.assertIn("configuracion", datos)
            self.assertEqual(datos["totales"]["registros_aceptados"], 5)


if __name__ == "__main__":
    unittest.main()
