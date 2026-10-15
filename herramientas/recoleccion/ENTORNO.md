# Entorno y requisitos del renderizado con JavaScript

Este documento describe cómo la herramienta de recolección
(`herramientas/recoleccion/`) obtiene páginas que se construyen en el cliente
usando un navegador Chromium real, y qué se necesita para que ese renderizado
funcione. Complementa, sin repetir, las bases metodológicas del proyecto y las
reglas de `reglas/calidad-dato.md`.

## 1. Qué navegador se usa

No se usa el navegador que Playwright descarga con `playwright install`. Se usa
un Chromium ya presente en el sistema, indicado con `executable_path` (equivalente
a `executable_path=` en la API de Playwright). La ruta se resuelve en este orden:

1. la opción de línea de comandos `--chromium RUTA`;
2. la variable de entorno `CHROMIUM_EXECUTABLE`;
3. el valor por defecto `render.EJECUTABLE_POR_DEFECTO`
   (`/opt/chromium/chrome-linux-arm64/chrome`).

Si la ruta indicada no corresponde a un archivo existente, el renderizador
lanza un error claro y la recolección continúa sin JavaScript (obtención
estática).

## 2. Requisitos

| Componente | Requisito verificado en este equipo |
| --- | --- |
| Contenedor | `proot-distro login ubuntu` |
| Intérprete | `/root/DataScience/.venv/bin/python` (Python 3.14) |
| Paquete | `playwright` 1.64.0 (ya instalado en el venv) |
| Navegador | Chrome for Testing 156.0.8078.4 |
| Ejecutable | `/opt/chromium/chrome-linux-arm64/chrome` |

Instalación de referencia (no ejecutar de nuevo si ya está):

```bash
/root/DataScience/.venv/bin/pip install playwright
```

No hace falta `playwright install chromium` ni `install-deps`: el navegador y
sus dependencias se toman del sistema. Este módulo no descarga navegadores ni
instala paquetes.

### Argumentos del navegador

Los argumentos base son `--no-sandbox` y `--disable-dev-shm-usage`, necesarios
en contenedores y en proot. Se pueden añadir más con la variable
`CHROMIUM_ARGS` (separados por espacios), por ejemplo:

```bash
CHROMIUM_ARGS="--disable-gpu --single-process" \
  herramientas/recoleccion/ejecutar.sh --fuente OLP-002
```

## 3. Uso

```bash
# Renderizar una fuente concreta (Playwright debe estar instalado)
herramientas/recoleccion/ejecutar.sh --fuente OLP-002

# Forzar el renderizado aunque el adaptador no lo marque, o indicar el binario
herramientas/recoleccion/ejecutar.sh --fuente OLP-002 --render --chromium /opt/chromium/chrome-linux-arm64/chrome
```

Los adaptadores de `adaptadores.json` marcan con `"requiere_js": true` las
fuentes cuyo contenido se construye en el cliente. La opción `--render` fuerza
el renderizado para cualquier fuente.

Antes de renderizar, cada URL sigue comprobándose contra `robots.txt`; el
renderizado no omite esa verificación.

## 4. Comportamiento y limitación conocidos

Estado verificado en este equipo (proot-distro sobre Android):

- `render.disponible()` devuelve `True`: Playwright está instalado.
- El navegador **arranca**: Chromium abre el puerto de DevTools y Playwright
  obtiene un proceso vivo con el ejecutable indicado.
- Al crear la primera página, los procesos hijo de Chromium (servicio de red y
  *renderer*) mueren con `SIGTRAP`; incluso `about:blank` falla. Playwright
  informa `TargetClosedError`. El error del GPU es secundario
  (`GPU process isn't usable. Goodbye.`).
- Por tanto, **en este entorno no es posible obtener HTML renderizado**. La
  herramienta lo detecta, lo informa una sola vez, cierra el navegador y
  continúa con la obtención estática. El resultado estático de Bembete sigue
  siendo válido: la portada y las páginas de categoría accesibles sin JS se
  conservan con su procedencia.

Combinaciones probadas (todas fallan al crear la página): `--disable-gpu`,
`--disable-dev-shm-usage`, `--no-zygote`, `--single-process`,
`--in-process-gpu`, `--disable-software-rasterizer`, `--ozone-platform=headless`,
`--use-gl=disabled`, `--use-angle=swiftshader`, `--disable-features=Vulkan`,
`--disable-gpu-compositing`, `--disable-gpu-process-crash-limit`,
`NetworkServiceInProcess`, `NetworkServiceSandbox`, `PROOT_NO_SECCOMP=1`, entre
otras.

### Requisitos para que el renderizado funcione de verdad

El renderizado con JavaScript requiere un entorno donde Chromium pueda crear
procesos hijo (*zygote*, servicio de red y *renderer*). En la práctica:

- no ejecutarlo bajo `proot`/`proot-distro` sobre Android, o
- disponer de un kernel/host que aporte los espacios de nombres y llamadas al
  sistema que Chromium necesita, manteniendo `--no-sandbox` por ejecutarse como
  root.

El código ya está preparado para ese caso: basta con que el ejecutable arranque
y pueda abrir páginas; no requiere cambios, solo que el entorno lo permita.

## 5. Resumen

- El renderizado es **opcional y no bloqueante**: si Chromium no puede
  renderizar, la recolección continúa de forma estática y así queda anotado en
  los avisos de la ejecución.
- El ejecutable del navegador se toma del sistema (no del que descarga
  Playwright), tal como se pidió.
- La configuración y el diagnóstico descritos arriba permiten reproducir el
  estado actual o migrar a un entorno que sí permita el renderizado, sin
  cambiar el código.
