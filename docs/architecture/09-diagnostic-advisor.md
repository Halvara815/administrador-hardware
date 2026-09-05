# Asesor de diagnóstico, ampliación y solución guiada

Fecha: 2026-09-04. Estado: **DISEÑO APROBADO PARA PLANIFICACIÓN; NO IMPLEMENTADO**.
Complementa [BUILD_PLAN.md](../../BUILD_PLAN.md) y la
[investigación](../RESEARCH_AI_HARDWARE.md). No cambia el estado de la Fase 1.
Alcance focalizado: ampliar el monolito existente, sin DB y sin reparación automática.

## Decisión y alternativas

Elegimos reglas deterministas con evidencia local, fuentes verificadas y explicación
IA opcional. Frente a un chatbot que decide por sí solo, permite abstención y pruebas
reproducibles; frente a un catálogo central con cuentas/DB, conserva operación local
y evita mantenimiento de infraestructura sin necesidad confirmada. El coste es
validar manuales por modelo y aceptar cobertura parcial de sensores y fabricantes.

La diferenciación propuesta es el recorrido completo, no exclusividad de funciones:
síntoma, evidencia, siguiente comprobación, recomendación y verificación posterior.
No se ha realizado un benchmark de precisión ni una prueba comercial comparativa.

## Experiencia dentro de la maqueta

Conservar navegación izquierda, resultados a la derecha y consola pequeña de
evidencia de solo lectura. No agregar otra ventana principal ni más opciones de menú.

- RAM: tarjetas «Instalada», «Máximo verificado» y «Ampliación recomendada».
- GPU: separar «Compatibilidad», «Rendimiento durante esta sesión» y «GPU recomendadas».
- Recomendaciones: síntoma, «¿Por qué?», «Antes de comprar» y «¿Se solucionó?».
- Monitorización: seleccionar aplicación y contexto, iniciar/detener sesión acotada.
- Reportes: comparar dos JSON elegidos por el usuario y vista previa para compartir.
- Monitor/vídeo: sugerir revisar modos de refresco disponibles; no cambiarlos.
- Almacenamiento: asesor de SSD; Recomendaciones: «¿Qué actualizo primero?» y
  ficha común de compra. RAM/GPU: revisar configuración y uso por aplicación.

Cada tarjeta muestra hechos, hipótesis, evidencia, fuente/fecha, limitaciones y
siguiente paso. Un fallo de consulta nunca aparece como componente sano.

## RAM: capacidad ampliable verificable

Separar instalado, máximo reportado por firmware, máximo documentado y objetivo
recomendado. Recopilar modelo/SKU/revisión, módulos, capacidad, DDR, formato,
velocidad reportada/configurada, memoria soldada y ranuras verificables.
El manual OEM del modelo exacto es referencia principal; catálogo de compatibilidad
como contraste. Registrar discrepancias, no elegir automáticamente el mayor número.

Calcular margen = máximo total verificado − total instalado solo cuando ambos datos
sean coherentes. Ese margen no significa que se pueda añadir un módulo de ese tamaño:
enumerar configuraciones admitidas, capacidad por ranura y módulos que deben retirarse.
Ejemplo sintético: 8 GB instalados, máximo 32 GB con 2 × 16 GB; llegar a 32 GB puede
exigir sustituir el módulo actual, no añadir 24 GB. RAM soldada puede impedir ampliación.

Verificar DDR, formato, ECC/buffering, organización, límites CPU/placa/BIOS y
configuración del fabricante. No garantizar perfiles XMP/EXPO ni inferir canales
activos solo por contar módulos. Si faltan datos: «pendiente de verificar», con el
dato requerido; no recomendar SKU compatible ni calcular un máximo inventado.
Recomendar capacidad según presión de memoria recurrente y uso/presupuesto declarado,
no por una lectura aislada. No prometer un incremento de FPS por añadir RAM.

## GPU: dos problemas diferentes

Compatibilidad: comprobar ranura/enlace, dimensiones y espacio, fuente/conectores,
modelo de tarjeta, SO/controlador y requisitos del fabricante. Fuente, cableado y
gabinete pueden requerir datos manuales; distinguir declarado de detectado/verificado.
No asumir que una GPU portátil es reemplazable ni que «Windows la detecta» verifica
alimentación, estabilidad o compatibilidad completa. Un enlace PCIe de otra generación
no se clasificará automáticamente como incompatible.

