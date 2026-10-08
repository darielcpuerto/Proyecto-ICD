# Reglas de calidad y trazabilidad del dato

## Regla general

No fabricar datos, fuentes, resultados ni conclusiones.

## Trazabilidad

Para cada conjunto de datos registrar, cuando sea posible:

- origen/fuente;
- fecha;
- método de obtención;
- variables;
- unidades;
- transformaciones;
- filtros;
- supuestos;
- problemas de calidad.

Conservar los datos originales siempre que sea legal y técnicamente posible.

## Distinciones obligatorias

### Población vs. muestra

No tratar una muestra como si fuera automáticamente representativa de toda la población.

### Dato observado vs. percepción

Una respuesta declarada por una persona representa una percepción o declaración, salvo que el diseño permita tratarla como medición.

### Estimación vs. dato observado

Las capacidades o requerimientos calculados a partir de usos y supuestos deben identificarse como estimaciones.

### Correlación vs. causalidad

Una asociación observada no demuestra una relación causal.

### Oferta observada vs. mercado completo

La oferta encontrada mediante Internet representa oferta observada, no necesariamente todo el mercado.

### Precio anunciado vs. precio de transacción

Un precio publicado no debe presentarse como precio efectivamente pagado.

### Disponibilidad anunciada vs. disponibilidad verificada

La presencia de un producto en un anuncio no demuestra que esté disponible físicamente o que pueda adquirirse en las condiciones anunciadas.

### Ausencia de datos vs. ausencia del fenómeno

Que no se encuentre información no demuestra que el fenómeno no exista.

## Reproducibilidad

Todo procesamiento importante debe poder reconstruirse, en la medida razonable, mediante:

**datos → código → transformaciones → resultado.**

Evitar pasos manuales no documentados cuando puedan automatizarse razonablemente.

## Calidad de la recolección

Los instrumentos y procedimientos deben permitir identificar el origen y momento de cada observación y conservar la información necesaria para revisar posteriormente cómo fue obtenida.
