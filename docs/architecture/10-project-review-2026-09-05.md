# Revisión de implementación y cobertura

Fecha: 2026-09-06. Alcance: código y documentación locales tras los cambios
recientes. Revisión estática más puertas automatizadas; no certifica sensores,
dispositivos físicos, rendimiento real ni un equipo Windows limpio distinto.

## Evidencia verificada

- Arquitectura: monolito local Python con CustomTkinter, `psutil`, PowerShell/CIM
  y comandos nativos con catálogo cerrado. No hay DB, API remota, cuentas ni IA
  implementada. La UI conserva 15 apartados más Salir y evidencia de solo lectura.
- Implementación: recolectores para sistema/CPU/RAM/red/E/S, almacenamiento,
  PnP USB/PCI/dispositivos con problema, GPU/monitor y drivers; servicios de
  escaneo, conectividad y monitorización; reportes HTML/JSON/TXT.
- Calidad ejecutada en este entorno (Fases F1, F2, F3 y F4 completadas con verificación humana pendiente): `pytest --capture=sys -q` = **271 passed, 29 subtests passed** (total: 271 pruebas evaluadas);
  `ruff check .` = **All checks passed!**; `mypy src` = **Success: no issues found in 37 source files**;
  build PyInstaller y smoke test del ejecutable = **PASS** (`{"has_report": false, "matrix_rows": 11, "navigation_items": 16, "selected": "system"}`).
  - Binario: `dist/AdministradorDeHardware/AdministradorDeHardware.exe`
  - SHA-256 (EXE): `523ee0dee5a77a30e131526a5247632797aa8dedc1ccf12ae2178a3af08ab011`
  - Fecha de compilación (EXE): `2026-09-05T20:57:15-06:00`
  - Paquete de entrega: `release/AdministradorDeHardware-v0.1.0-windows-x64.zip`
  - SHA-256 (ZIP): `57db1f6d189b54f0633a89f91f16c01294c69d6722ea8447e074fd41d3400730`
  - Intérprete de empaquetado: CPython 3.12.14 Windows x86_64 con Tcl/Tk 8.6.12 completo (`tcl86t.dll`, `tk86t.dll`, `_tkinter.pyd`).
  - Nota de auditoría: Los builds previos generados bajo Python 3.14 quedan **INVALIDADOS** debido a que carecían de binarios Tcl/Tk funcionales (`ModuleNotFoundError: No module named 'tkinter'`). El nuevo build ha sido validado mediante doble `--smoke-test` obligatorio (apertura y cierre de ventana principal, ventana hija de sensores térmicos y ventana hija de eventos de Windows) tanto en el EXE de `dist` como en el EXE extraído del ZIP.
- Entrega observada: existe EXE y ZIP de release; CI Windows y `pip-audit` están
  configurados. No se ejecutó en esta revisión el pipeline remoto, el
  protocolo PR-01…PR-18 ni la prueba del EXE en una segunda máquina.

## Estado contra el alcance implementado

| Área | Estado | Evidencia o límite |
|---|---|---|
| Interfaz, matriz, consola y 15 apartados | COMPLETADA | `ui/main_window.py`, contratos UI y pruebas |
| CPU/RAM de uso instantáneo, reglas y gráficos | COMPLETADA | `core.py`, `rules.py`, gráficos y tests |
| Discos: espacio, medio/bus, volúmenes y USB sin volumen | COMPLETADA | `storage.py`, consultas Get-Disk/Get-PhysicalDisk/Get-Volume |
| Salud profunda de almacenamiento (SMART/Reliability) | COMPLETADA | `storage.py`, `powershell.py`: contadores de fiabilidad, degradación por permisos, sin falsos positivos |
| Batería, energía, plan y reporte bajo demanda | COMPLETADA | `core.py`, `commands.py`, `main_window.py`: powercfg con askokcancel, asksaveasfilename y ejecución asíncrona |
| Firmware, Placa base, TPM y Secure Boot | COMPLETADA | `core.py`, `powershell.py`: Win32_BaseBoard, Win32_BIOS, Get-Tpm, Confirm-SecureBootUEFI |
| Módulos físicos de memoria RAM (SMBIOS) | COMPLETADA | `core.py`, `powershell.py`: desglose por ranura, DMTF SMBIOS (DDR4/DDR5/etc.), velocidad configurada |
| Periféricos clave (PnP extendido) | COMPLETADA | `core.py`, `powershell.py`: Bluetooth, cámara, multimedia, entrada; fallos aislados sin condenar el subsistema |
| Telemetría térmica, sensores y throttling (Fase F3) | NEEDS_USER_VERIFICATION | `thermal.py`, recolectores y ventana hija «Temperaturas y sensores»: lecturas visibles de WMI ACPI, SMART storage y NVIDIA SMI con banderas oficiales de throttling térmico |
| Red básica y escalonada | COMPLETADA | adaptador, IP, gateway, IP externa y DNS; timeout/presupuesto |
| Red profunda y eventos críticos de Windows (Fase F4) | NEEDS_USER_VERIFICATION | `connectivity_service.py`, `windows_events.py`, `drivers.py` y ventana hija «Eventos de Windows»: latencia/pérdida hacia gateway/externo, ICMP filtrado, estadísticas de interfaz con psutil, Wi-Fi con netsh, Get-WinEvent (ventana 7 días allowlisted, try/catch sin SilentlyContinue, manejo estricto de permisos como NOT_SUPPORTED y fallos como ERROR), regla KP41 no causal a lo sumo WARNING, sanitización de privacidad (500 chars, depuración IPs/rutas/seriales/usuarios), correlación de drivers exclusivamente por DeviceID/InstanceId normalizado contra PROBLEM_DEVICES |
| USB, PCI/PCIe y dispositivos con problema | COMPLETADA | IDs/códigos PnP, casos C2/C3 y tests |
| GPU/monitor y drivers de inventario | COMPLETADA | WMI, versión de driver como inventario; no asesor de actualización |
| Recomendaciones guiadas C1–C5 | COMPLETADA | reglas deterministas; no realiza cambios automáticamente |
| Monitorización pasiva de E/S | COMPLETADA | 1 s, buffer 300 y parada explícita |
| Exportación y privacidad base | COMPLETADA | HTML, JSON y TXT; identidad opcional en JSON/TXT |
| Empaquetado y documentación base | COMPLETADA CON VERIFICACIÓN HUMANA PENDIENTE | falta equipo limpio y protocolo físico |

