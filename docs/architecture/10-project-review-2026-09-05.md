# Revisión de implementación y cobertura

Fecha: 2026-09-05. Alcance: código y documentación locales tras los cambios
recientes. Revisión estática más puertas automatizadas; no certifica sensores,
dispositivos físicos, rendimiento real ni un equipo Windows limpio distinto.

## Evidencia verificada

- Arquitectura: monolito local Python con CustomTkinter, `psutil`, PowerShell/CIM
  y comandos nativos con catálogo cerrado. No hay DB, API remota, cuentas ni IA
  implementada. La UI conserva 15 apartados más Salir y evidencia de solo lectura.
- Implementación: recolectores para sistema/CPU/RAM/red/E/S, almacenamiento,
  PnP USB/PCI/dispositivos con problema, GPU/monitor y drivers; servicios de
  escaneo, conectividad y monitorización; reportes HTML/JSON/TXT.
- Calidad ejecutada en este entorno (Fase F1 y F2 completadas): `pytest -q` = **199 passed, 8 skipped, 29 subtests passed**;
  `ruff check .` = **All checks passed!**; `mypy src` = **Success: no issues found in 35 source files**;
  build PyInstaller y smoke test del ejecutable = **PASS** (`{"has_report": false, "matrix_rows": 11, "navigation_items": 16, "selected": "system"}`).
  - Binario: `dist/AdministradorDeHardware/AdministradorDeHardware.exe`
  - SHA-256 (EXE): `f358360fa8c0ab593d75e328980766317d5ccea4776ffc289bf02937c38eb1da`
  - Fecha de compilación (EXE): `2026-09-05T17:29:07-06:00`
  - Paquete de entrega: `release/AdministradorDeHardware-v0.1.0-windows-x64.zip`
  - SHA-256 (ZIP): `97cb8f9dcd1567ab85183bc184c8dedf81785058346c7157343a544db5e31e7d`
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
| Red básica y escalonada | COMPLETADA | adaptador, IP, gateway, IP externa y DNS; timeout/presupuesto |
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
| Temperaturas CPU/GPU/disco, ventiladores, voltajes, frecuencias y throttling | Pendiente: hoja comercial Fase 3 (NO INICIADA) |
| Prueba corta de disco / autoprueba SMART activa | Pendiente: Fase 6 |
| Asesor de compatibilidad de ampliación RAM con placa | Pendiente: Asesor E2 |
| Diagnóstico de memoria Windows y prueba de RAM segura | Pendiente: Fase 6, con consentimiento/reinicio explícito |
| Latencia/pérdida, Wi-Fi y descartes de red | Pendiente: Fase 4; gateway/DNS/Internet ya completados |
| Eventos WHEA/disco/drivers/reinicios/BSOD | Pendiente: Fase 4 |
| Drivers faltantes/deshabilitados/antiguos y actualización segura OEM | Parcial: hoy se muestran versión/fecha/firma/IDs y PnP reporta códigos; asesor P15 pendiente |
| Motor multimuestreo, confianza y correlación de señales | Pendiente: Fase 5; monitorización E/S no satisface este motor |
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

1. La advertencia de `.pytest_cache` fue corregida mediante la configuración explícita
   de `cache_dir = ".cache/pytest"` en `pyproject.toml`, eliminando `PytestCacheWarning` / `WinError 183`.
2. `README.md` aún describía exportación HTML como si fuese la única; se corrige
   en esta actualización para reflejar JSON/TXT ya implementados.
3. La trazabilidad histórica de 2026-09-04 conserva conteos anteriores (12 tests,
   21 archivos). Es evidencia histórica válida, no el estado presente. El resultado
   actual de esta revisión es el indicado arriba.
4. No hay evidencia nueva de que el EXE de hoy se haya probado en equipo limpio,
   ni de PR-01…PR-18. Son `NEEDS_USER_VERIFICATION`, no fallos de código.

## Orden recomendado al retomar

1. El siguiente trabajo canónico debe ser la **Fase 3 comercial (sensores y comportamiento térmico)**,
   la cual permanece **ESTRICTAMENTE NO INICIADA**.
2. Posteriormente avanzar secuencialmente a Fase 4 (red avanzada y eventos del sistema) y
   Fase 5 (motor multimuestreo y correlación de señales).
3. E1–E8 e I1–I5 después de tener mediciones y fuentes verificables; no sustituir
   reglas por IA ni integrar una clave del vendedor dentro del EXE.

No se utilizó ni se requiere base de datos para lo completado ni para estas fases
locales. Una futura gestión de cuentas/cuotas con clave comercial sí requerirá una
decisión separada de persistencia y seguridad.
