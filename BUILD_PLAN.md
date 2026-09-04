# Plan de construcción

## Estado

- Alcance: producto académico local para Windows.
- Persistencia: sin base de datos; reportes sólo por exportación explícita.
- Arquitectura: monolito modular en un único proceso.
- Estado del plan: completado y verificado el 2026-09-04.

## Slice 1: ventana y diagnóstico de CPU/RAM

Estado: **COMPLETADO**.

- Resultado observable: abrir una ventana, pulsar **Analizar equipo** y ver CPU,
  RAM, matriz, conclusión y evidencia técnica.
- Módulos: `ui`, `services`, `collectors/psutil_collector.py`, `diagnostics`.
- Riesgo atacado: mantener la interfaz fluida durante una medición bloqueante.
- Pruebas: reglas de umbral, manejo de error y prueba manual de no congelamiento.
- Fix-forward: conservar la aplicación abierta y mostrar el componente como error.
- Aceptación: el análisis termina, actualiza la pantalla y no usa la terminal externa.

## Slice 2: sistema, discos, red y E/S

Estado: **COMPLETADO**.

- Resultado observable: las opciones 1 a 5 y 11 muestran datos reales y evidencia.
- Módulos: recolectores de `platform` y `psutil`.
- Riesgo atacado: unidades ausentes, contadores no disponibles y divisiones por cero.
- Pruebas: formateo de bytes, interfaces sin IP y particiones inaccesibles.
- Aceptación: un fallo parcial no cancela el resto del análisis.

## Slice 3: USB, PCI/PCIe, controladores, problemas y GPU

Estado: **COMPLETADO**.

- Resultado observable: las opciones 6 a 10 muestran tablas obtenidas de Windows.
- Módulos: `infrastructure/powershell.py` y recolector PnP/CIM.
- Riesgo atacado: codificación, permisos, timeouts y cambios de formato de PowerShell.
- Pruebas: respuestas JSON simuladas, timeout y comando no permitido.
- Seguridad: lista cerrada de consultas; nunca concatenar entrada del usuario.
- Aceptación: se conservan salida técnica, estado y mensaje comprensible.

## Slice 4: diagnóstico integrado

Estado: **COMPLETADO**.

- Resultado observable: matriz completa y causa probable basada en evidencia.
- Módulos: `diagnostics/engine.py` y reglas por componente.
- Pruebas: caso del enunciado y combinaciones de CPU/RAM/USB/GPU.
- Aceptación: cada conclusión referencia al menos un hallazgo medido.

## Slice 5: reportes y empaquetado

Estado: **COMPLETADO**.

- Resultado observable: exportar un reporte y ejecutar la aplicación sin consola.
- Módulos: `reports`, recursos visuales y configuración de PyInstaller.
- Pruebas: caracteres españoles, ruta cancelada, archivo existente y smoke test del `.exe`.
- Rollback: distribuir el último paquete verificado; los reportes del usuario no se modifican.
- Aceptación: el reporte contiene fecha, evidencia, matriz, interpretación y conclusión.

## Slice 6: hardening y entrega

Estado: **COMPLETADO** para la máquina Windows verificada.

- Formato, lint, tipos, pruebas y revisión de dependencias.
- Validación en Windows con usuario estándar y, por separado, permisos elevados.
- Verificación en resolución 1366×768 y escalado de pantalla de 100–150 %.
- Manual breve de uso y limitaciones conocidas.
