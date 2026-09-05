# Trazabilidad del nuevo enunciado — 46 secciones

Fecha: 2026-09-04. Diseño pendiente de implementación, no certificación de cumplimiento.
Referencia canónica: [BUILD_PLAN](../BUILD_PLAN.md).
“Base” indica código reutilizable; “pendiente” exige implementación y nueva evidencia.

| Sección docente | Requisito / decisión | Base y brecha | Fase / evidencia prevista |
|---|---|---|---|
| 1–5 | Nombre, problema, misión y objetivos | Base gráfica; nuevo alcance diagnóstico | 1–7; nombre visible y demo |
| 6 | 15 opciones y Salir | Actual 12 opciones | 4; contrato navegación y prueba visual |
| 7 | General con conteos y estados | Matriz actual; conteos únicos pendientes | 5; resumen sin doble conteo |
| 8 | PCIe: nombre/clase/estado/ID e investigación | PnpCollector; conceptos y reglas pendientes | 3/6; tabla y marco conceptual |
| 9 | NIC PCIe no inicia | Estado obtenido; correlación driver y procedimiento pendientes | 3; fixture localizado |
| 10 | Red con IPv6 | IPv4/MAC/estado/velocidad disponibles | 2; IPv6 y configuración real |
| 11–12 | ipconfig, ping, DNS, ARP; Wi-Fi sin navegación | Pruebas pendientes | 2; caso DNS y evidencia de comandos |
| 13–14 | USB y memoria no reconocida | Catálogo disponible; relación volumen pendiente | 3; tres ramas del caso USB |
| 15–16 | Get-Disk/PhysicalDisk/Volume, disco 96 % | Get-Disk/uso disponibles | 3; datos físicos, tipo y recomendación |
| 17–18 | CPU 70/90, CPU98/RAM52/disco30 | Métricas disponibles; umbrales incorrectos para nueva rúbrica | 1; bordes y proceso a revisar |
| 19–20 | RAM 70/90, CPU30/RAM95/disco20 | Métricas disponibles; umbrales pendientes | 1; bordes y recomendaciones |
| 21–22 | GPU y límites de estado OK | Falta VideoProcessor y explicación por síntoma | 3; caso gráfico ambiguo |
| 23 | Dispositivo-driver-SO | DriverVersion disponible, falta ID de asociación | 3; join por ID y ausencias |
| 24–25 | Clasificación central y recomendaciones | Motor básico; reglas ampliadas pendientes | 1/4; estado original y evidencia |
| 26–27 | >=5 fichas con nueve campos | Dependencias existentes; investigación formal pendiente | 6; fichas completas y fuentes |
| 28 | Tres mecanismos Python–Windows | psutil y PowerShell actuales | 2; CMD fijo y captura de tres rutas |
| 29 | EXE; explicar .py/.exe y empaquetado | PyInstaller actual reutilizable | 6/7; explicación y máquina limpia |
| 30 | TXT o JSON con usuario/equipo y recomendaciones | HTML actual insuficiente | 5; JSON completo y UTF-8 |
| 31 | C1 APIPA/DHCP | Pendiente | 2; fixture, nunca ejecutar release/renew |
| 32 | C2 NIC PCIe aislada | Pendiente | 3; ocho pasos y alcance localizado |
| 33 | C3 USB controlador OK/periférico error | Pendiente | 3; distinguir bus y periférico |
| 34 | C4 CPU97/RAM91 | Motor parcial | 4; recursos, servicios e inicio |
| 35 | C5 todo OK y reinicio al jugar | Síntoma/conclusión pendientes | 1; diagnóstico adicional obligatorio |
| 36 | Variables, condiciones, ciclos, funciones, listas, diccionarios, excepciones, módulos, entrada/salida, archivos, subprocess y dependencia externa | Base reutilizable | 6; índice de ejemplos reales en fuente; sin herencia artificial |
| 37 | Arquitectura modular recomendada | Equivalente en collectors/infrastructure/diagnostics/reports | 0–7; conservar límites y pruebas |
| 38 | PDF técnico APA 7 completo | Arquitectura MD existente; PDF pendiente | 6; índice completo y revisión visual |
| 39 | >=5 pruebas reales | Tests actuales no sustituyen dossier | 6; siete pruebas previstas y obtenido real |
| 40 | Demo EXE y todos los módulos, conectividad, problema, recomendación y reporte | Parte del recorrido actual | 7; guion y ensayo |
| 41 | ZIP con estructura exacta | ZIP actual solo distribución | 7; inspección del paquete completo |
| 42 | README con integrantes, bibliotecas, casos y límites | README parcial, integrantes pendientes | 7; lista de campos revisada |
| 43 | Rúbrica 25 puntos | No reevaluada | Tabla inferior |
| 44–46 | Detección ≠ diagnóstico ≠ solución; justificar incertidumbre | Motor requiere ampliación | 1–7; cada hallazgo con evidencia y siguiente prueba |

## Rúbrica y evidencia a producir

| Criterio | Puntos | Fase y aceptación |
|---|---:|---|
| Investigación de bibliotecas/tecnologías | 2 | 6; >=5 fichas completas |
| Menú | 2 | 4; 15 opciones + Salir funcionales |
| CPU/RAM | 2 | 1; umbrales y casos §18/20 |
| Almacenamiento | 2 | 3; tres consultas y disco lleno |
| USB/periféricos | 3 | 3; detección, ramas y C3 |
| PCI/PCIe | 3 | 3; ID/driver, C2 y conceptos |
| Red | 3 | 2; IPv6, pruebas, DNS y C1 |
| GPU/controladores | 2 | 3; datos, asociación y límites |
| Motor/recomendaciones | 2 | 1/4; cinco integradores y fundamentos |
| Reportes | 1 | 5; JSON/TXT con campos completos |
| Ejecutable | 1 | 7; arranque sin Python instalado |
| Documentación APA 7 | 1 | 6; PDF renderizado y referencias |
| Presentación/demo | 1 | 7; recorrido docente completo |
| **Total** | **25** | **Evaluación pendiente; no puntos obtenidos** |

## Datos que se completarán al retomar

- Grupo, integrantes, institución, docente, fecha de entrega.
- Dispositivos de prueba disponibles y versión Windows/privilegios.
- Confirmación de resultados reales y autoría/fecha de cada evidencia.
- Versiones efectivas, fuentes conceptuales y referencias APA completas.

La documentación anterior conserva valor histórico, pero no sustituye estos gates.
