# Hardware Diagnostic & Repair Assistant — plan del nuevo enunciado

Fecha: 2026-09-04. Estado: **FASE 1 COMPLETADA; resto del plan sin implementar**.
Fuente: enunciado del docente, secciones 1–46, adjuntado por el usuario.
Este plan sustituye la prioridad comercial anterior. La app v0.1.0 permanece funcional.
El desarrollo continúa cuando el usuario lo indique.

Investigación adicional solicitada: [fuentes técnicas y asesor de IA](docs/RESEARCH_AI_HARDWARE.md).
Propone recomendaciones verificables de drivers y RAM con referencias oficiales.
Estado: diseño, no implementación; IA opcional y sin DB propia para el prototipo.
La ampliación no reemplaza las reglas ni la rúbrica académica.

## Decisiones y fundamento

- Conservar Python, CustomTkinter y el monolito modular: ya resuelven ventana,
  evidencia tipo terminal, procesamiento en segundo plano y ejecutable.
- Mantener la maqueta: navegación izquierda y resultados a la derecha, con
  consola pequeña de evidencia. Adaptar posteriormente a 15 opciones y Salir.
- **NO se utilizará DB**, local ni remota. Analizar varios computadores en el
  planteamiento no exige inventario centralizado. Se ejecutará la app en cada equipo.
- Resultados y muestras en memoria; archivos TXT/JSON/HTML por exportación explícita.
  Logs técnicos rotativos existentes, sin evidencia cruda ni datos personales completos.
- “Repair Assistant” significa proponer procedimientos correctivos, no reparar
  automáticamente. No se ejecutarán release/renew, limpieza DNS o cambios de drivers.
- La implementación recomendada por el docente es una guía de responsabilidades.
  Mantener el paquete actual evita renombrados masivos y rotura de importaciones.
- Suscripciones, activación, nube, sensores avanzados, pruebas de estrés y firma
  comercial quedan en [la hoja de ruta diferida](docs/COMMERCIAL_ROADMAP.md).
  El enunciado pide recomendar investigación térmica; no exige implementarla.

Alternativas descartadas: un archivo único mezcla UI y comandos; cliente-servidor
con DB agrega operación sin requisito; rehacer las carpetas literalmente no mejora
la evaluación. Elegimos extender los módulos existentes con contratos compatibles.

## Estado observado y brechas

La evidencia histórica no certifica el nuevo enunciado. Los 18 tests aprobados en
la última construcción no cubren todavía las nuevas reglas ni los cinco casos.

| Área | Base disponible | Trabajo pendiente |
|---|---|---|
| Interfaz | 12 opciones, análisis general/sección, consola | 15 opciones, Salir, síntoma y recomendaciones |
| CPU | Modelo, núcleos, uso; umbrales 85/95 | Aplicar clasificación docente y probar bordes |
| RAM | Total/disponible/uso; umbrales 80/95 | Aplicar 70/90 |
| Discos | psutil y Get-Disk | Get-PhysicalDisk/Get-Volume, asociaciones, tipo y recomendaciones |
| Red | MAC, IPv4, estado, velocidad | IPv6, gateway, DNS, APIPA y pruebas escalonadas |
| PnP | USB/PCI presentes e ID | Relación dispositivo-driver-volumen y diagnóstico localizado |
| GPU | Nombre, driver, memoria reportada | VideoProcessor, límites WMI, caso de síntomas con estado OK |
| Motor | Reglas básicas y conclusión | Recomendaciones estructuradas y cinco casos integradores |
| Monitorización | Muestra breve de E/S | Muestreo periódico acotado, detener y datos con fecha |
| Reportes | HTML | JSON obligatorio elegido; TXT adicional, equipo/usuario/recomendaciones |
| Entrega | EXE y ZIP de distribución | ZIP académico con fuente, PDF APA 7, evidencias y requirements.txt |

## Estructura objetivo, no creada todavía

Los archivos con [nuevo] son propuestas. Los actuales se extenderán por fases.