Rendimiento: evaluar aplicación, resolución, ajustes, límite FPS/VSync, alimentación
y duración, junto a tiempos de fotograma, CPU por núcleo, GPU, RAM/VRAM y sensores
disponibles. PresentMon es candidato opcional, no dependencia adoptada. La carga
global CPU baja no descarta un hilo limitante; GPU baja puede deberse a límite FPS.
No generar un porcentaje universal de cuello de botella desde nombres comerciales.

Salida: indicios de limitación CPU/GPU/memoria/térmica, mixta o no concluyente,
limitados a la sesión observada. Proponer repetir una escena comparable cambiando
un solo factor; no confundir correlación con causalidad ni extrapolar FPS futuros.
Sensores ausentes quedan como desconocidos. No ejecutar estrés para obtener evidencia.

### Recomendación de compra de GPU

Proponer modelos concretos que se ajusten al equipo, presupuesto, país/moneda,
aplicaciones/juegos, resolución, calidad y FPS objetivo del usuario. «RTX 3050» es
un ejemplo de nombre que podría aparecer, no una recomendación predeterminada ni
una declaración de compatibilidad con el equipo actual. Identificar variante,
memoria, fabricante y SKU exactos antes de verificar especificaciones o precio.

Primero comprobar si cambiar GPU atiende la limitación observada. Si predominan
CPU, falta de RAM, temperatura o límite FPS, explicar por qué comprar GPU podría
no resolverla y ofrecer comprobaciones/alternativas sin compra. Sin mediciones,
presentar candidatos orientativos, no una mejora demostrada.

Cuando existan candidatos respaldados, mostrar hasta tres opciones: económica,
equilibrada y de mayor margen, sin forzar tres si la evidencia o presupuesto no
lo permiten. Cada tarjeta incluye SKU, compatibilidad verificada/pendiente,
motivo, limitación que podría reducir, restricciones que persistirían, coste total
incluidas adaptaciones necesarias, fuentes y fecha. Verificar precios y disponibilidad
al consultar; no inventarlos si no hay acceso a fuentes actuales.

Solo estimar FPS o mejora con benchmarks trazables y contexto comparable (CPU,
GPU, RAM, aplicación/versión, resolución y ajustes); indicar diferencias y rango
de incertidumbre. Sin esos datos, no cuantificar la mejora. Nunca usar «GPU perfecta»,
«cero cuello de botella» ni garantizar que desaparezcan todas las limitaciones.
La opción recomendada significa la mejor ajustada a los criterios y candidatos
verificados, no la mejor del mercado. No realizar compras ni abrir instaladores.

## Solución guiada y detalles de producto

- Red: adaptador → IP/DHCP → gateway → conectividad externa → DNS → aplicación/proxy.
  ICMP bloqueado no prueba ausencia de Internet; pruebas externas son opcionales.
- USB: detección → estado/driver → disco → partición/volumen → acceso. No formatear
  ni atribuir el fallo de un periférico al bus completo sin evidencia.
- Lentitud: observar procesos y recursos durante el síntoma, diferenciando espacio
  ocupado de actividad/latencia del disco. «Antes de comprar» prioriza pruebas sin coste.
- Reinicios/errores gráficos: preguntar hora y actividad; correlacionar eventos,
  drivers y sensores disponibles. Kernel-Power 41 no identifica una fuente defectuosa.
- «¿Por qué?»: evidencia favorable, otras explicaciones y comprobación faltante.
- «¿Se solucionó?»: repetir prueba y registrar resuelto según usuario, mejoría observada,
  persiste o no concluyente; una sola repetición no certifica reparación definitiva.
- «¿Qué cambió?»: comparar datos normalizados, versiones, cobertura y contexto de dos
  reportes; no atribuir causalidad a un driver por haber cambiado cerca del incidente.
- Compartir: vista previa depurada, sin usuario/hostname, seriales, IP/MAC, rutas ni claves.
  Mantener intacto el original. No denominar anónimo un reporte sin validar su contenido.
- Refresco: comparar modo activo con modos disponibles para resolución/conexión actuales;
  ofrecer guía, no prometer que el máximo comercial del monitor esté disponible.

## Módulos objetivo y contratos

### Detalles complementarios aprobados, pendientes

Se amplían recorridos existentes en lugar de duplicar pantallas o motores:

