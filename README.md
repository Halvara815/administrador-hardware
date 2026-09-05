# Administrador de Hardware

> Nueva etapa planificada: **Hardware Diagnostic & Repair Assistant**.
> El [plan vigente](BUILD_PLAN.md) y la
> [trazabilidad del nuevo enunciado](docs/ASSIGNMENT_TRACEABILITY.md) describen
> los cambios pendientes. Esta reestructuración es documental; las funciones
> enumeradas debajo corresponden a la versión actual. Se mantiene **sin DB**.
> La [hoja de ruta comercial](docs/COMMERCIAL_ROADMAP.md) queda diferida.

La [investigación de IA y compatibilidad](docs/RESEARCH_AI_HARDWARE.md) reúne
repositorios, fuentes y el diseño futuro de recomendaciones de controladores/RAM.
Esta función todavía no está implementada.

Aplicación de escritorio para Windows que recopila información real del equipo,
presenta evidencia técnica similar a una terminal y genera un diagnóstico
justificado. El proyecto no utiliza base de datos ni servicios externos.

![Interfaz ejecutada](docs/ui-live.png)

## Alcance funcional

1. Información del sistema
2. CPU
3. Memoria
4. Discos
5. Red
6. USB
7. PCI/PCIe
8. Controladores
9. Dispositivos con problemas
10. Monitor y GPU
11. Monitorización de E/S
12. Generación de reporte

## Uso de la aplicación terminada

El ejecutable se encuentra en:

```text
dist/AdministradorDeHardware/AdministradorDeHardware.exe
```

La carpeta completa `AdministradorDeHardware` debe conservarse junta. Abra el
`.exe`, pulse **ANALIZAR EQUIPO**, seleccione cualquier componente y use la opción
12 para exportar el reporte HTML.

También se genera un ZIP listo para copiar o entregar en `release/`.

## Desarrollo y reconstrucción

En Windows, ejecute `build.cmd`. El proceso crea el entorno virtual cuando hace
falta, instala las versiones de `requirements.lock`, ejecuta pruebas, lint y
tipado, y sólo entonces construye el `.exe`.

Para abrir la versión de desarrollo sin consola puede usar `run.cmd`.

## Arquitectura

Se utiliza un monolito modular con cuatro responsabilidades separadas:

- `collectors`: obtiene evidencia desde `psutil` y consultas permitidas de Windows.
- `diagnostics`: convierte métricas y estados en hallazgos explicables.
- `services`: coordina un análisis completo sin bloquear la interfaz.
- `ui`: presenta navegación, matriz, conclusión y evidencia técnica de solo lectura.

Los modelos compartidos viven en `domain`. La interacción con PowerShell y el
sistema operativo queda aislada en `infrastructure`.

Consulta [BUILD_PLAN.md](BUILD_PLAN.md) y [docs/architecture](docs/architecture)
antes de comenzar la implementación.

## Seguridad y datos

- Las consultas PowerShell pertenecen a una lista cerrada.
- No se aceptan comandos escritos por el usuario.
- Los recolectores son de sólo lectura y tienen timeout.
- Un fallo parcial no elimina los resultados obtenidos.
- El estado vive en memoria; sólo se escribe un reporte por petición explícita.
- Los logs no guardan la evidencia cruda completa.

## Verificación

El pipeline local incluye `pytest`, `ruff`, `mypy`, smoke test de interfaz,
diagnóstico real, render del reporte y smoke test del artefacto PyInstaller.
Consulta [la revisión de entrega](docs/architecture/08-production-readiness.md)
para ver el estado de cada gate.