```text
src/hardware_admin/
  main.py                         entrada y título visible futuro
  app_factory.py                  composición de servicios
  domain/
    models.py                     evidencia, dispositivo, resultado y reporte
  collectors/
    core.py                       compatibilidad durante extracción gradual
    cpu.py, memory.py             [nuevos] mediciones por componente
    storage.py, network.py        [nuevos] volúmenes/adaptadores
    pnp.py, gpu.py, drivers.py    [nuevos] identidad y asociaciones
  infrastructure/
    powershell.py                 catálogo CIM/PnP/Storage/Net
    commands.py                   [nuevo] CMD/herramientas con argumentos cerrados
  diagnostics/
    engine.py                     conclusión global y alcance
    rules.py                      [nuevo] clasificación central comprobable
    recommendations.py            [nuevo] causa, pasos y fundamento
  services/
    scan_service.py                un diagnóstico activo, progreso, errores
    connectivity_service.py       [nuevo] adaptador → IP → gateway → IP externa → DNS
    monitoring_service.py         [nuevo] muestras acotadas y parada
  reports/
    html_report.py                conservar
    json_report.py, txt_report.py [nuevos] exportaciones del enunciado
  ui/
    main_window.py                 maqueta existente ampliada
    theme.py, icons.py             conservar estilo
docs/
  architecture/                   decisiones y contratos
  REQUIREMENTS_TRACEABILITY.md    evidencia histórica y enlace al nuevo alcance
  ASSIGNMENT_TRACEABILITY.md      requisitos 1–46 y aceptación futura
  research/                       [futuro] fichas bibliográficas y marco conceptual
  evidence/                       [futuro] pruebas reales consentidas
  Informe.md                      [futuro] fuente del informe APA 7
tests/                            bordes, casos integradores, comandos y exportaciones
scripts/                          build y futuro ensamblador de entrega
```

Mapeo al docente: diagnostico → collectors; sistema → infrastructure;
analisis → diagnostics; reportes → reports. No es necesario introducir herencia:
protocolos y composición actuales permiten probar recolectores aislados.

Dependencias: UI → servicios/dominio; servicios → recolectores/motor/reportes;
recolectores → infraestructura/dominio; motor → dominio. Ningún motor consulta
Windows directamente. La UI actualiza widgets solo desde su hilo principal.
Las asociaciones se realizan por InstanceId/PNPDeviceID/DeviceID y relaciones
reportadas por Windows, nunca por coincidencia de nombres solamente.

## Contratos e invariantes propuestos

Extender sin eliminar los contratos actuales:

- Evidencia: fuente, consulta identificable, salida limitada, UTC, éxito y error.
- Medición: valor numérico, unidad, momento, intervalo y disponibilidad.
- Dispositivo: ID estable, clase, presencia, estado Windows, código y asociaciones.
- Hallazgo: componente/dispositivo, severidad, evidencia, explicación y causas posibles.
- Recomendación: pasos ordenados, fundamento, comprobación posterior y si modifica el sistema.
- Contexto: síntoma opcional y dispositivo esperado seleccionado por el usuario.
- Reporte: schema_version, versión app, fecha, equipo, usuario, SO, resultados,
  errores de consulta, recomendaciones, conclusión, cobertura y limitaciones.

Separar severidad de disponibilidad. Dato ausente, truncado, permiso denegado,
JSON inválido, prueba omitida o fallo de consulta no equivalen a hardware sano.
Una lista vacía tampoco demuestra que un USB esperado nunca haya existido.

Preservar los valores de enum internos actuales y traducir a NORMAL, ADVERTENCIA,
CRÍTICO/PROBLEMA en presentación. No confundir PASS de una consulta con salud física.
No afirmar “sin problemas”: expresar “sin anomalías en los indicadores consultados”.
Un síntoma persistente obliga a proponer diagnóstico adicional aunque todo figure OK.

## Menú gráfico previsto

1. Diagnóstico general: resumen de SO, arquitectura, CPU, RAM, discos, red, GPU,
   total de dispositivos únicos y dispositivos con problemas.
2. CPU.
3. RAM.
4. PCI/PCIe.
5. Red.
6. USB.
7. Almacenamiento.
8. GPU/vídeo.
9. Controladores.
10. Dispositivos con problemas.
11. Conectividad.
12. Monitorización.
13. Recomendaciones.
14. Generar reporte: vista del reporte completo.
15. Exportar diagnóstico: guardar JSON/TXT y conservar HTML.
0. Salir: cierre ordenado de tareas y ventana.

La entrada será mediante botones, selección y síntoma opcional. No es requisito
abrir terminal externa. Mostrar conteos únicos, no sumar USB/PCI/errores duplicados.
Mostrar si un catálogo está limitado: hoy hay consultas con límites 100/150.

