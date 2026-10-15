"""Núcleo de la herramienta de recolección.

Reúne la infraestructura común a todos los sitios: obtención HTTP, política de
acceso, contenido observable, extracción estructurada genérica, deduplicación y
almacenamiento, relevancia y orquestación.

No contiene lógica específica de ningún sitio: eso vive en
``herramientas.recoleccion.sitios``.
"""
