# Trazabilidad de requisitos

> Evidencia histórica de la base funcional. Consultar
> [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md) para las ampliaciones pendientes.

Fecha de verificación: 2026-09-04

| # | Requisito | Implementación | Evidencia |
|---:|---|---|---|
| 1 | Información del sistema | `SystemCollector` | Windows, fabricante, modelo, arquitectura y uptime obtenidos en el análisis real |
| 2 | CPU: modelo, núcleos y uso | `CpuCollector` | Contrato validado en `test_windows_integration.py` |
| 3 | RAM: total, disponible y uso | `MemoryCollector` | Contrato validado y visible en `docs/ui-live.png` |
| 4 | Discos: unidad, bus, capacidad, estado y uso | `DiskCollector` + `Get-Disk` | Campos reales validados en análisis y reporte |
| 5 | Red: adaptador, MAC, IPv4, estado y velocidad | `NetworkCollector` | Datos normalizados desde `psutil` |
| 6 | USB: dispositivo, estado e ID | `PnpCollector(USB_PRESENT)` | 10 dispositivos reales detectados durante la verificación |
| 7 | PCI/PCIe: dispositivo, clase, estado e ID | `PnpCollector(PCI_PRESENT)` | 16 dispositivos reales detectados durante la verificación |
| 8 | Controladores: nombre, tipo y estado | `DriverCollector` | 149 controladores reales consultados; campos normalizados en español |
| 9 | Dispositivos con problemas | `PnpCollector(PROBLEM_DEVICES)` | Consulta de dispositivos presentes con filtrado de estado |
| 10 | Monitor y GPU | `MonitorGpuCollector` | Una GPU y un monitor detectados en la prueba real |
| 11 | Monitorizar E/S | `IoCollector` | Tasas de lectura, escritura, envío y recepción calculadas en un intervalo real |
| 12 | Generar reporte | Vista previa en «14. Exportar diagnóstico» + `export_html` y selector de archivo | `reports/diagnostico-final-verificado.html` generado por el `.exe` |
| — | Matriz diagnóstica | `HardwareAdminApp.matrix` | Captura `docs/ui-live.png` |
| — | Evidencia tipo terminal | Consola visual de sólo lectura | Captura y smoke test de UI |
| — | Causa probable justificada | `RuleBasedDiagnosticEngine` | Prueba del caso final CPU/RAM/USB/GPU |
| — | Ejecutable sin terminal | PyInstaller `console=False` | Smoke test del `.exe` con código de salida 0 |
| — | Sin base de datos | `DiagnosticReport` sólo en memoria | Búsqueda de SQLite/SQLAlchemy/SQL sin coincidencias |

## Evidencia automatizada

- 12 pruebas pasaron, incluida una integración con hardware real de Windows.
- Ruff: sin hallazgos.
- Mypy estricto: sin hallazgos en 21 archivos fuente.
- Auditoría de dependencias: ninguna vulnerabilidad conocida.
- Smoke test del ejecutable: código 0.
- Análisis y reporte desde el ejecutable final: código 0; 8.11 s observados en esta máquina.
