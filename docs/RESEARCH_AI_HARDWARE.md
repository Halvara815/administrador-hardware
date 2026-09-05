# Investigación: fuentes técnicas y asesor de IA para hardware

Fecha de consulta: 2026-09-04.
Estado: investigación y diseño propuesto; no se instaló software, contrató API,
envió inventario del equipo a terceros ni implementó integración.
Complementa [BUILD_PLAN.md](../BUILD_PLAN.md); la rúbrica académica sigue siendo prioritaria.
Método: documentación del fabricante y repositorios upstream. No se han ejecutado
los proyectos candidatos ni medido comparativamente modelos de IA.

## 1. Decisión recomendada

Construir un asesor basado en tres elementos: inventario real, comprobaciones de
compatibilidad y explicación asistida por IA con fuentes. Un modelo lingüístico
no determina por sí solo qué driver instalar o qué módulo comprar.

El asesor debe contestar:

- Qué componente está instalado y qué datos no pudieron obtenerse.
- Qué problema se observó y qué otras explicaciones siguen siendo posibles.
- Si existe una actualización aplicable y por qué conviene revisarla.
- Qué especificación de RAM es compatible y qué productos la cumplen.
- Qué dato falta antes de recomendar una compra o actualización.

Su ubicación propuesta es la opción 13, Recomendaciones, con acciones
“Explicar diagnóstico”, “Revisar controladores” y “Consultar ampliación de RAM”.
La información básica y las reglas deterministas funcionan sin IA ni Internet.
Las respuestas asistidas identifican modelo, fecha de consulta, evidencia y fuentes.

## 2. Repositorios útiles y uso propuesto

