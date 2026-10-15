Journal del proyecto
2026-09-17 — Creación del proyecto 
Se creó el repositorio del proyecto. Se estableció una estructura inicial para organizar los archivos, del proyecto.

Estado: proyecto iniciado.

2026-10-08 — Organización del proyecto

Se reorganizan los archivos del proyecto y se pasa la documentación a la raíz del repositorio. Subí los cambios a GitHub. El proyecto ya tiene su documentación inicial versionada.

Estado: estructura organizada; continúa el desarrollo de la investigación.

2026-10-15 — Soporte de renderizado con JavaScript (Playwright)

Se añade a la herramienta de recolección el uso de un navegador Chromium del
sistema mediante `executable_path` (opciones `--chromium`, `--render`, variable
`CHROMIUM_EXECUTABLE` y argumentos extra con `CHROMIUM_ARGS`). No se descarga ni
reinstala nada; Playwright ya estaba instalado en el venv de análisis.

Comprobación real: el navegador arranca, pero en este entorno (proot-distro
sobre Android) los procesos hijo de Chromium mueren con SIGTRAP al crear la
primera página, por lo que no es posible renderizar JavaScript aquí. La
herramienta lo detecta, lo informa y continúa con la obtención estática sin
interrumpir la recolección. La configuración, los requisitos y el diagnóstico
quedan documentados en `herramientas/recoleccion/ENTORNO.md`.

Estado: renderizado integrado y documentado; pendiente de un entorno que
permita crear procesos de Chromium para validarlo de extremo a extremo.
