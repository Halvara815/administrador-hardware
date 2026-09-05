# Diseño del sistema

> Este documento describe la base v0.1.0. La estructura objetivo, contratos,
> límites, menú y fases del alcance del producto están en
> [BUILD_PLAN.md](../../BUILD_PLAN.md). Fase 1 completada según el plan; resto pendiente.
> Se conservará el monolito modular y la ausencia de base de datos.

## Extensión planificada del asesor

[09-diagnostic-advisor.md](09-diagnostic-advisor.md) define RAM ampliable,
compatibilidad GPU, rendimiento contextual, guía por síntoma y comparación de reportes.
Todos sus slices E1–E8 están pendientes, incluidos asesor SSD y prioridad de ampliación.
Servicios coordinan inventario y fuentes;
reglas puras validan evidencia; IA opcional explica; UI conserva la maqueta.
La captura de rendimiento es un adaptador opcional, no un servicio obligatorio.
No se incorporan DB, reparación automática ni nuevas dependencias en esta revisión.

## Decisión

Monolito modular de escritorio en un solo proceso. La interfaz desconoce cómo se
obtienen los datos; recibe modelos normalizados del servicio de análisis.

## Componentes

```text
┌──────────────────────── Interfaz de escritorio ────────────────────────┐
│ navegación | tarjetas | matriz | conclusión | evidencia sólo lectura │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ eventos/modelos
┌──────────────────────────────▼─────────────────────────────────────────┐
│ ScanService: orquestación, progreso, cancelación futura y aislamiento │
└───────────────┬───────────────────────────────┬────────────────────────┘
                │                               │
┌───────────────▼──────────────┐   ┌────────────▼────────────────────────┐
│ Collectors                   │   │ DiagnosticEngine                    │
│ platform/psutil/PnP/CIM      │   │ reglas, estados y conclusión       │
└───────────────┬──────────────┘   └─────────────────────────────────────┘
                │
┌───────────────▼────────────────────────────────────────────────────────┐
│ Infrastructure: PowerShell seguro, reloj, filesystem de exportación   │
└────────────────────────────────────────────────────────────────────────┘
```

## Dependencias permitidas

- `ui` → `services` y `domain`.
- `services` → `collectors`, `diagnostics` y `domain`.
- `collectors` → `infrastructure` y `domain`.
- `diagnostics` → únicamente `domain`.
- `infrastructure` → biblioteca estándar y sistema operativo.

`domain` no importa módulos de UI, PowerShell ni librerías de presentación.

## Flujo de análisis

1. La UI desactiva el botón y crea un trabajo en segundo plano.
2. `ScanService` ejecuta cada recolector y publica progreso.
3. Cada recolector devuelve datos normalizados y evidencia técnica.
4. El motor aplica reglas deterministas y produce la matriz/conclusión.
5. La UI actualiza todo desde su hilo principal y habilita la exportación.

## Manejo de fallos

- Timeout, permiso insuficiente y salida inválida son estados explícitos.
- No se interpreta “dato ausente” como “hardware sano”.
- Los resultados exitosos se conservan aunque otro recolector falle.
