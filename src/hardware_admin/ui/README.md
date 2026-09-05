# Capa visual

La ventana se dividirá en:

- `MainWindow`: composición, navegación y ciclo de vida.
- `NavigationPanel`: los 15 apartados más Salir y el botón de análisis.
- `SummaryPanel`: tarjetas rápidas de CPU, RAM, disco y red.
- `DiagnosticMatrix`: evidencia, estado y posible problema.
- `EvidenceConsole`: salida monoespaciada, limitada y de solo lectura.
- `ConclusionPanel`: conclusión y recomendaciones.
- `charts.py`: series de tiempo, medidor y barras sobre `tkinter.Canvas`.

La UI nunca ejecutará PowerShell directamente. Iniciará `ScanService` en un
trabajador y aplicará los resultados desde el hilo principal de la interfaz.


## Evolución visual prevista

Conservar navegación lateral, matriz y evidencia. El plan prevé ampliar a quince
opciones y Salir, con gráficos por componente y monitorización acotada.
Los gráficos se renderizarán en la UI con Canvas/CustomTkinter y consumirán datos
normalizados; no deben ejecutar consultas Windows ni presentar mediciones ausentes
como cero. La IA futura se integrará en recomendaciones con fuentes visibles.