## Reglas y casos obligatorios

CPU: NORMAL <=70; ADVERTENCIA >70 y <90; CRÍTICO >=90.
El docente escribe 0–70, 71–89 y 90–100 para enteros; la regla continua >70
cubre los decimales sin huecos. Documentar esta interpretación en el informe.
RAM: NORMAL <70; ADVERTENCIA >=70 y <90; CRÍTICO >=90.
Disco: conservar provisionalmente 85/95, política del proyecto; 96 % debe ser CRÍTICO.
No diagnosticar daño físico basándose únicamente en porcentajes de utilización.

| Caso | Entrada | Salida y prueba de aceptación |
|---|---|---|
| CPU individual (§18) | CPU98/RAM52/disco30 | Carga CPU alta; revisar procesos |
| RAM individual (§20) | CPU30/RAM95/disco20 | Memoria alta; procesos, inicio y ampliación si recurrente |
| Disco (§16) | C:96 % | Espacio insuficiente; liberar espacio de forma guiada |
| DNS (§12) | Adaptador/IP/gateway/IP externa OK, DNS falla | Posible DNS; verificar configuración, sugerir limpieza sin ejecutarla |
| C1 (§31) | 169.254.x.x, sin gateway, ping falla | Posible DHCP/red local; sugerir ipconfig /all, /release y /renew |
| C2 (§32) | NIC PCIe error; resto OK | Problema localizado; ID, driver, administrador, conexión, actualización si procede, reinicio y repetir |
| C3 (§33) | Controlador USB OK; memoria error; driver problema; sin disco | Detección/configuración/driver del periférico, no condenar todo el bus |
| C4 (§34) | CPU97/RAM91/disco12; resto normal | Recursos elevados; revisar procesos, aplicaciones, servicios, inicio y memoria |
| C5 (§35) | Todo OK, reinicio al jugar | Sin anomalías básicas; investigar temperatura, fuente, GPU, drivers, eventos, RAM y hardware |

Añadir casos USB ausente, USB presente con error y USB OK sin volumen (§14).
Para GPU con síntomas y estado OK (§22), incluir también aplicación, DirectX
y conexiones. Memoria reportada por WMI no se presenta como VRAM exacta garantizada.
Estado Unknown requiere investigación; no prueba daño. Guardar el estado original.

## Interacción con Windows y controles

Demostrar tres rutas con evidencia en el informe:

1. Python → psutil para CPU, RAM, red y E/S.
2. Python → PowerShell con catálogo cerrado y JSON.
3. Python → CMD mediante una invocación fija de cmd.exe /d /c ipconfig /all;
   herramientas adicionales ping.exe, nslookup.exe, arp.exe y driverquery.exe
   mediante lista de argumentos validada y shell=False.

PowerShell añadirá Get-NetAdapter, Get-NetIPConfiguration, Get-PhysicalDisk,
Get-Volume y VideoProcessor. Consultar identidad de controlador por ID del dispositivo.
CMD solo recibirá el literal aprobado; ningún síntoma o texto libre se interpolará.
Validar IP de gateway y destino; no incluir operadores de shell.

Ping 8.8.8.8, nslookup google.com y arp -a cumplen los ejemplos del docente.
Registrar interfaz/ruta seleccionada, pues VPN o loopback no demuestran Internet.
Un ping sin respuesta puede reflejar ICMP bloqueado: resultado no concluyente
sin pruebas complementarias. ARP solo muestra vecinos conocidos, no todos los equipos.

Amenazas concretas: inyección de comandos → catálogo/argumentos y tests;
falso positivo → evidencia y casos ambiguos; bloqueo → timeout/cancelación;
datos personales en exportación → aviso previo y elección de destino;
sobrescritura → confirmación; permisos insuficientes → estado explícito.
No aumentar privilegios automáticamente ni ejecutar reparaciones.
El síntoma y la evidencia se tratarán como datos, nunca como instrucciones.

## Objetivos operativos propuestos

Objetivos a medir, no garantías: un escaneo activo; límite total de escaneo básico
60 s; consultas individuales <=15 s; pruebas de red acotadas a 5 s por intento
y 30 s totales. Al exceder el límite mostrar resultados parciales.
Monitorización por defecto cada 1 s, buffer máximo 300 muestras, parada explícita.
UI confirma la acción en menos de 250 ms en el equipo de referencia.
No añadir estrés activo para cumplir “monitorización”.

