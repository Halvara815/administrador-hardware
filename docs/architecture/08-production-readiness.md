# Revisión de preparación para entrega

- Fecha: 2026-09-04
- Owner: equipo del proyecto
- Resultado: **LISTO PARA ENTREGA ACADÉMICA EN WINDOWS**
- Alcance: aplicación local, de un usuario, sin base de datos ni servicios externos.

| Área | Gate | Estado | Evidencia / razón |
|---|---|---|---|
| Producto | Doce opciones del enunciado | PASS | `NAV_ITEMS`, recolectores y trazabilidad |
| Producto | Matriz, conclusión y evidencia técnica | PASS | Smoke test y capturas a dos resoluciones |
| Producto | Caso final del ingeniero | PASS | Test CPU 95 %, RAM 92 %, USB y GPU con error |
| Reliability | Fallo parcial no cancela el análisis | PASS | `test_scan_service.py` |
| Reliability | UI no bloqueada | PASS | Recolectores en `ThreadPoolExecutor` y captura tras flujo real |
| Capacidad | Tiempo de análisis razonable | PASS | 5.49 s desde Python y 8.11 s desde `.exe` final en esta máquina |
| Seguridad | Sin comandos libres ni `shell=True` | PASS | Enum cerrado y `test_powershell.py` |
| Seguridad | Dependencias conocidas | PASS | `pip-audit -r requirements.lock`: sin vulnerabilidades conocidas |
| Privacidad | Retención y exportación | PASS | Estado en memoria; reporte explícito; manual con aviso de datos técnicos |
| Identidad | Auth, sesiones y multiusuario | N/A | Aplicación local sin cuentas ni servidor |
| Datos | DB, migraciones, backup y restore | N/A | No existe persistencia interna; ADR-001 |
| Entrega | Build reproducible | PASS | `requirements.lock`, `build.cmd` y spec de PyInstaller |
| Entrega | Ejecutable sin consola | PASS | `console=False`; smoke test del artefacto con código 0 |
| Entrega | Reporte desde artefacto | PASS | `reports/diagnostico-final-verificado.html`, 99 030 bytes |
| Entrega | Paquete final | PASS | ZIP versionado con `.exe`, recursos y `LEEME.txt` |
| Observabilidad | Logs de fallos y duración | PASS | Log rotativo en `%LOCALAPPDATA%\AdministradorHardware\logs` |
| Operación | Dashboards, on-call y alertas | N/A | No existe servicio ni operación continua |
| Costos | Infraestructura y terceros | N/A | Ejecución local sin nube ni API externa |
| Distribución | Firma de código | N/A | No fue requisito académico; sería necesaria para distribución pública |
| Compatibilidad | Segunda máquina Windows limpia | NO VERIFICADO | Recomendado si se evaluará en hardware distinto |

## Evidencia final

- `pytest`: 12 pruebas pasadas, incluida integración real de Windows.
- `ruff`: sin hallazgos.
- `mypy --strict`: sin hallazgos en 21 archivos fuente.
- `pip-audit`: sin vulnerabilidades conocidas en el lockfile.
- PyInstaller: build completado; advertencias limitadas a módulos opcionales o de otras plataformas.
- Ejecutable: smoke y análisis completo con código de salida 0.
- Reporte HTML: renderizado visualmente sin desbordes en la primera página.
- UI: verificada visualmente a 1580×900 y 1280×760.

## Riesgos residuales

- Windows puede mostrar SmartScreen porque el ejecutable académico no está firmado.
- Los datos disponibles dependen de permisos, drivers y proveedores del equipo.
- Un diagnóstico por software no sustituye inspección física si el problema persiste.