| Proyecto upstream | Hallazgo documentado | Uso y decisión |
|---|---|---|
| [giampaolo/psutil](https://github.com/giampaolo/psutil) | Métricas de sistema y procesos; [licencia BSD-3-Clause](https://github.com/giampaolo/psutil/blob/master/LICENSE) | Conservar la dependencia existente; no cubre catálogo comercial de RAM/drivers |
| [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) | Sensores de temperatura, ventilador, voltaje, carga y frecuencia; biblioteca .NET; MPL 2.0 y licencias de terceros | Candidato para futura fase térmica, mediante adaptador; verificar permisos y redistribución |
| [smartmontools](https://github.com/smartmontools/smartmontools) | Herramientas SMART, soporte Windows; GPL v2 | Candidato opcional para discos; evaluar invocación separada y obligaciones de distribución |
| [ollama/ollama](https://github.com/ollama/ollama) | Ejecución de modelos, motor con [licencia MIT](https://github.com/ollama/ollama/blob/main/LICENSE) | Alternativa local; cada modelo descargado tiene su propia licencia y necesidades de memoria |
| [googleapis/python-genai](https://github.com/googleapis/python-genai) | SDK oficial de Gemini; repositorio Apache 2.0 | Candidato para adaptador de IA remota |
| [anthropics/anthropic-sdk-python](https://github.com/anthropics/anthropic-sdk-python) | SDK oficial de Claude | Alternativa para IA remota; verificar LICENSE de la versión que se seleccione |

No copiar aplicaciones completas ni integrar repositorios por número de estrellas.
Antes de adoptar: seleccionar release/commit, revisar licencia y terceros, probar
Windows objetivo, dependencias, errores, cancelación, empaquetado y seguridad.
Las condiciones de un SDK no sustituyen los términos del servicio de IA.
LibreHardwareMonitor advierte en su README que no está afiliado a
librehardwaremonitor.com: usar el repositorio upstream como punto de distribución.
No introducir acceso privilegiado a sensores solo para enriquecer la IA.

## 3. Controladores: datos necesarios y fuentes

Microsoft explica que los [Hardware IDs](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/hardware-ids)
permiten asociar un dispositivo con paquetes de controladores. El nombre comercial
por sí solo no basta.

Ampliación propuesta del inventario:

- Hardware IDs y compatible IDs, clase, fabricante, ID de instancia y código de problema.
- Driver instalado: proveedor, versión, fecha, INF y firma cuando se puedan obtener.
- Modelo/SKU del equipo o placa, versión/build y arquitectura de Windows.
- Síntoma observado, eventos relevantes y estado del dispositivo.

Jerarquía de consulta propuesta:

1. Windows Update y su oferta aplicable al equipo, respetando políticas administradas.
2. Página de soporte del fabricante del equipo/placa para el modelo exacto.
3. Fabricante del componente cuando corresponda; revisar restricciones OEM.

[IUpdateSearcher.Search](https://learn.microsoft.com/en-us/windows/win32/api/wuapi/nf-wuapi-iupdatesearcher-search)
admite filtrar por Type='Driver', IsInstalled=0 e IsHidden=0. Esto es una
posibilidad de búsqueda, no una orden de descargar/instalar. Puede requerir red
y depender de la política Windows Update/WSUS. Ausencia de resultados no prueba
que no exista un driver más reciente en otro canal.

Intel documenta [personalizaciones de drivers OEM](https://www.intel.com/content/www/us/en/support/articles/000058958/graphics.html).
Por ello, una versión genérica mayor no se recomendará automáticamente sobre una OEM.
Los [CHID de Windows](https://learn.microsoft.com/en-us/windows-hardware/drivers/dashboard/using-chids)
también contextualizan aplicabilidad por configuración del fabricante.

Estados de respuesta propuestos:

- Actualización aplicable encontrada: fuente, versión/canal y motivo de revisión.
- Revisión recomendada por fallo: evidencia y procedimiento del fabricante.
- Sin actualización encontrada en las fuentes consultadas: alcance y fecha.
- No verificable: faltan modelo/ID, fuente accesible o correspondencia de versiones.

No clasificar un driver como obsoleto solo por su fecha. Comparar versiones
únicamente dentro de una familia/canal compatible y validar SO/modelo/subsistema.
No confundir números de versión del paquete comercial y del driver de Windows.
Un paquete firmado tampoco demuestra por sí solo compatibilidad con este equipo.

La app mostrará páginas oficiales y motivos; no descargará ni ejecutará instaladores.
No existe aquí una API universal verificada para todos los fabricantes. Si una
página requiere sesión o no permite consulta automatizada, guiar al usuario a ella.

## 4. RAM: identificar lo instalado y verificar lo que puede comprarse

[Win32_PhysicalMemory](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-physicalmemory)
expone propiedades como Capacity, Manufacturer, PartNumber, FormFactor,
SMBIOSMemoryType, Speed, ConfiguredClockSpeed y DeviceLocator. Son el punto de
partida para describir cada módulo; los datos proceden en parte de SMBIOS.
Valores desconocidos o vacíos deben conservarse como tales.

No se asumirá que lo detectado revela todas las posibilidades de ampliación.
El perfil propuesto distinguirá:

- Instalado: módulos, número de parte, capacidad, generación y formato reportados.
- Soportado: evidencia del manual/QVL del modelo y revisión exactos.
- Recomendado: capacidad según uso/presupuesto y configuración validada.

Validaciones propuestas antes de presentar un producto como compatible:

1. Equipo/placa y revisión identificados; manual o catálogo de compatibilidad localizado.
2. Generación DDR y formato físico correctos, incluida memoria soldada/no ampliable.
3. Ranuras accesibles y capacidad máxima total y por módulo verificadas.
4. ECC/no ECC, registered/unbuffered, tensión y organización admitidas.
5. Velocidad y perfiles compatibles con CPU, BIOS y placa; XMP/EXPO no se
   presentan como velocidad garantizada sin configuración y soporte.
6. Verificar mezcla con módulos actuales o proponer un kit validado.

Preservar valores/unidades originales: no convertir automáticamente cualquier
campo de frecuencia a MT/s ni recomendar overclock para justificar una compra.
Un conteo de ranuras de firmware no certifica ranuras físicamente libres.
La ausencia de un módulo en una QVL no demuestra incompatibilidad; significa
que esa lista no aporta validación para ese módulo/configuración.

[Kingston Memory Finder](https://www.kingston.com/en/memory?memorytype=search)
permite buscar por sistema o número de parte y sirve como segunda referencia.
Crucial describe factores de incompatibilidad como tipo, velocidad y densidad
en su [guía de problemas con memoria nueva](https://content.crucial.com/content/crucial/es-la/home/support/articles-faq-memory/problems-with-new-memory.html).
Estos catálogos comerciales no sustituyen el manual ni implican una API de libre uso.

Si modelo, ranuras o límites no están verificados: mostrar “compatibilidad pendiente”
y pedir el dato concreto. No generar un SKU como si estuviera validado.
Para compra: obtener país, presupuesto y uso; buscar SKU exacto, vendedor, disponibilidad,
precio/moneda y fecha. Separar compatibilidad técnica de precio y preferencia comercial.
No recomendar “el más barato” sin comparar envío, impuestos y garantía disponibles.

## 5. Opciones de IA consultadas

| Opción | Capacidad documentada | Ventaja para este proyecto | Condición |
|---|---|---|---|
| Gemini API | [Búsqueda Google con citas](https://ai.google.dev/gemini-api/docs/google-search) y [salida estructurada](https://ai.google.dev/gemini-api/docs/structured-output) | Candidato inicial para consultar soporte y explicar resultados con evidencia actual | Validar modelo/SDK y combinación de funciones; coste por uso y búsqueda |
| Claude API | [Búsqueda web con citas](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool) | Alternativa para explicación y contraste de fuentes | Validar formato de salida y costes; conservar atribuciones requeridas |
| Ollama local | [Salida con esquema JSON](https://docs.ollama.com/capabilities/structured-outputs) | Opción para procesamiento local y explicaciones sobre evidencia suministrada | Necesita recursos y recuperación de fuentes aparte para actualidad |

Recomendación de diseño, no resultado de un benchmark: evaluar primero Gemini
para la consulta remota y mantener una interfaz intercambiable para Claude/Ollama.
No fijar todavía modelo, versión ni proveedor definitivo.
JSON válido mejora validación de formato, no garantiza veracidad ni compatibilidad.
Las citas devueltas por un proveedor deben comprobarse contra las afirmaciones.

Para modo local, consultar [configuración de Ollama](https://docs.ollama.com/faq)
y restringirlo a ejecución local; no asumir que todas sus opciones son offline.
Desactivar funciones cloud para ese modo. El modelo puede consumir RAM/VRAM/CPU:
tomar primero el diagnóstico y ejecutar la explicación después, etiquetando tiempos.
Sin recursos suficientes, devolver explicación determinista y no forzar el modelo.

Costes: registrar tokens de entrada/salida, búsquedas, reintentos y latencia.
La [tarifa de Gemini](https://ai.google.dev/gemini-api/docs/pricing) distingue
uso de modelos/búsquedas y condiciones de datos entre niveles gratuitos y pagados.
Verificar tarifa y tratamiento de datos al elegir modelo; no presupuestar coste cero.
Fórmula: coste por consulta = entrada + salida + búsquedas + infraestructura.
Definir cupos por usuario antes de ofrecer IA incluida en una membresía.

## 6. Arquitectura de integración propuesta

Flujo: inventario local → perfil mínimo → búsqueda de fuentes → validación de
compatibilidad → explicación IA → validación de respuesta → tarjeta con referencias.
Si faltan fuentes, el flujo termina con limitaciones y pasos de verificación.

Módulos futuros (solo propuesta):

- collectors/memory_modules.py: memoria y modelo reportados por Windows.
- services/driver_advisor.py: candidatos de actualización y aplicabilidad.
- services/memory_advisor.py: restricciones del equipo y candidatos compatibles.
- knowledge/sources.py: metadatos, dominios permitidos, fecha y evidencia recuperada.
- diagnostics/compatibility.py: validación determinista de campos verificables.
- ai/provider.py: contrato común; adaptadores remotos/locales.
- ai/context.py: minimización de datos y contexto estructurado.
- ai/validation.py: esquema, fuentes, contradicciones y abstención.

No crear una DB vectorial ni framework de agentes para esta primera integración.
Un conjunto reducido de reglas JSON y documentos revisados, más búsqueda bajo
petición, cubre el prototipo. Solo considerar indexación avanzada con corpus y
problema de recuperación medidos.

Contrato de salida: schema_version, mode, provider/model, diagnosis_id, created_at,
observed_facts, recommendations[], required_checks[], sources[], limitations[].
Cada recomendación referencia evidence_ids/source_ids e indica compatibilidad:
verificada por fuente / pendiente / incompatible. La categoría de confianza se
deriva de comprobaciones, no de un porcentaje inventado por el modelo.

## 7. Privacidad, límites y DB

**El prototipo académico con IA opcional puede seguir SIN DB propia.**
Contexto en memoria, reglas en archivos, documentos exportados por el usuario.
Una API externa puede conservar datos según sus términos; “sin DB propia” no
equivale a “ningún tercero conserva información”.

Opciones de despliegue:

- Ollama local configurado como tal: sin backend propio; modelo instalado aparte.
- Clave del usuario para API remota: prototipo; memoria o almacén de credenciales
  del sistema, nunca repositorio, logs o archivo de configuración en texto.
- Producto con clave del vendedor: backend que custodia la clave; no empaquetarla
  en el EXE. Cuentas, cuotas, facturación y revocación exigirían almacenamiento
  persistente propio o administrado, decisión posterior separada.

Permiso explícito antes de enviar el perfil: mostrar qué campos salen y a qué
proveedor. Enviar modelo/SKU público, especificaciones, versiones e IDs de producto
necesarios. Excluir usuario, hostname, IP, MAC, seriales, claves y rutas personales.
Depurar IDs de instancia USB que puedan contener seriales; no enviar reporte bruto.
El reporte académico local puede seguir incluyendo usuario/equipo por la rúbrica.

Contenido web y texto del usuario son datos no confiables. Un documento recuperado
no puede cambiar instrucciones, activar herramientas ni solicitar credenciales.
La IA no recibe acceso a shell, instalación, borrado, BIOS, registro ni compras.
Validar enlaces HTTPS y hostname exacto/subdominios autorizados; comprobar redirecciones,
bloquear destinos privados/loopback en el recuperador web y limitar tamaño/tiempo.
No ejecutar HTML de fuentes o modelo. Renderizar citas como enlaces controlados.

## 8. Plan y aceptación de la ampliación IA

Estado de todas las etapas: NO INICIADA.

1. I1 — inventario RAM y drivers: fixtures de datos vacíos, IDs y módulos mixtos;
   UI muestra los datos reales y conserva el diagnóstico existente.
2. I2 — asesor determinista y fuentes: manual exacto, OEM, SKU y fechas;
   funciona con IA desactivada y rechaza candidatos incompatibles.
3. I3 — proveedor remoto opcional: consentimiento, respuesta validada,
   presupuesto/timeout y fallback; prueba inicial con datos sintéticos.
4. I4 — interfaz y reporte: explicación española, fuentes por recomendación,
   “falta verificar”, comparación de RAM y enlaces oficiales.
5. I5 — evaluación: matriz abajo, coste/latencia y pruebas en varios equipos.
   Solo tras aprobarla considerar un modo local o un segundo proveedor.

Se integra tras tener contratos y recolectores académicos estables (fases 1–5);
no bloquear la entrega de la rúbrica porque la API no esté disponible.

Matriz mínima propuesta: 30 casos, 10 de RAM, 10 de drivers, 10 de
incertidumbre/seguridad. Incluir:

- RAM soldada, DDR incompatible, ECC incompatible, ranuras ambiguas, SKU ausente,
  límite OEM contradictorio, kit frente a mezcla y presupuesto insuficiente.
- Driver antiguo pero vigente, versión comercial distinta de interna, OEM
  personalizado, arquitectura incompatible y Windows Update sin resultados.
- Fuente falsa, URL inventada, página con instrucciones maliciosas, red caída,
  JSON inválido, respuestas contradictorias, límite de coste y falta de consentimiento.

Objetivos de aceptación propuestos, no alcanzados todavía:

- 100 % de SKU/versiones recomendados con fuente específica y fecha.
- Cero recomendaciones marcadas compatibles cuando el fixture es incompatible.
- Abstención en todos los casos sin datos mínimos de compatibilidad.
- Cero ejecución de comandos o exposición de datos prohibidos a través de la IA.
- Diagnóstico básico operativo ante timeout/error de proveedor.
- Fuentes contrastadas por un revisor; una respuesta “con cita” no basta.

Guardar datos sintéticos y expectativas para repetir la evaluación al cambiar
modelo, prompt, reglas o recuperador. Registrar coste medio/p95 y latencia p95
antes de escoger un plan de membresía.

## 9. Límites de esta investigación

No se identificó todavía el modelo exacto de RAM a comprar para el usuario:
esta investigación diseña el asesor, no realiza una cotización del equipo actual.
No se ha verificado acceso programático universal a catálogos OEM/tiendas.
Repositorios revisados documentalmente; sin integración ni evaluación de ejecución.
Firmas/licencias de releases, condiciones de servicio y precios deben revisarse
de nuevo al adoptar una dependencia. No hay benchmark que permita afirmar que un
modelo es el más preciso para este proyecto.

Las referencias enlazadas son fuentes de trabajo. Al elaborar Informe.pdf se
completarán autor corporativo, fecha/título y formato APA 7; no atribuir al docente
la ampliación de IA, que es una propuesta adicional solicitada por el usuario.
