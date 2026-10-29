# Bembete: filtro de provincias y recolección de 250 anuncios

Fecha: 2026-10-29
Fuente: OLP-002 Bembete
Estado: completado y auditado; dataset de 250 anuncios

## Objetivo

Sustituir el dataset anterior de Bembete por una recolección nueva en la que
solo cuenten como válidas las páginas de detalle cuyo texto no mencione las
provincias o municipios indicados por el usuario: Pinar del Río, Artemisa,
Mayabeque, Matanzas, Cienfuegos, Ciego de Ávila, Sancti Spíritus, Villa Clara,
Camagüey, Las Tunas, Santiago de Cuba, Holguín, Granma y Guantánamo.

Se mantienen el objetivo de 250 anuncios de detalle únicos, la ventana de 30
días, la pasada única secuencial, el respeto a `robots.txt`/`Crawl-delay` y la
deduplicación por `id_oferta`/URL canónica.

## Cambios en la herramienta

- `sitios/base.py`: `EvidenciaPagina` incorpora el campo `texto`.
- `nucleo/recolector.py`: el texto extraído de la página se pasa a la
  evidencia de clasificación.
- `sitios/bembe.py`: nueva constante `PROVINCIAS_EXCLUIDAS`, normalizada
  (minúsculas, sin acentos), y comprobación antes de evaluar la relevancia. Se
  incluyen `guantanamo` y la grafía errónea `gauntanamo`.
- Una página descartada por provincia no cuenta para el objetivo, no guarda
  crudo ni texto y deja el motivo en `descartes.jsonl`.
- `pruebas/test_pasada_unica.py`: pruebas de exclusión con las 14 provincias y
  de aceptación cuando el texto solo menciona La Habana.

## Ejecución

Se eliminó el dataset anterior de Bembete (339 registros; recuperable desde el
commit `dbec1f3`) y se lanzó:

```bash
herramientas/recoleccion/ejecutar.sh --fuente OLP-002 --todo \
  --objetivo-paginas 250 --max-intentos 4000 --ventana-dias 30 \
  --salida archivos/recoleccion
```

La ejecución tuvo dos fases:

1. **27 de octubre, 20:19–21:59 UTC.** 145 anuncios válidos en 1.490 intentos.
   Se interrumpió por pérdida de conexión; los JSONL quedaron íntegros y los 9
   errores de red se registraron como transitorios.
2. **29 de octubre, 14:10–15:10 UTC.** Tras resolver el DNS de proot, 105
   anuncios nuevos en 1.095 intentos, 0 errores y objetivo alcanzado.

## Resultados

- **250 anuncios válidos** (145 + 105), 250 registros, 250 crudo y 250 texto.
- 2.585 intentos de red en total; 9 errores transitorios, todos de la primera
  fase.
- 2.326 páginas descartadas: 2.165 por provincia, 147 por falta de término
  fuerte, 7 por patrón negativo, 5 por batería de vehículo y el resto por
  motivos puntuales.
- 42.717 candidatos descartados por el prefiltro de slug, sin descarga.
- Sitemaps usados: 23 al 29 de octubre (7 días).
- 0 registros descartados y 0 duplicados.

## Auditoría

- 250 `id_oferta`, 250 URLs canónicas y 250 hashes de contenido únicos.
- Las 250 páginas aceptadas son de tipo `detalle` y respondieron HTTP 200.
- 250 registros con `product_name` y precio; 44 conservan el precio `1 CUP`
  que publica el sitio.
- 0 textos aceptados contienen alguna de las provincias excluidas.
- 0 líneas JSON inválidas, 0 archivos vacíos y 0 registros sin página aceptada
  asociada.
- `resumen.json` registra 105 registros porque corresponde a la última pasada;
  el dataset total es de 250 (145 previos + 105 nuevos).

## Incidencia de DNS en proot

Al reanudar, proot no resolvía nombres: los DNS `8.8.8.8` y `8.8.4.4` no
respondían (puerto 53 bloqueado), aunque el resolvedor de Android y la conexión
del dispositivo funcionaban. Sin `robots.txt`, la herramienta cayó a
`/sitemap.xml`, que ya no es el índice (ahora es `/sitemap-index.xml`), no
encontró sitemaps diarios y terminó sin recolectar.

Se verificó que `robots.txt` declara `https://bembete.com/sitemap-index.xml` y
se añadió una entrada temporal en `/etc/hosts` de proot con las IPs de
CloudFront (`13.224.30.38`, `.42`, `.76`, `.79`). Con eso la reanudación leyó 30
sitemaps diarios y completó la meta. Si cambian las IPs de CloudFront hay que
actualizar la entrada; para revertirla basta con eliminar esas líneas de
`/etc/hosts` dentro de proot.

## Cómo repetir o reanudar

```bash
# Reanudar sin repetir lo ya capturado
herramientas/recoleccion/ejecutar.sh --fuente OLP-002 --todo \
  --objetivo-paginas 250 --max-intentos 4000 --ventana-dias 30 \
  --salida archivos/recoleccion

# Pruebas del módulo
herramientas/recoleccion/pruebas/probar.sh -p "test_pasada_unica.py"
```

## Archivos clave

- `herramientas/recoleccion/sitios/bembe.py`: filtro de provincias.
- `herramientas/recoleccion/sitios/base.py`: campo `texto` en la evidencia.
- `herramientas/recoleccion/nucleo/recolector.py`: paso del texto a la
  clasificación.
- `herramientas/recoleccion/pruebas/test_pasada_unica.py`: pruebas nuevas.
- `archivos/recoleccion/OLP-002_bembete/`: dataset final de 250 anuncios.

## Límites y pendientes

- El filtro de provincias usa el texto completo de la página; si el sitio
  añadiera esas provincias en menús o bloques comunes, podría descartar páginas
  de La Habana. En la muestra real las coincidencias eran la ubicación del
  vendedor.
- La entrada de `/etc/hosts` es un parche local, no una solución de red.
- El trabajo de Revolico que había sin commitear en el árbol se dejó intacto y
  fuera de este commit.