- **¿Qué actualizo primero? (P24):** ordenar acciones RAM/GPU/almacenamiento según
  evidencia, objetivo, presupuesto total y compatibilidad. Mostrar fundamento,
  requisitos previos, costes adicionales y opción «no comprar». No inventar un
  porcentaje de beneficio común a componentes distintos ni recomendar sustituir
  CPU/placa sin un asesor de compatibilidad específico. Si faltan mediciones,
  indicar qué comprobar antes de priorizar.
- **Asesor SSD (P25):** identificar unidad actual y comprobar en documentación del
  modelo exacto interfaz/protocolo, formato, dimensiones, conectores, bahías/ranuras
  accesibles y restricciones de instalación/arranque. No inferir compatibilidad
  SATA/NVMe por la etiqueta M.2, ni ranura libre porque Windows no detecte una unidad.
  Separar añadir de reemplazar, capacidad objetivo y accesorios requeridos. Mostrar
  candidato/SKU solo con fuentes; solicitar manual o comprobación física si falta
  evidencia. Orientar respaldo y planificación del traslado de datos; no clonar,
  particionar, formatear ni migrar automáticamente.
- **Velocidad RAM (P26):** comparar valor configurado con límites verificados del
  equipo/configuración; conservar unidades y origen, sin confundir MHz con MT/s.
  Un perfil comercial no es una velocidad garantizada. Explicar discrepancias
  posibles sin afirmar avería ni activar XMP/EXPO o modificar BIOS.
- **GPU por aplicación (P27):** asociar proceso/sesión y adaptador mediante evidencia
  disponible, admitiendo varias GPU y distinción entre renderizado/presentación.
  No deducir uso de una aplicación desde carga global o GPU que conecta la pantalla.
  Si no puede medirse, mostrar desconocido; si difiere de lo esperado, orientar
  revisión de preferencias, no cambiar configuración automáticamente.
- **Ficha antes de comprar (amplía P17):** reutilizar los asesores RAM/GPU/SSD para
  resumir SKU, compatibilidad, datos pendientes, accesorios, coste total conocido,
  fuentes/fecha y limitaciones. Precio desconocido no equivale a cero. Exportación
  voluntaria, sin compra ni apertura automática de instaladores.
- **El problema comenzó después de… (amplía P16/P18):** preguntar momento y cambios
  recientes de hardware, driver, aplicación o configuración. Etiquetar el relato
  como declarado por el usuario y contrastarlo con reportes/eventos cuando existan.
  La proximidad temporal orienta pruebas, no demuestra causa.
- **Verificar una ampliación instalada (amplía P18):** el usuario selecciona el
  cambio esperado y reporte previo; comprobar identidad, capacidad/configuración
  detectadas y repetir una prueba comparable. Diferenciar «detectado como se esperaba»,
  «mejoría observada», «persiste» y «no concluyente». Sin baseline no cuantificar
  mejora; detectar RAM/GPU/SSD no certifica estabilidad física ni reparación completa.
- **Cuándo acudir a un técnico (P28):** pasos con criterios explícitos de parada
  ante riesgos físicos declarados, fallos persistentes, posible pérdida de datos
  o comprobaciones fuera de cobertura. No emitir «todo seguro» por falta de sensores;
  no guiar apertura de fuentes ni trabajos eléctricos. Orientar asistencia y reporte
  depurado; no reservar servicios ni compartir datos sin solicitud.

Son requisitos de producto, no nuevos hallazgos empíricos ni afirmaciones de
exclusividad. Las especificaciones y precios se verificarán al implementar/consultar
cada asesor. No cambian la decisión sin DB ni la IA opcional.

Nombres propuestos, no crear archivos vacíos. Extender contratos actuales opcionalmente.

| Módulo futuro | Responsabilidad |
|---|---|
| collectors/memory_modules.py | Inventario modular y límites reportados |
| collectors/system_events.py, display_modes.py | Eventos acotados y modos de pantalla |
| infrastructure/performance_capture.py | Adaptador opcional PresentMon, timeout/cancelación |
| diagnostics/compatibility.py, performance.py | Reglas puras sobre evidencia suministrada |
| services/memory_advisor.py, gpu_advisor.py | Restricciones verificadas y alternativas |
| services/storage_advisor.py, upgrade_planner.py | SSD compatible y prioridad entre ampliaciones; reutilizar asesores |
| services/troubleshooting_service.py | Recorrido por síntoma y repetición de pruebas |
| services/report_comparison.py | Comparación de reportes explícitamente seleccionados |
| reports/redaction.py | Copia depurada y vista previa de exportación |
| knowledge/sources.py, ai/provider.py, ai/validation.py | Fuentes, IA intercambiable y validación |