Registrar ID de sesión, consulta, duración y resultado; no guardar usuario/IP/MAC
en logs ordinarios. Exportación incluye equipo y usuario por requisito docente:
advertirlo y anonimizar copias compartidas como evidencias. No habrá telemetría remota.
Recuperación: reiniciar app y repetir análisis; los reportes exportados no se borran.

## Fases ejecutables

La Fase 1 está completada; las demás están **NO INICIADAS**. Cada fase debe
completar medición → regla → UI → reporte → prueba correspondiente antes de
avanzar; no crear carpetas vacías masivamente.

| Fase | Cambio y módulos | Pruebas/aceptación | Recuperación |
|---|---|---|---|
| 0 | Baseline, rama, fixtures; docs/tests | Capturar versión, ejecutar gates actuales y guardar artefacto/hash | Recuperar commit y ZIP académico |
| 1 | domain, rules, engine, UI — **COMPLETADA** | Umbrales decimales/bordes; ERROR distinto de CRÍTICO; síntoma y C5 — gates pytest/ruff/mypy en verde | Campos nuevos opcionales; revertir slice |
| 2 | commands, network, connectivity, UI | Tres rutas Python–Windows; DNS, APIPA y C1; sin inyección ni UI bloqueada | Omitir pruebas externas y conservar datos locales |
| 3 | pnp, drivers, storage, gpu | IDs correlacionados; C2/C3; Get-PhysicalDisk/Volume; GPU con síntoma | Conservar core.py hasta paridad |
| 4 | monitoring, charts por apartados, recommendations, UI | Gráficos visuales integrados en apartados (CPU, RAM, Discos, Red, E/S); buffer/parada; 15 opciones+Salir | Cancelar tareas y volver a última UI estable |
| 5 | reports JSON/TXT, general | Esquema completo, UTF-8, fecha/equipo/usuario, límites y recomendaciones | HTML anterior disponible; no tocar reportes previos |
| 6 | docs/research, Informe.md | >=5 fichas, marco conceptual, APA 7, >=5 pruebas reales | Mantener borradores y evidencia versionados |
| 7 | packaging, entrega, README | EXE sin Python instalado, ZIP exacto y demostración completa | Última entrega verificada; no publicar fallos |

### Especificación técnica del apartado de gráficos (Fase 4)

Los gráficos interactivos y de diagnóstico se integran en la **Fase 4** como parte de la modernización de la UI y el servicio de monitorización, respetando estrictamente los principios arquitectónicos del proyecto:

1. **Aislamiento por capas (sin daños en la lógica existente)**:
   - La capa de presentación (`hardware_admin.ui`) es la **única** responsable de renderizar gráficos.
   - No se alteran los contratos de `domain`, los recolectores de `collectors` ni las reglas de diagnóstico de `diagnostics`.
   - Los gráficos consumen exclusivamente los datos estructurados y normalizados ya provistos en `ComponentResult.facts` o en las series de `monitoring_service`.

2. **Apartados con gráficos asignados**:
   - **CPU**: Medidor/gauge de uso total (%) y barras de distribución por núcleo lógico según datos disponibles.
   - **Memoria (RAM)**: Barra de asignación de capacidad (usada vs. libre vs. total) y estado de memoria virtual.
   - **Discos / Almacenamiento**: Gráfico de barras apiladas de espacio por unidad/volumen (usado vs. disponible) y salud reportada.
   - **Red**: Gráficos de velocidad de enlace por adaptador y estado de actividad de interfaces.
   - **Monitorización (E/S)**: Gráfico de series de tiempo (gráfico de líneas dinámico sobre buffer de 300 muestras) mostrando tasas de lectura/escritura en disco y tráfico de red en vivo con botón de parada.

3. **Restricción de dependencias y rendimiento**:
   - No se introducen dependencias pesadas adicionales (como `matplotlib` o `numpy`) para evitar sobrecargar el empaquetado de PyInstaller o ralentizar el arranque.
   - Se implementarán mediante widgets modulares nativos sobre `tkinter.Canvas` y componentes de `customtkinter`, sincronizados con la paleta de colores de `theme.py`.

Cada fase registrará fallos y duración de pruebas. Sin migraciones de DB;
schema_version permitirá leer exportaciones antiguas o avisar incompatibilidad.
No imponer un plazo comercial al trabajo académico: recalcular tras la Fase 0
según acceso a equipos, integrantes y fecha de entrega.

