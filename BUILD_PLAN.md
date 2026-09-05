# Hardware Diagnostic & Repair Assistant — plan de producto

Fecha: 2026-09-05. Estado: **FASES 1, 2, 3 Y 4 COMPLETADAS; fases 5, 6 y 7 sin implementar**.
Proyecto personal con evolución comercial. Se conserva la aplicación funcional y se amplía por fases.
El desarrollo continúa cuando el usuario lo indique.

Investigación adicional solicitada: [fuentes técnicas y asesor de IA](docs/RESEARCH_AI_HARDWARE.md).
Propone recomendaciones verificables de drivers, ampliación RAM, compatibilidad GPU,
rendimiento por sesión y solución guiada con referencias oficiales.
Estado: diseño, no implementación; IA opcional y sin DB propia para el prototipo.
La IA complementa las reglas verificables del producto.

La [ampliación del asesor](docs/architecture/09-diagnostic-advisor.md) define los
slices E1–E8, todos NO INICIADOS, sus contratos, módulos, pruebas y recuperación.
Incluye «¿Por qué?», «Antes de comprar», «¿Se solucionó?», comparación de reportes,
exportación depurada y revisión de refresco. Mantiene maqueta, menú y ausencia de DB.
P23 incorpora candidatos concretos de GPU en E4–E5, ajustados a uso y presupuesto,
con SKU/fuentes y alternativa de no comprar cuando el diagnóstico no lo justifique.
No se garantiza eliminar todos los cuellos de botella ni se fija una GPU por defecto.
P24–P28 añaden prioridad de ampliaciones, asesor SSD, revisión de velocidad RAM,
GPU por aplicación y criterios para acudir a un técnico. P16–P18 se amplían, sin
duplicarse, con cambios recientes, ficha de compra y verificación de la ampliación.

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
- La estructura separa responsabilidades de medición, análisis y presentación.
  Mantener el paquete actual evita renombrados masivos y rotura de importaciones.
- Suscripciones, activación, nube, sensores avanzados, pruebas de estrés y firma
  comercial quedan en [la hoja de ruta diferida](docs/COMMERCIAL_ROADMAP.md).
  La consulta de sensores se incorporará cuando tenga compatibilidad y pruebas suficientes.

Alternativas descartadas: un archivo único mezcla UI y comandos; cliente-servidor
con DB agrega operación sin requisito; rehacer las carpetas literalmente no mejora
la mantenibilidad. Elegimos extender los módulos existentes con contratos compatibles.

## Estado observado y brechas

La tabla identifica capacidades de base y ampliaciones. El estado de fases debe
contrastarse con las pruebas del commit que vaya a distribuirse.

| Área | Base disponible | Trabajo pendiente |
|---|---|---|
| Interfaz | 12 opciones, análisis general/sección, consola | 15 opciones, Salir, síntoma y recomendaciones |
| CPU | Modelo, núcleos y clasificación de Fase 1 | Mantener pruebas de bordes y regresión |
| RAM | Total/disponible/uso y clasificación de Fase 1 | Mantener umbrales 70/90 y casos de regresión |
| Discos | psutil y Get-Disk | Get-PhysicalDisk/Get-Volume, asociaciones, tipo y recomendaciones |
| Red | MAC, IPv4, estado, velocidad | IPv6, gateway, DNS, APIPA y pruebas escalonadas |
| PnP | USB/PCI presentes e ID | Relación dispositivo-driver-volumen y diagnóstico localizado |
| GPU | Nombre, driver, memoria reportada | VideoProcessor, límites WMI, caso de síntomas con estado OK |
| Motor | Reglas básicas y conclusión | Recomendaciones estructuradas y cinco casos integradores |
| Monitorización | Muestra breve de E/S | Muestreo periódico acotado, detener y datos con fecha |
| Reportes | HTML | JSON obligatorio elegido; TXT adicional, equipo/usuario/recomendaciones |
| Distribución | EXE y ZIP | Manual de usuario, notas de versión, licencias de terceros y validación en equipo limpio |

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
    rules.py                      existente; clasificación central comprobable
    recommendations.py            [nuevo] causa, pasos y fundamento
  services/
    scan_service.py                un diagnóstico activo, progreso, errores
    connectivity_service.py       [nuevo] adaptador → IP → gateway → IP externa → DNS
    monitoring_service.py         [nuevo] muestras acotadas y parada
  reports/
    html_report.py                conservar
    json_report.py, txt_report.py [nuevos] exportaciones del producto
  ui/
    main_window.py                 maqueta existente ampliada
    theme.py, icons.py             conservar estilo