Servicios orquestan recolectores, fuentes, reglas y explicación; las reglas no acceden
a Windows, red ni IA. UI consume dominio/servicios. Adaptadores se inyectan desde
app_factory; la IA no ejecuta herramientas del sistema. No incorporar DB vectorial.

Contratos propuestos, con schema_version y referencias de evidencia:

- UpgradeAssessment: modelo/revisión, installed_bytes, firmware_max_bytes,
  verified_max_bytes opcional, slots, soldered, supported_configurations,
  proposed_changes, compatibility_status, missing_checks, source_ids.
- PerformanceSession: app, resolución/ajustes declarados, FPS cap/VSync,
  alimentación, inicio/duración, muestras/unidades, cobertura, limitaciones y conclusión.
- GpuPurchaseAdvice: session_id opcional, objetivo/uso, presupuesto/moneda/país,
  candidates[] (SKU, especificaciones, compatibility_status, precio/fecha/fuente
  opcionales, costes adicionales, fundamento, benchmark_sources, limitaciones),
  recommended_candidate_id opcional, no_purchase_reason y missing_checks.
- TroubleshootingCase: síntoma, intervalo del fallo, pasos, resultados,
  hipótesis, siguiente comprobación y outcome. Pasos correctivos solo instrucciones.
- ComparisonResult: report_ids, cambios, campos no comparables, contexto y cautelas.
- Recommendation: evidence_ids, source_ids, fundamento, alternativas, datos faltantes,
  riesgo, acción propuesta, verificación posterior y origen (regla/IA).
- StorageUpgradeAssessment: unidad actual, modelo/revisión equipo, interfaz/protocolo,
  formato/dimensiones, ranuras verificadas, añadir/reemplazar, candidatos/SKU,
  accesorios, compatibility_status, missing_checks y source_ids.
- UpgradePlan: objetivo, presupuesto/moneda/país, acciones ordenadas referenciadas a
  asesores, dependencias/costes conocidos, evidencia y alternativa sin compra.
  No duplicar inventario; reutilizar Recommendation y fichas de candidatos.
- Extensiones opcionales: TroubleshootingCase incorpora cambios declarados con fecha,
  expected_upgrade y stop_criteria; PerformanceSession registra process_id, periodo,
  adapter_ids y papel observado; ComparisonResult conserva baseline ausente o
  contexto no comparable. No exportar rutas/nombres de procesos sensibles sin revisión.

## Seguridad, datos y límites operativos

**SIN DB local ni remota propia para estas ampliaciones.** Sesiones en memoria;
comparación mediante archivos JSON seleccionados, exportación explícita y logs mínimos.
Sin historial automático ni telemetría remota. IA externa requiere consentimiento y
perfil mínimo depurado; no transmitir reportes originales. Claves nunca en EXE/logs.
Cuentas/cuotas/pagos con clave del vendedor requerirían otra decisión de persistencia.

Importación JSON: limitar tamaño (objetivo 10 MiB), validar versión/esquema/profundidad,
rechazar entradas incompatibles sin ejecutar contenido ni seguir enlaces del reporte.
Exportar con confirmación de sobrescritura. Fuentes web no confiables: validar dominios,
enlaces y citas; sin shell, instalación, BIOS, registro, borrado ni compras desde IA.

Objetivos iniciales a medir: una sesión activa; captura pasiva 60 s por defecto,
máximo 300 s; series agregadas de 1 s hasta 300 muestras. Si se incorpora captura
por fotograma, procesarla con buffer acotado, no guardarla ilimitadamente en RAM.
Cancelar con respuesta visible <250 ms y cierre de captura objetivo <=2 s; informar
fallo de cierre sin detener procesos ajenos. Medir sobrecarga, no asumir impacto nulo.
Ejecutar IA local después del muestreo. Permiso insuficiente desactiva el adaptador;
no cambiar grupos, instalar servicios ni elevar privilegios automáticamente.

## Slices posteriores: todos NO INICIADOS