## Investigación y documentación del docente

Documento futuro Informe.pdf (no generado en esta etapa): portada con integrantes,
introducción, problema, objetivos, marco conceptual, bibliotecas, arquitectura,
menú, desarrollo, casos, pruebas, resultados, dificultades/soluciones,
conclusiones y referencias APA 7. No inventar resultados ni datos de estudiantes.

Marco conceptual obligatorio: buses, PCI/PCIe y lanes, USB, E/S, DMA,
interrupciones, drivers, periféricos, x86, PnP/enumeración/recursos;
SATA/NVMe/USB y HDD/SSD. Distinguir bus de transporte y tipo de medio.

Documentar mínimo cinco fichas; proponemos psutil, subprocess, platform, socket,
pathlib y PyInstaller. Cada ficha incluirá nombre, versión realmente utilizada,
autor/proyecto, propósito, instalación, funciones, ejemplo, uso aquí y limitaciones.
Los módulos estándar siguen la versión Python del build y no se instalan con pip.
psutil 7.2.2 y PyInstaller 6.22.2 están fijados en el lockfile actual;
registrar la versión efectiva al construir. Evaluar wmi/pywin32 como alternativas;
pynput no es necesario para diagnóstico y no se capturará teclado.

Bibliografía inicial oficial consultada el 2026-09-04 (convertir a APA 7 al redactar):

- [psutil, API y mediciones](https://psutil.readthedocs.io/stable/index.html).
- [Python, subprocess](https://docs.python.org/3/library/subprocess.html).
- [Microsoft, ipconfig](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/ipconfig).
- [Microsoft, nslookup](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/nslookup).
- [PyInstaller, funcionamiento](https://pyinstaller.org/en/stable/operating-mode.html).

Explicar .py frente a .exe: PyInstaller empaqueta intérprete y dependencias;
no vuelve el código inmune a inspección ni genera automáticamente binarios para
otros sistemas. Preferir onedir conservando sus dependencias; onefile es opcional.
Añadir fuentes oficiales de cada concepto restante antes de cerrar el PDF.

## Pruebas reales, evidencia y entrega

Ejecutar y documentar al menos cinco pruebas reales (planificar siete):
USB conectado, USB desconectado, ping, GPU, disco, PCIe y driver.
USB desconectado se prepara con un dispositivo de prueba y retirada segura;
no desconectar almacenamiento en uso. No provocar fallos físicos ni cambiar drivers.

Cada registro: ID, fecha, equipo anonimizado, entorno/permisos, procedimiento,
resultado esperado, resultado obtenido, captura/salida y estado.
Los cinco integradores se prueban con fixtures reproducibles, etiquetados como
simulados. No cuentan automáticamente como las cinco pruebas reales.
Prueba bloqueada por equipo/permisos queda NO EJECUTADA, nunca APROBADA.

ZIP futuro: Proyecto_HardwareDiagnostic_GrupoX.zip; GrupoX e integrantes pendientes.
Estructura:
```text
Proyecto/
  Ejecutable/HardwareDiagnostic.exe
  Ejecutable/_internal/          dependencias si onedir
  CodigoFuente/                 src, tests, scripts, assets y configuración
  Reportes/                     diagnóstico ejemplo anonimizado TXT/JSON
  Documentacion/Informe.pdf
  Evidencias/                   pruebas reales documentadas
  requirements.txt              dependencias necesarias fijadas
  README.md                     integrantes, requisitos, instalación, uso y límites
```

Crear requirements.txt coherente con pyproject/lockfile en la fase de entrega;
no instalar dependencias nuevas ahora. Excluir .venv, cachés, secretos y reportes
personales. Nombre nuevo del EXE solo cuando el build y sus tests lo soporten.

Aceptación final: rúbrica de 25 puntos trazada en
[ASSIGNMENT_TRACEABILITY.md](docs/ASSIGNMENT_TRACEABILITY.md);
todos los casos obligatorios pasan; cinco pruebas reales documentadas;
PDF revisado visualmente; EXE probado en máquina limpia y demo §40 completa.
“No hay anomalías básicas” nunca equivale a “hardware sin fallas”.
Los gates históricos en docs/architecture/08-production-readiness.md se refieren
exclusivamente a v0.1.0, no a esta nueva entrega.
