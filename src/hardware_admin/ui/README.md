# Capa visual

La ventana se dividirá en:

- `MainWindow`: composición, navegación y ciclo de vida.
- `NavigationPanel`: las doce opciones y el botón de análisis.
- `SummaryPanel`: tarjetas rápidas de CPU, RAM, disco y red.
- `DiagnosticMatrix`: evidencia, estado y posible problema.
- `EvidenceConsole`: salida monoespaciada, limitada y de solo lectura.
- `ConclusionPanel`: conclusión y recomendaciones.

La UI nunca ejecutará PowerShell directamente. Iniciará `ScanService` en un
trabajador y aplicará los resultados desde el hilo principal de la interfaz.

