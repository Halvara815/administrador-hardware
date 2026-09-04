# Observabilidad y calidad

## Señales útiles

- Inicio y fin de cada análisis.
- Duración y resultado de cada recolector.
- Timeout, permiso insuficiente y error de parseo.
- Resultado y ruta final de exportación, sin registrar el contenido completo.

## Objetivos verificables

- La UI permanece interactiva durante el 100 % de los análisis de aceptación.
- Un fallo parcial aparece en pantalla y no elimina los resultados exitosos.
- Cada fila problemática tiene evidencia y explicación.
- Ningún comando fuera de la lista permitida puede ejecutarse desde la aplicación.

## Logging

Formato estructurado y rotación local pequeña. Se omiten o reducen identificadores,
IPs, MACs y salida cruda cuando no sean necesarios para diagnosticar la propia app.

