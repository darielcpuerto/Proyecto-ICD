Journal del proyecto
2026-09-17 — Creación del proyecto 
Se creó el repositorio del proyecto. Se estableció una estructura inicial para organizar los archivos, del proyecto.

Estado: proyecto iniciado.

2026-10-08 — Organización del proyecto

Se reorganizan los archivos del proyecto y se pasa la documentación a la raíz del repositorio. Subí los cambios a GitHub. El proyecto ya tiene su documentación inicial versionada.

Estado: estructura organizada; continúa el desarrollo de la investigación.

2026-10-15 — Herramienta de recolección de oferta solar

Se desarrolla, por fases, la herramienta `herramientas/recoleccion/` para
recolectar y preservar la oferta solar publicada en las fuentes de
`referencias/fuentes_internet.json`, respetando las reglas de calidad del dato.
Incluye política de acceso (robots.txt, avisos legales y excepciones
autorizadas), descarga con trazabilidad (crudo, texto, imágenes y manifiesto),
extracción estructurada sin inferir valores (JSON-LD, datos incrustados y
heurística de texto) y adaptadores para Revolico, Bembete y SunCar.

Se añade el uso de un navegador Chromium del sistema mediante `executable_path`
(opciones `--chromium` y `--render`, variable `CHROMIUM_EXECUTABLE` y argumentos
extra con `CHROMIUM_ARGS`). No se descarga ni reinstala nada; Playwright ya
estaba instalado en el venv de análisis. Comprobación real: el navegador
arranca, pero en este entorno (proot-distro sobre Android) los procesos hijo de
Chromium mueren con SIGTRAP al crear la primera página, por lo que no es posible
renderizar JavaScript aquí. La herramienta lo detecta, lo informa y continúa con
la obtención estática sin interrumpir la recolección. La configuración, los
requisitos y el diagnóstico quedan documentados en
`herramientas/recoleccion/ENTORNO.md`.

Se crea la carpeta `handoffs/` para los traspasos de sesión y se actualiza
`.gitignore` para excluir cachés y temporales de Python. Los cambios de la
herramienta se suben a GitHub.

Estado: herramienta de recolección operativa en estático y versionada;
renderizado integrado y documentado, pendiente de un entorno que permita crear
procesos de Chromium para validarlo de extremo a extremo.

2026-10-15 — Reimplementación de la herramienta de recolección

Se reimplementa `herramientas/recoleccion/` separando el núcleo común
(`nucleo/`) de un módulo por sitio (`sitios/`: Revolico, Bembete, SunCar e
Infinity) reunidos en un registro. Se retiran `adaptadores.json/.py` y
`extractores.py`.

Cambios principales:

- Deduplicación por contenido: el crudo y el texto se nombran por hash de su
  contenido (no por fecha), no se repiten URLs ya intentadas ni se duplican
  registros en `datos.jsonl`. El crudo se conserva en texto plano dentro de Git.
- Las imágenes salen del flujo y del catálogo
  (`download_images_when_accessible: false`; `images` retirado de
  `content_targets`).
- Puerta de relevancia: el descubrimiento escribe `candidatos.jsonl`
  (versionado) y solo se descarga lo aprobado por archivo o por umbral
  (`--aprobar-relevantes`). El lexicón vive en `referencias/relevancia.json`,
  derivado de los `content_targets` y del dominio solar, y exige al menos un
  término fuerte.
- Flujo en dos fases (`--descubrir` y `--recolectar`) con `--forzar`.
  Idempotencia verificada: una segunda pasada añade 0 bytes.
- Suite de pruebas reescrita (23 pruebas) e `ENTORNO.md` actualizado.

Se ejecuta una recolección por sitio, con un límite de 250 páginas por sitio:
Bembete 9 páginas y 292 registros; SunCar 6 páginas y 47 registros; Revolico 4
semillas con HTTP 403 (sin datos); Infinity 1 página (SPA sin render, sin
datos).

Estado: herramienta reestructurada y verificada, con los datos recolectados
versionados; pendiente evaluar el renderizado JavaScript para los sitios SPA y
las categorías, y revisar el bloqueo de Revolico.

2026-10-15 — Recolección sin navegador, exclusión de Revolico e Infinity desde el bundle

Se corrige y cierra la reimplementación de `herramientas/recoleccion/` con tres
decisiones:

- **Sin navegador.** Se elimina Chromium/Playwright por completo
  (`nucleo/render.py`, opciones `--render`/`--chromium`, atributo
  `Sitio.requiere_js`). Toda la obtención es HTTP `GET` con `robots.txt`
  respetado. `ENTORNO.md` pasa a describir las «estrategias sin navegador».
- **Revolico (OLP-001) excluida.** Todas sus rutas responden `HTTP 403` con
  `cf-mitigated: challenge` (challenge gestionado de Cloudflare), también su API
  y `robots.txt`; no hay bypass con HTTP simple. La política admite exclusiones
  explícitas (`excluir: true`, evaluadas antes que robots/avisos) y Revolico se
  recolecta a mano en `archivos/recoleccion/OLP-001_revolico/manual/`.
- **Infinity (OLP-005) sin navegador.** Es un SPA que devuelve la misma cáscara
  para cualquier ruta; el catálogo viaja en el bundle `/assets/index-*.js`. Se
  añade el mecanismo de *activos* (`Sitio.activos()` + `Sitio.extraer(activos=…)`)
  y el adaptador localiza los arreglos de objetos `var=[{…}]` y los interpreta
  con un lector de literales JavaScript. Resultado: 17 productos y 9 accesorios.

Además se corrigió la decodificación en `fetcher` (respetar el `charset`
declarado y preferir UTF-8 cuando no lo hay, en lugar del ISO-8859-1 por defecto
de `text/*`), que corrompía los acentos.

Se vacían los datos y se recolecta de nuevo (una pasada, ≤250 páginas/sitio):
Bembete 10 páginas y 305 registros; SunCar 4 páginas y 33 registros; Infinity 1
página, 1 activo y 26 registros; Revolico excluida. Suite de 28 pruebas OK.
Idempotencia verificada: una segunda pasada añade 0 bytes.

Estado: herramienta sin navegador y verificada; datos recolectados versionados.
Revolico queda como descarga manual documentada.
