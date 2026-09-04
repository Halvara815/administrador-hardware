# Datos y contratos

## Persistencia

No existe base de datos, repositorio persistente ni API. El estado de un análisis
vive en memoria y desaparece al cerrar la aplicación. Sólo un reporte solicitado
explícitamente se escribe en el sistema de archivos.

## Modelo principal

- `ComponentKind`: categoría estable del componente.
- `EvidenceRecord`: fuente, consulta mostrable, salida, fecha y éxito.
- `ComponentResult`: hechos normalizados, estado, problema y evidencias.
- `DiagnosticReport`: conjunto inmutable de resultados y conclusión.

## Invariantes

- Toda advertencia o problema debe incluir evidencia.
- Una conclusión no puede afirmar una causa que no aparezca en los resultados.
- `ERROR` significa que la medición falló; no significa que el dispositivo falló.
- Fechas internas en UTC; la UI puede mostrarlas en hora local.
- La evidencia se conserva como texto de solo lectura y se limita antes de mostrarla.

## Contrato de exportación

El reporte incluirá: versión de la app, fecha, resumen del sistema, matriz,
evidencias relevantes, interpretación, conclusión y limitaciones de la ejecución.
El nombre y ubicación los elige el usuario. No se sobrescribe sin confirmación.