Las fases 0–7 siguen siendo el plan base. E identifica ampliaciones funcionales;
I1–I5 en investigación siguen siendo integración/evaluación de IA, no nuevas fases base.

| Slice y dependencia | Resultado vertical / módulos | Prueba de aceptación | Recuperación |
|---|---|---|---|
| E1, tras 2–5 | Guía por síntoma, evidencia, «antes de comprar»; troubleshooting + rules + UI/reporte | C1–C5, USB sin volumen, ICMP bloqueado, evento 41 aislado; sin reparación automática | Desactivar guía, conservar escaneo |
| E2, tras E1 e inventario I1 | RAM instalada/máximo/configuración; memory_advisor + compatibility + UI/reporte | Soldada, ranuras ambiguas, límites contradictorios, kit/reemplazo; abstención sin manual | Mostrar inventario básico |
| E3, tras E1 y JSON fase 5 | Antes/después, cambios y copia compartible; comparison + redaction + UI | Versiones incompatibles, contexto distinto, JSON malicioso, originales intactos y sin datos prohibidos | Mantener exportación previa; no migrar originales |
| E4, tras fase 3 y E2 | Compatibilidad GPU; gpu_advisor + UI/reporte | Fuente/espacio desconocidos, conector incorrecto, portátil no ampliable; pendiente != incompatible | Inventario GPU básico |
| E5, tras E4 y monitorización fase 4 | Rendimiento por sesión; capture + performance + UI/reporte | FPS limitado, hilo CPU saturado, GPU limitada, sensores ausentes, cancelar/timeout; no porcentaje universal | Adaptador nulo y resultado no concluyente |
| E6, tras fase 3 | Revisión de refresco; display_modes + reglas + UI/reporte | Multimonitor, resolución distinta, sin modos disponibles; ningún cambio automático | Ocultar sugerencia, conservar monitor/GPU |
| E7, tras fase 3 y E2 | Asesor SSD; storage_advisor + compatibility + UI/reporte | M.2 con protocolo distinto, ranura no verificada, añadir/reemplazar, accesorio/precio desconocidos; sin migración automática | Inventario almacenamiento básico |
| E8, tras E2–E5 y E7 | Prioridad de ampliación y ficha común; upgrade_planner + UI/reporte | Presupuesto insuficiente, costes adicionales, sin evidencia de beneficio y opción no comprar; reutilizar asesores | Mostrar recomendaciones por componente |

E1 añade cambios declarados y criterios de parada P28; E2 añade P26 (unidades,
perfil frente a configuración, datos ausentes); E3 verifica ampliaciones P18
(baseline ausente, capacidad inesperada, contexto distinto); E5 añade P27
(GPU híbrida, múltiples adaptadores, proceso terminado y permisos insuficientes).
Estas extensiones incluyen regla, UI, reporte y pruebas; comparten recuperación
y límites del slice existente. Todos E1–E8 siguen NO INICIADOS.

E4 añade filtros y fichas de candidatos en gpu_advisor; E5 completa su priorización
con evidencia de rendimiento y UI/reporte. P23 exige pruebas de presupuesto
insuficiente, fuente desconocida, variantes de nombre similar, precio ausente,
benchmarks no comparables y limitación CPU/FPS donde cambiar GPU no está justificado.
Sin fuente o sesión válida, degradar a orientación/abstención y conservar inventario.

Cada slice conserva reportes/contratos previos, registra duración, cobertura y resultado
sin contenido personal, y actualiza manual/limitaciones. Rama y commit recuperables;
revertir solo su cambio, no trabajo ajeno. No migraciones de DB ni nuevas dependencias
hasta validar licencia/release, Windows objetivo, permisos, empaquetado y cancelación.

Gates: tests de reglas/contratos, integración con fixtures, regresión UI/reportes,
lint/tipado, revisión de secretos/licencias y EXE en equipo limpio al distribuir.
Para E2/E4 probar laptop y escritorio con especificaciones verificadas; para E5,
GPU integrada/dedicada y cargas comparables. Sin hardware de prueba, registrar
NEEDS_USER_VERIFICATION; mocks no certifican precisión real. Ninguna recomendación
compatible sin evidencia mínima, ninguna reparación automática y diagnóstico básico
operativo sin proveedor IA, Internet, sensores o PresentMon.

Revisar el diseño si hace falta catálogo mantenido a escala, historial consultable,
cuentas o pruebas activas; no deducir su autorización de esta planificación.
