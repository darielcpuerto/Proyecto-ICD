# Handoff de sesión — Herramienta de recolección web

Fecha: 2026-10-15
Ámbito: `herramientas/recoleccion/` (recolección de oferta solar desde Internet).
Estado del repositorio: **sin commit** por esta sesión. `git status`:
`M journal/JOURNAL.md`, `?? herramientas/`, `?? handoffs/`,
`?? archivos/recoleccion/`.
Último commit existente: `70573f8 Actualiza el diario del proyecto`.

Este documento vive en `handoffs/`. Convención de nombre:
`AAAA-MM-DD-tema.md` (véase `handoffs/README.md`).

## 1. Objetivo

Construir, por fases, una herramienta en Python que recolecte y preserve la
oferta solar publicada en las fuentes de Internet del catálogo
`referencias/fuentes_internet.json`, respetando `reglas/calidad-dato.md`
(trazabilidad, no inferir, no convertir moneda, distinguir disponibilidad
anunciada de stock verificado, no tratar resultados de buscadores como dato).

## 2. Qué se hizo

- **Fase 0** — Clasificación de fuentes y detección de un conflicto de
  cumplimiento en SunCar (aviso en `robots.txt` que prohíbe recolección
  automatizada aunque las directivas `Allow` la permiten).
- **Fase 1** — Núcleo: `politica.py`, `extraccion.py`, `extractor.py`,
  `fetcher.py`, `storage.py`, `config.py`, fixtures y pruebas.
- **Fase 2** — Separación `campos` (objetivo) / `campos_adicionales`;
  `sitemap.py`, `adaptadores.py`, `adaptadores.json`; adaptador de SunCar por
  sitemap. Corrección de comparación de dominio (`www.` vs sin `www.`).
- **Fase 3** — `extractores.py` (adaptadores Revolico: Apollo + feed SSR;
  Bembete: flight stream de Next.js), `render.py` (Playwright diferido),
  integración en `recolector.py`/`__main__.py`, opción `--render`.
- **Render con Chromium del sistema** — `render.py` usa `executable_path`
  (no descarga de Playwright); opción `--chromium`, variable
  `CHROMIUM_EXECUTABLE`, argumentos extra con `CHROMIUM_ARGS`. Manejo robusto de
  la caída del navegador y degradación a obtención estática.
- **Documentación** — `herramientas/recoleccion/ENTORNO.md` (configuración y
  requisitos del render) y entrada en `journal/JOURNAL.md`.

## 3. Archivos clave

| Archivo | Rol |
| --- | --- |
| `config.py` | Carga/valida catálogo y filtra fuentes |
| `fetcher.py` | HTTP con retardo, reintentos y `robots.txt` |
| `politica.py` + `politica_sitios.json` | Decisión de acceso y excepciones (SunCar) |
| `sitemap.py` + `adaptadores.py` + `adaptadores.json` | Semillas por sitemap/patrones/explícitas y `requiere_js` |
| `extractor.py` | Contenido observable de una página (título, texto, imágenes, enlaces) |
| `extraccion.py` | JSON‑LD, datos incrustados (Next.js) y heurística de precios |
| `extractores.py` | Adaptadores de sitio (`revolico`, `bembete`) |
| `render.py` | Renderizado JS opcional con Chromium del sistema |
| `recolector.py` | Orquestación por fuente, fallback estático, manifiesto |
| `storage.py` | Salida en `archivos/recoleccion/<ID>_<slug>/` |
| `__main__.py` | CLI |
| `ejecutar.sh` | Envoltura con el venv de proot |
| `pruebas/` | `probar.sh`, `test_recoleccion.py`, `fixtures/` |
| `ENTORNO.md` | Configuración y requisitos del render |

## 4. Cómo ejecutar y probar

```bash
herramientas/recoleccion/ejecutar.sh --listar
herramientas/recoleccion/ejecutar.sh --fuente OLP-002 --simular
herramientas/recoleccion/ejecutar.sh --fuente OLP-004 --sin-imagenes
herramientas/recoleccion/ejecutar.sh --fuente OLP-002 --render \
    --chromium /opt/chromium/chrome-linux-arm64/chrome
herramientas/recoleccion/pruebas/probar.sh
```

Entorno: `proot-distro login ubuntu` + `/root/DataScience/.venv/bin/python`
(Python 3.14; requests, beautifulsoup4, pandas, playwright 1.64.0). No crear
otro venv ni reinstalar dependencias.

## 5. Resultados verificados

- Pruebas: **19 OK, 1 omitida** (la de “Playwright no instalado”, porque sí lo
  está).
- Salida acumulada en `archivos/recoleccion/` (líneas de `datos.jsonl`
  **acumuladas entre corridas**, no únicas):
  - `OLP-001_revolico` — 359
  - `OLP-002_bembete` — 3118
  - `OLP-004_suncar` — 57
- Render: `disponible()=True`, ejecutable resuelto
  `/opt/chromium/chrome-linux-arm64/chrome`, **arranque OK** (Chrome for Testing
  156.0.8078.4), pero **crear página falla** (`TargetClosedError`); la
  herramienta avisa y sigue en estático.

## 6. Decisiones

- Fuente de configuración única: `referencias/fuentes_internet.json`.
- Validación de Fase 1 con fixtures locales + fuentes permitidas.
- Un carpeta por fuente (sin subcarpetas por corrida; el usuario declinó
  separar corridas).
- SunCar se recolecta pese al aviso, por autorización del usuario registrada en
  `politica_sitios.json`.
- Navegador: se usa el Chromium del sistema vía `executable_path`; no se
  ejecuta `playwright install chromium`.

## 7. Bloqueo actual

En este entorno (`proot-distro` sobre Android) Chromium **no puede crear
procesos hijo**: los procesos de red/renderer mueren con `SIGTRAP` incluso con
`about:blank`. Probadas muchas combinaciones de flags (ver `ENTORNO.md`), todas
fallan. Consecuencia: los listados de categoría de Bembete y el SPA de Infinity
(OLP‑005) no se obtienen aquí; el resto se recolecta en estático.

## 8. Pendientes / próximos pasos

1. **Fase 4 — `.gitignore`**: ignorar cachés y temporales (`__pycache__/`,
   `.venv`, temporales) sin excluir documentación ni datos importantes.
   Revisar `archivos/` antes de tocar; el `.gitignore` actual solo ignora copias
   de seguridad locales.
2. Revisar las **semillas de Revolico**: hoy devuelven `403` (problema del
   sitio, no de la herramienta) y OLP‑001 puede quedar en 0 páginas.
3. Decidir el destino del render JS: dejarlo documentado como limitación o
   migrar la ejecución a un entorno que permita procesos de Chromium.
4. Valorar un adaptador para **Infinity (OLP‑005)** cuando haya render disponible.
5. No hay commits pendientes de hacer por indicación del usuario.

## 9. Restricciones a respetar

- No hacer commit.
- No borrar archivos ni sobrescribir trabajo del usuario sin revisarlo antes.
- No reproducir/duplicar la metodología del proyecto; consultar `README.md`,
  `referencias/contexto/` y `reglas/calidad-dato.md`.
- Trabajar por fases con validación entre ellas.
