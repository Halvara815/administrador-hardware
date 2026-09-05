# Seguridad y modelo de amenazas

## Alcance y activos

- Integridad del equipo analizado.
- Privacidad de nombres del equipo, direcciones IP/MAC e identificadores de dispositivos.
- Integridad del reporte y disponibilidad de la interfaz.

## Fronteras de confianza

- La UI y sus servicios son código de la aplicación.
- PowerShell, CIM, PnP y sus salidas pertenecen al límite del sistema operativo.
- La ruta de exportación y el archivo elegido pertenecen al usuario.

## Amenazas y controles

| Riesgo | Control | Evidencia de prueba |
|---|---|---|
| Inyección de comandos | Consultas fijas; `subprocess` sin `shell=True`; sin entrada del usuario | Test de rechazo de comando desconocido |
| Proceso colgado | Timeout y finalización controlada | Test de timeout |
| Salida enorme o malformada | `MAX_OUTPUT_CHARS` y validación JSON en `parse_json_rows` | `MalformedOutputTests` en `test_powershell.py` y `MalformedOutputScanTests` |
| Confundir falta de permiso con hardware sano | Estado `ERROR` y mensaje explícito | Test de permiso denegado |
| Exponer información al exportar | Guardado explícito y aviso de contenido | Prueba de cancelación y revisión manual |
| Dependencia comprometida | Mínimas dependencias, revisión y archivo de bloqueo antes de entrega | Escaneo de dependencias |

## Principio operativo

La herramienta es diagnóstica y de solo lectura. No instala, actualiza, deshabilita
ni repara controladores o dispositivos. La elevación de privilegios no será
automática; si una consulta no está autorizada se informa la limitación.