docs/
  architecture/                   decisiones y contratos
  REQUIREMENTS_TRACEABILITY.md    evidencia histórica y enlace al nuevo alcance
  PRODUCT_REQUIREMENTS.md      requisitos funcionales y aceptación
  research/                       [futuro] fichas bibliográficas y marco conceptual
  evidence/                       [futuro] pruebas reales consentidas
  USER_GUIDE.md                    [futuro] guía de uso y solución de problemas
tests/                            bordes, casos integradores, comandos y exportaciones
scripts/                          build y futuro ensamblador de entrega
```

Los módulos adicionales de asesoría están especificados en
[09-diagnostic-advisor.md](docs/architecture/09-diagnostic-advisor.md).
Se crearán únicamente al implementar el slice correspondiente, no en esta revisión.

Responsabilidades: medición → collectors; Windows → infrastructure;
reglas → diagnostics; exportación → reports. No es necesario introducir herencia:
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
La regla continua cubre valores decimales sin huecos; es una política de
clasificación de carga y no una prueba de daño físico.
RAM: NORMAL <70; ADVERTENCIA >=70 y <90; CRÍTICO >=90.
Disco: conservar provisionalmente 85/95, política del proyecto; 96 % debe ser CRÍTICO.
No diagnosticar daño físico basándose únicamente en porcentajes de utilización.

| Caso | Entrada | Salida y prueba de aceptación |
|---|---|---|
| CPU individual | CPU98/RAM52/disco30 | Carga CPU alta; revisar procesos |
| RAM individual | CPU30/RAM95/disco20 | Memoria alta; procesos, inicio y ampliación si recurrente |
| Disco | C:96 % | Espacio insuficiente; liberar espacio de forma guiada |
| DNS | Adaptador/IP/gateway/IP externa OK, DNS falla | Posible DNS; verificar configuración, sugerir limpieza sin ejecutarla |
| C1 | 169.254.x.x, sin gateway, ping falla | Posible DHCP/red local; sugerir ipconfig /all, /release y /renew |
| C2 | NIC PCIe error; resto OK | Problema localizado; ID, driver, administrador, conexión, actualización si procede, reinicio y repetir |
| C3 | Controlador USB OK; memoria error; driver problema; sin disco | Detección/configuración/driver del periférico, no condenar todo el bus |
| C4 | CPU97/RAM91/disco12; resto normal | Recursos elevados; revisar procesos, aplicaciones, servicios, inicio y memoria |
| C5 | Todo OK, reinicio al jugar | Sin anomalías básicas; investigar temperatura, fuente, GPU, drivers, eventos, RAM y hardware |
| USB ausente | Consulta USB sin filas | Lista vacía no prueba ausencia física; confirmar por ID antes de descartar el bus |
| USB con error | Periférico con código, host OK | Cubierto por C3: falla localizada sin condenar el bus |
| USB sin volumen | Medio USB sano sin letra de unidad | Detección/configuración del periférico; asignar letra o revisar formato, sin daño físico |

Los casos USB ausente, USB presente con error y USB OK sin volumen ya están
implementados y cubiertos por pruebas; la asociación disco-volumen la resuelve
Windows mediante Get-Disk/Get-Partition, nunca por coincidencia de nombres.
Para GPU con síntomas y estado OK, incluir también aplicación, DirectX
y conexiones. Memoria reportada por WMI no se presenta como VRAM exacta garantizada.
Estado Unknown requiere investigación; no prueba daño. Guardar el estado original.

## Interacción con Windows y controles

Usar las rutas apropiadas y documentar sus límites:

1. Python → psutil para CPU, RAM, red y E/S.
2. Python → PowerShell con catálogo cerrado y JSON.
3. Python → CMD mediante una invocación fija de cmd.exe /d /c ipconfig /all;
   herramientas adicionales ping.exe, nslookup.exe, arp.exe y driverquery.exe
   mediante lista de argumentos validada y shell=False.

PowerShell añadirá Get-NetAdapter, Get-NetIPConfiguration, Get-PhysicalDisk,
Get-Volume y VideoProcessor. Consultar identidad de controlador por ID del dispositivo.
CMD solo recibirá el literal aprobado; ningún síntoma o texto libre se interpolará.
Validar IP de gateway y destino; no incluir operadores de shell.

Ping 8.8.8.8, nslookup google.com y arp -a son consultas de referencia para el diagnóstico.
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
en logs ordinarios. Diseño de exportación: permitir omitir equipo y usuario;
mostrar los campos incluidos antes de guardar y anonimizar las copias compartidas. No habrá telemetría remota.
Recuperación: reiniciar app y repetir análisis; los reportes exportados no se borran.

## Fases ejecutables

Las Fases 1, 2 y 3 están completadas; las demás están **NO INICIADAS**. Cada fase debe
completar medición → regla → UI → reporte → prueba correspondiente antes de
avanzar; no crear carpetas vacías masivamente.

| Fase | Cambio y módulos | Pruebas/aceptación | Recuperación |
|---|---|---|---|
| 0 | Baseline, rama, fixtures; docs/tests | Capturar versión, ejecutar gates actuales y guardar artefacto/hash | Recuperar commit y ZIP inicial |
| 1 | domain, rules, engine, UI — **COMPLETADA** | Umbrales decimales/bordes; ERROR distinto de CRÍTICO; síntoma y C5 — gates pytest/ruff/mypy en verde | Campos nuevos opcionales; revertir slice |
| 2 | commands, network, connectivity, UI — **COMPLETADA** | Tres rutas Python–Windows; DNS, APIPA y C1; sin inyección ni UI bloqueada — gates pytest/ruff/mypy en verde | Omitir pruebas externas y conservar datos locales |
| 3 | pnp, drivers, storage, gpu — **COMPLETADA** | IDs correlacionados; C2/C3; Get-PhysicalDisk/Volume; GPU con síntoma — gates pytest/ruff/mypy en verde | Conservar core.py hasta paridad |
| 4A | monitoring_service, ui/charts, panel de E/S — **COMPLETADA** | Buffer 300 y parada explícita; series de disco y red en vivo; gates pytest/ruff/mypy en verde | Retirar los dos módulos nuevos y el panel |
| 4B | Gráficos de CPU, RAM, discos y red — **COMPLETADA** | Medidor y barras por apartado; series numéricas con prefijo `_`; gates pytest/ruff/mypy en verde | Ocultar el panel y conservar la tabla |
| 4C | diagnostics/recommendations — **COMPLETADA** | Causa, pasos, fundamento, comprobación y si modifica el sistema; en reporte y ficha; gates en verde | Mostrar sólo el problema posible |
| 4D | Menú de 15 opciones y Salir — **COMPLETADA** | 16 entradas; Conectividad y Recomendaciones propias; ver ≠ exportar; cierre ordenado; gates en verde | Volver a la navegación de 12 |
| 5 | reports JSON/TXT — **COMPLETADA** | schema_version 1.0, UTF-8, equipo/usuario omitibles, cobertura, límites y recomendaciones; gates en verde | HTML anterior intacto |
| 6 | Documentación de producto — **COMPLETADA** (pruebas reales pendientes de ejecutar) | Guía de uso, notas de versión, límites, licencias, política de datos, soporte y protocolo PR-01…PR-18 | Documentación versionada |
| 7 | packaging, distribución, README | EXE sin Python instalado, paquete verificable y recorrido completo | Última versión verificada |

### Especificación técnica del apartado de gráficos (Fase 4)

La fase 4 se ejecuta por rebanadas. La **4A** está implementada: el servicio
`monitoring_service` posee la serie acotada de 300 muestras con arranque y
parada explícitos, y `ui/charts` la dibuja en dos gráficos apilados de escala
independiente dentro del apartado de E/S. Disco y red no comparten eje porque
sus tasas difieren en órdenes de magnitud. Diseño y plan en
[docs/superpowers](docs/superpowers/specs/2026-09-05-monitorizacion-en-vivo-design.md).
La **4B** también está implementada. Los `facts` publicaban solo texto ya
formateado (`'43.5%'`, `'15.9 GB'`), inservible para graficar, así que se
establece esta convención:

> **Las claves de `facts` que empiezan por `_` son series numéricas para los
> gráficos, no texto para mostrar.** El reporte HTML y la ficha de la interfaz
> las omiten. Al añadir una serie nueva, respetar el prefijo: sin él aparecerá
> como texto crudo en el reporte.

Series actuales: `_uso` y `_nucleos` (CPU), `_uso` y `_memoria` (RAM),
`_volumenes` (almacenamiento) y `_adaptadores` (red). Ninguna clave de texto se
modificó ni se renombró, de modo que matriz, ficha, reporte y las pruebas de las
fases 1-3 siguen leyendo exactamente lo mismo.

La **4C** añade recomendaciones estructuradas. Cada procedimiento lleva causa,
pasos ordenados, fundamento, comprobación posterior y el campo `modifies_system`:

> **La aplicación propone procedimientos; nunca los ejecuta.** Los que alteran el
> equipo —`ipconfig /release`, `/renew`, `/flushdns`, reinstalar controladores—
> van marcados para que el usuario sepa qué va a cambiar antes de aplicarlos.

El generador es una función pura sobre los resultados ya clasificados: no consulta
Windows ni reinterpreta porcentajes, de modo que una recomendación no puede
contradecir la matriz. Un equipo sin anomalías y sin síntoma no genera ninguna.
Diseño en [docs/superpowers](docs/superpowers/specs/2026-09-05-recomendaciones-design.md).

La **4D** completa el menú: 15 apartados más Salir. Cuatro entradas no
corresponden a ningún componente —Conectividad, Recomendaciones, Exportar y
Salir—, así que `NAV_ITEMS` pasa a declarar componente **o** acción, nunca ambos.

Conectividad y Recomendaciones no miden nada nuevo: presentan las etapas que ya
produce `ConnectivityService` y los procedimientos de la 4C. «14. Generar
reporte» **muestra** el reporte completo y «15. Exportar diagnóstico» lo
**guarda**; son acciones distintas, como pide el enunciado.

**La fase 4 queda completa.**

La **fase 5** salda la deuda: la opción 15 exporta HTML, JSON y TXT según la
extensión elegida en el diálogo. El JSON lleva `schema_version` para que una
herramienta futura pueda leer exportaciones antiguas o avisar de
incompatibilidad, sin migraciones ni base de datos.

Antes de guardar se pregunta si incluir el nombre del equipo y del usuario;
al responder «No» se escribe `(omitido)` en ambos y el resto del contenido es
idéntico, conforme a la política de anonimizar las copias compartidas. Las
series con prefijo `_` no se exportan: existen para dibujar.

`errores_de_consulta` y `cobertura` van separados de `resultados`, porque una
consulta que no se completó deja el componente sin evaluar y no debe leerse
como ausencia de problemas.

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
Reestimar fechas según acceso a equipos, alcance y resultados de pruebas.

## Documentación del producto

Después de estabilizar las dependencias base, seguir E1 (guía), E2 (RAM), E3
(comparación/privacidad), E4 (compatibilidad GPU), E5 (rendimiento) y E6 (refresco).
E7 añade SSD tras fase 3/E2; E8 integra prioridades y fichas tras E2–E5/E7.
La IA I1–I5 complementa estos recorridos: E1 y E3 no dependen de una API; E2/E4
deben poder abstenerse y explicar reglas sin IA. No se promete compatibilidad por
nombre comercial ni porcentajes universales de cuello de botella.

Mantener una guía de instalación, uso, desinstalación y solución de problemas;
notas de versión, limitaciones conocidas, fuentes técnicas, política de datos,
dependencias/licencias y procedimiento de soporte. Documentar cada dependencia
adoptada con versión, propósito, instalación, ejemplo y límites.

Las referencias sobre buses, PCI/PCIe, USB, E/S, DMA, interrupciones, drivers,
PnP, SATA/NVMe y tipos de memoria servirán para explicar los diagnósticos.
No imponer un número de fichas ni un formato bibliográfico específico.
Conservar enlaces oficiales y fechas de consulta en la investigación.

## Validación y distribución

Validar escenarios reales de USB conectado/desconectado, conectividad, GPU,
discos, PCIe y drivers. Registrar entorno, versión, procedimiento, resultado
esperado y obtenido. Retirar dispositivos de prueba de forma segura.
Los fixtures de fallos y casos ambiguos se etiquetarán como simulados;
no sustituyen las pruebas reales. Una prueba bloqueada se registra como no ejecutada.

Distribución prevista, separada del repositorio de desarrollo:

```text
HardwareDiagnostic-<version>-windows-x64.zip
  HardwareDiagnostic/
    HardwareDiagnostic.exe
    _internal/              dependencias si onedir
    LEEME.txt               instalación, uso y soporte
    CHANGELOG.md            cambios y limitaciones de la versión
    THIRD_PARTY_NOTICES.txt licencias/atribuciones aplicables
```

El nombre final del EXE se cambiará cuando empaquetado y pruebas lo soporten;
la ruta del ejecutable actual continúa indicada en README.md.
Código fuente y evidencias internas permanecen en el repositorio privado.
No incluir reportes personales, credenciales, cachés o entorno virtual en el ZIP.
La eventual licencia comercial, firma y mecanismo de actualización están
planificados en COMMERCIAL_ROADMAP.md, no se consideran implementados.

Aceptar una versión cuando los requisitos de
[PRODUCT_REQUIREMENTS.md](docs/PRODUCT_REQUIREMENTS.md) tengan pruebas,
el EXE funcione en un equipo limpio y el recorrido de usuario esté verificado.
“No hay anomalías básicas” nunca equivale a “hardware sin fallas”.
La evidencia histórica se conserva con su alcance y fecha; no certifica
funciones nuevas ni preparación comercial.
