# Análisis del Mercado Solar Cubano

Proyecto académico de Introducción a la Ciencia de Datos (ICD),
desarrollado en MATCOM, Universidad de La Habana.

## Objetivo principal

Caracterizar la relación entre la necesidad energética y la
posibilidad económica de cubanos con la oferta del mercado solar.

## Enfoque de investigación

El proyecto sigue el hilo conductor:

**NECESIDAD → CAPACIDAD ECONÓMICA → OFERTA → ADECUACIÓN → BRECHAS**

Se busca estudiar las necesidades energéticas de las personas,
sus posibilidades económicas, la oferta solar observada en Cuba
y los posibles desajustes entre estos elementos.

## Objetivos de investigación

1. **Necesidades:** caracterizar las necesidades energéticas y
   prioridades de distintos usuarios.
2. **Posibilidades económicas:** estudiar las condiciones y
   restricciones que influyen en la adquisición de soluciones solares.
3. **Oferta:** caracterizar la oferta observada, sus características
   técnicas, precios y distribución geográfica.
4. **Adecuación:** evaluar qué soluciones observadas podrían resultar
   potencialmente adecuadas para distintos perfiles.
5. **Brechas:** identificar los principales desajustes entre necesidades,
   posibilidades económicas y oferta observada.

## Fuentes de datos

El proyecto contempla tres fuentes principales:

- **Personas:** necesidades, prioridades, experiencias, presupuesto
  y percepción de precios y disponibilidad.
- **Internet:** anuncios y ofertas de productos solares, características
  técnicas, precios, vendedores y disponibilidad anunciada.
- **Instituciones:** información estadística y contexto económico,
  energético, territorial y regulatorio.

Estas fuentes tienen funciones distintas y se utilizarán de forma
complementaria cuando los datos lo permitan.

## Estructura del repositorio

```text
.
├── README.md
├── .gitignore
├── archivos/
├── journal/
│   └── JOURNAL.md
├── referencias/
│   ├── contexto/
│   │   ├── objetivos.md
│   │   ├── preguntas-investigacion.md
│   │   ├── metodologia.md
│   │   └── fuentes-datos.md
│   └── fuentes_internet.json
└── reglas/
    └── calidad-dato.md
```

## Estado actual

El proyecto cuenta con documentación inicial sobre objetivos,
preguntas de investigación, metodología, fuentes de datos y
principios de calidad del dato.

La operacionalización detallada, los instrumentos de recolección,
la definición de la muestra, el procesamiento y los análisis
deberán desarrollarse y documentarse progresivamente.

No se presentan resultados empíricos mientras no estén respaldados
por datos recolectados y analizados.

## Criterios de trabajo

- No fabricar datos, fuentes, resultados ni conclusiones.
- Registrar el origen, la fecha y las transformaciones de los datos.
- Distinguir datos observados, estimaciones y percepciones.
- Diferenciar la oferta observada del mercado completo.
- Mantener explícitas las decisiones metodológicas pendientes.
- Priorizar análisis transparentes, interpretables y reproducibles.

## Trazabilidad

El historial de Git registra los cambios del proyecto.
El diario de trabajo se encuentra en `journal/JOURNAL.md`.

Repositorio:
https://github.com/darielcpuerto/Proyecto-ICD-Dariel-Cabrera-Puerto
