# Revolico (OLP-001) — recolección manual

Revolico está **excluido de la recolección automática** (ver
`nucleo/politica_sitios.json`, entrada `OLP-001`). Todo su contenido responde a
un *challenge* gestionado de Cloudflare (`HTTP 403`, `cf-mitigated: challenge`)
en todas las rutas —incluidas `api.revolico.com`, `robots.txt` y
`sitemap.xml`—, por lo que no puede obtenerse con HTTP simple ni, dadas las
restricciones del entorno, con navegador.

## Cómo depositar el material

1. Abre las páginas en un navegador normal.
2. Guarda cada página como HTML (*Guardar como… → Página web, solo HTML*) o
   copia el HTML completo desde «Ver código fuente».
3. Colócalos en esta carpeta (`manual/`) con un nombre que describa la página,
   por ejemplo:

   ```
   manual/
     busqueda-panel-solar.html
     anuncio-inversor-3kw.html
   ```

4. Anota, si es posible, la URL de origen y la fecha de consulta dentro del
   propio archivo o en un `manual/indice.md`.

Estos archivos quedan fuera del flujo automático: no se deduplican, no se
puntúan por relevancia ni se reescriben. Se conservan tal como se descargaron,
como fuente primaria del proyecto.
