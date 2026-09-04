# Requisitos no funcionales

## Objetivos iniciales

- La ventana debe permanecer interactiva durante todo el análisis.
- Cada consulta al sistema tendrá timeout; objetivo inicial: 15 segundos por consulta.
- Un fallo de un componente no debe impedir resultados de los demás.
- La aplicación soportará un solo análisis activo para evitar duplicar carga.
- La evidencia visible se limitará a un tamaño razonable para proteger la memoria y UI.
- Resolución mínima objetivo: 1366×768 con navegación desplazable.
- Escalado visual objetivo: 100 %, 125 % y 150 % en Windows.

## Volumen estimado

- Decenas o cientos de dispositivos locales, no millones de registros.
- Un reporte por ejecución cuando el usuario lo solicite.
- Sin concurrencia de red ni almacenamiento persistente.

## Recuperación

- Si una consulta falla, su resultado queda como `ERROR` con evidencia del fallo.
- Si la exportación falla, el diagnóstico permanece visible y se permite reintentar.
- RPO/RTO y backups de servidor no aplican porque no existe servicio ni base de datos.