El estado COMPLETADA describe la capacidad delimitada en esta tabla; no significa
«diagnóstico físico completo» ni sustituye una prueba real de hardware.

## Alcance del ingeniero que sigue pendiente

| Requisito o mejora | Estado y destino |
|---|---|
| Validación física de sensores en hardware Intel/AMD/NVIDIA/AMD GPU heterogéneo | Pendiente: validación humana en laboratorio / NEEDS_USER_VERIFICATION |
| Verificación de eventos de Windows y red en equipos reales | Pendiente: validación humana en laboratorio / NEEDS_USER_VERIFICATION |
| Prueba corta de disco / autoprueba SMART activa | Pendiente: Fase 6 |
| Asesor de compatibilidad de ampliación RAM con placa | Pendiente: Asesor E2 |
| Diagnóstico de memoria Windows y prueba de RAM segura | Pendiente: Fase 6, con consentimiento/reinicio explícito |
| Motor multimuestreo, confianza y correlación de señales | Pendiente: Fase 5 (ESTRICTAMENTE NO INICIADA) |
| Actualización segura OEM de drivers y asesor P15 | Pendiente: Asesorías comerciales |
| PDF y modo técnico/básico | PDF pendiente Fase 7 comercial; HTML/JSON/TXT completados |
| MSI/MSIX, firma, actualización, licencia/activación y matriz comercial | Pendiente: Fases 8–9 comerciales |

## Investigación y asesorías previamente aprobadas

Todos los requisitos P13–P28 y slices E1–E8 están conservados en
[09-diagnostic-advisor.md](09-diagnostic-advisor.md) y
[PRODUCT_REQUIREMENTS.md](../PRODUCT_REQUIREMENTS.md). Ninguno se halló
implementado, por lo que permanecen **NO INICIADOS**: IA opcional, drivers OEM,
RAM ampliable, comparación de reportes, copia depurada, compatibilidad y compra
de GPU, rendimiento por aplicación, refresco, SSD y priorizador de actualizaciones.

## Inconclusos o discrepancias encontrados

1. pytest ejecuta 271 passed y 29 subtests passed (total: 271 pruebas evaluadas). La persistencia de caché presenta PytestCacheWarning / WinError 183 en este entorno cuando no se especifica directorio alterno. Se registra como NOT_RUN_ENV_LIMITATION y no afecta los resultados funcionales.
2. Los empaquetados anteriores generados bajo Python 3.14 quedan marcados como INVALIDADOS debido a la ausencia de Tcl/Tk. El nuevo empaquetado bajo CPython 3.12.14 contiene la distribución completa de Tcl/Tk y supera el smoke test tanto en `dist` como en el ZIP.
3. `README.md` aún describía exportación HTML como si fuese la única; se corrige
   en esta actualización para reflejar JSON/TXT ya implementados.
4. La trazabilidad histórica de 2026-09-04 conserva conteos anteriores (12 tests,
   21 archivos). Es evidencia histórica válida, no el estado presente. El resultado
   actual de esta revisión es el indicado arriba.
5. No hay evidencia nueva de que el EXE de hoy se haya probado en equipo limpio,
   ni de PR-01…PR-18. Son `NEEDS_USER_VERIFICATION`, no fallos de código.

## Orden recomendado al retomar

1. Con la telemetría térmica implementada en F3 y el subsistema de red/eventos críticos implementado en F4 (ambas marcadas `NEEDS_USER_VERIFICATION` a la espera de pruebas físicas en laboratorio y entornos reales de Windows), el siguiente trabajo canónico es la **Fase 5 comercial (motor de diagnóstico multimuestreo y correlación de señales)**, la cual permanece **ESTRICTAMENTE NO INICIADA**.
2. Posteriormente avanzar secuencialmente a Fase 5 (motor multimuestreo y correlación de señales) y Fase 6 (pruebas de estrés controladas y diagnósticos de memoria seguros).
3. E1–E8 e I1–I5 después de tener mediciones y fuentes verificables; no sustituir
   reglas por IA ni integrar una clave del vendedor dentro del EXE.

No se utilizó ni se requiere base de datos para lo completado ni para estas fases
locales. Una futura gestión de cuentas/cuotas con clave comercial sí requerirá una
decisión separada de persistencia y seguridad.
