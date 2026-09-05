# Fase 4A — Monitorización en vivo y gráfico de E/S

Fecha: 2026-09-05. Estado: diseño aprobado, pendiente de implementar.
Rebanada 1 de 4 de la Fase 4. Las rebanadas 4B (gráficos estáticos por
apartado), 4C (recomendaciones) y 4D (menú de 15 opciones y Salir) tienen
su propio ciclo y no se abordan aquí.

## Problema

El apartado de E/S entrega hoy una muestra única de 0,5 s mediante
`IoCollector`. El plan exige muestreo periódico acotado, parada explícita y
datos con fecha, además de un gráfico de series de tiempo en vivo. No existe
ningún servicio de monitorización ni ningún widget de gráfico en el proyecto.

## Alcance

Entra: `services/monitoring_service.py`, `ui/charts.py`, el cableado del
apartado de E/S existente y sus pruebas.

No entra: la reestructuración del menú a 15 opciones (4D), los gráficos de
CPU/RAM/Discos/Red (4B), las recomendaciones estructuradas (4C) y la
exportación de la serie a JSON/TXT (Fase 5). No se altera ningún contrato de
`domain`, ningún recolector ni ninguna regla de `diagnostics`. `IoCollector`
y su fila en la matriz permanecen intactos.

## Decisiones y fundamento

**El servicio es dueño de la serie.** El hilo de muestreo escribe en un
`deque` acotado dentro del servicio y la UI pide instantáneas. Alternativa
descartada: una cola al estilo de `scan_service`, que dejaría el buffer en la
UI y volvería la serie no exportable ni comprobable sin abrir ventana; la
especificación del plan dice explícitamente «las series de
`monitoring_service`».

**El muestreo vive en un hilo, no en el temporizador de Tk.** Leer contadores
de psutil es barato, pero un tropiezo de `disk_io_counters()` en Windows
congelaría la interfaz y el objetivo operativo es que responda en menos de
250 ms. El hilo es demonio y se detiene con un `threading.Event`.

**Arranque y parada explícitos.** Abrir el apartado no muestrea nada. Se
corresponde con «parada explícita» y «no añadir estrés activo para cumplir
monitorización» del plan, y evita consumo sorpresa con la ventana abierta.

**Al detener se conserva lo capturado.** La evidencia interesa justo después
de capturarla. `clear()` la descarta cuando el usuario lo pide.

**Dos gráficos apilados con escala independiente.** Las tasas de disco y de
red difieren en órdenes de magnitud; con eje Y compartido la red quedaría
pegada al cero e ilegible.

**El muestreador se inyecta.** En producción lee psutil; en pruebas es una
función determinista, de modo que la suite no duerme un segundo por muestra
y no depende del hardware de la máquina que la ejecute.

## Contratos

```text
Sample (inmutable)
    collected_at        datetime UTC
    disk_read_bps       float
    disk_write_bps      float
    net_sent_bps        float
    net_recv_bps        float

MonitoringService(sampler, interval_seconds=1.0, capacity=300)
    start()      arranca el muestreo; idempotente
    stop()       detiene y espera al hilo; idempotente
    snapshot()   tuple[Sample, ...] inmutable, la más reciente al final
    summary()    picos, medias y ventana temporal de la serie
    clear()      vacía el buffer
    is_running   bool
```

`ui/charts.py` expone `scale_series(values, width, height) -> list[point]`
como función pura y `TimeSeriesChart`, un widget sobre `tkinter.Canvas` que
la consume. La separación permite probar la geometría sin abrir ventana, que
es como están escritas hoy las pruebas de UI.

## Invariantes

- El buffer nunca excede `capacity`; al llenarse descarta la muestra más antigua.
- La primera lectura no produce muestra: sin lectura previa no hay tasa, y
  publicar una sería un pico falso de arranque.
- Un fallo del muestreador se registra y no interrumpe el hilo ni la aplicación.
- Sólo el hilo principal toca widgets; el hilo de muestreo jamás dibuja.
- Cerrar la ventana detiene el muestreo.
- Una serie vacía, de un solo punto o con todos los valores en cero se dibuja
  sin excepción ni división por cero.

## Pruebas de aceptación

Servicio, con muestreador falso y sin dormir: el buffer se corta en 300 y
descarta lo antiguo; `start` y `stop` son idempotentes; tras `stop()` no
entran más muestras; cada muestra lleva fecha UTC; `summary()` calcula picos
y medias sobre la ventana; un muestreador que lanza excepción no detiene el
hilo. Gráfico: `scale_series` con serie vacía, un punto, valores constantes
en cero y valores mixtos. Cierre: la ventana detiene el servicio.

Gates de la fase: pytest, ruff y mypy en verde.

## Recuperación

El servicio es independiente del análisis: si falla, el resto de la
aplicación sigue operativa y el apartado vuelve al estado detenido. Revertir
la rebanada es retirar los dos módulos nuevos y el bloque de UI que los usa,
sin tocar nada preexistente.
