"""Pruebas de los sitios especializados: registro, semillas y extractores."""

import json
import unittest

from herramientas.recoleccion.nucleo.config import Fuente
from herramientas.recoleccion.nucleo.fetcher import Respuesta
from herramientas.recoleccion import sitios

FECHA = "2026-10-15T00:00:00+00:00"


def fuente(fid: str, nombre: str, url: str) -> Fuente:
    return Fuente(
        id=fid, nombre=nombre, url=url, categoria="c", tipo="t",
        estado="verified", prioridad="high",
        datos_esperados=(
            "product_name", "price", "currency", "power_w", "brand", "model",
            "availability", "description", "warranty", "installation",
        ),
    )


class FakeFetcher:
    """Fetcher mínimo para probar el descubrimiento por sitemap sin red."""

    def __init__(self, xml: str) -> None:
        self.xml = xml

    def obtener(self, url: str) -> Respuesta:
        return Respuesta(
            url_solicitada=url, url_final=url, estado_http=200,
            content_type="application/xml", contenido=self.xml.encode("utf-8"),
            encoding="utf-8",
        )


class TestRegistro(unittest.TestCase):
    def test_sitios_conocidos(self):
        self.assertEqual(sitios.obtener("OLP-002").nombre, "Bembete")
        self.assertEqual(sitios.obtener("OLP-004").nombre, "SunCar")
        self.assertEqual(sitios.obtener("OLP-005").nombre, "Infinity Energy Cuba")

    def test_revolico_no_tiene_modulo(self):
        # Revolico se recolecta a mano (excluida en la política).
        self.assertIsNone(sitios.obtener("OLP-001"))

    def test_fuente_desconocida_usa_generico(self):
        f = fuente("OLP-999", "Otra", "https://otra.test")
        sitio = sitios.para_fuente(f)
        self.assertEqual(sitio.semillas(None, None), ["https://otra.test"])


class TestBembete(unittest.TestCase):
    def test_extrae_incrustados(self):
        payload = {"pageProps": {"ofertas": [
            {"nombre": "Kit 8kW Felicity", "precio": 6460, "moneda": "USD"},
        ]}}
        html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
        f = fuente("OLP-002", "Bembete", "https://bembete.com")
        regs = sitios.obtener("OLP-002").extraer(html, "", "https://bembete.com/", FECHA, f)
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0]["metodo_extraccion"], "adaptador_bembete")


class TestSunCarSitemap(unittest.TestCase):
    def test_semillas_filtra_por_patron(self):
        xml = (
            "<urlset>"
            "<url><loc>https://suncarsrl.com/ofertas</loc></url>"
            "<url><loc>https://suncarsrl.com/productos</loc></url>"
            "<url><loc>https://suncarsrl.com/blog/nota</loc></url>"
            "<url><loc>https://otro.test/ofertas</loc></url>"
            "</urlset>"
        )
        sitio = sitios.obtener("OLP-004")
        urls = sitio.semillas(FakeFetcher(xml), "User-agent: *\nAllow: /")
        self.assertIn("https://suncarsrl.com/ofertas", urls)
        self.assertIn("https://suncarsrl.com/productos", urls)
        self.assertNotIn("https://suncarsrl.com/blog/nota", urls)
        self.assertNotIn("https://otro.test/ofertas", urls)


class TestInfinity(unittest.TestCase):
    """El catálogo viaja en un bundle JavaScript, no en el HTML."""

    SHELL = (
        '<html><head>'
        '<script type="module" crossorigin src="/assets/index-abc123.js"></script>'
        '</head><body><div id="root"></div></body></html>'
    )
    #: Bundle minificado de ejemplo: catálogo + accesorios + arreglo no-catálogo.
    BUNDLE = (
        'var x=[{id:"tv",name:"Televisor",defaultWatts:120,defaultHours:4}];'
        'var q5=[{id:"sistema-5kw",name:"Sistema Solar 5 kW",price:"$5,000 USD",'
        'shortDescription:"Sistema de 5 kW",keySpecs:["Batería 5 kWh"],'
        'image:"https://cdn/x.jpg",badge:"OFERTA",warranty:"2 años"},'
        '{id:"agotado-1",name:"Kit SACO 12 kW",price:"Agotado",'
        'shortDescription:"Kit agotado",keySpecs:[]}];'
        'var OA=[{id:"cable",name:"Cable Fotovoltaico",priceDisplay:"$4 USD / m",'
        'prices:[{label:"metro",value:"$4 USD"}],description:"Cable calibre 10",'
        'details:["Para instaladores"],alt:"Cable"}];'
    )

    def test_activos_declara_el_bundle(self):
        sitio = sitios.obtener("OLP-005")
        self.assertEqual(sitio.activos(self.SHELL, "https://infinitysolarcuba.com/"),
                         ["/assets/index-abc123.js"])

    def test_extrae_productos_y_accesorios_del_bundle(self):
        sitio = sitios.obtener("OLP-005")
        f = fuente("OLP-005", "Infinity Energy Cuba", "https://infinitysolarcuba.com/")
        activos = {"https://infinitysolarcuba.com/assets/index-abc123.js": self.BUNDLE}
        regs = sitio.extraer(self.SHELL, "", "https://infinitysolarcuba.com/", FECHA, f, activos=activos)
        nombres = sorted(r["campos"]["product_name"] for r in regs)
        self.assertEqual(nombres, ["Cable Fotovoltaico", "Kit SACO 12 kW", "Sistema Solar 5 kW"])
        self.assertTrue(all(r["metodo_extraccion"] == "bundle_js" for r in regs))

        por_nombre = {r["campos"]["product_name"]: r for r in regs}
        kit = por_nombre["Sistema Solar 5 kW"]
        self.assertEqual(kit["campos"]["price"], "5,000")
        self.assertEqual(kit["campos"]["currency"], "USD")
        self.assertEqual(kit["campos_adicionales"]["insignia"], "OFERTA")
        self.assertEqual(kit["campos"]["warranty"], "2 años")

        agotado = por_nombre["Kit SACO 12 kW"]
        self.assertEqual(agotado["campos"]["availability"], "Agotado")
        self.assertNotIn("price", agotado["campos"])

    def test_ignora_arreglos_que_no_son_catalogo(self):
        sitio = sitios.obtener("OLP-005")
        f = fuente("OLP-005", "Infinity Energy Cuba", "https://infinitysolarcuba.com/")
        solo_televisores = 'var x=[{id:"tv",name:"Televisor",defaultWatts:120}];'
        regs = sitio.extraer(
            self.SHELL, "", "https://infinitysolarcuba.com/", FECHA, f,
            activos={"https://infinitysolarcuba.com/assets/index-abc123.js": solo_televisores},
        )
        self.assertEqual(regs, [])


if __name__ == "__main__":
    unittest.main()
