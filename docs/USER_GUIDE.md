# Guía de uso — Administrador de Hardware

Versión 0.1.0. Aplicación local de diagnóstico de hardware para Windows.

Esta guía cubre instalación, uso, desinstalación, política de datos y solución
de problemas. Las limitaciones conocidas están en [CHANGELOG.md](../CHANGELOG.md).

---

## 1. Qué hace y qué no hace

**Hace:** consulta el estado de once áreas del equipo, clasifica lo que
encuentra, explica la causa probable y propone procedimientos correctivos con
sus pasos, su fundamento y cómo comprobar después si se resolvió.

**No hace:** no repara. Cuando un procedimiento modifica el sistema —renovar la
concesión DHCP, vaciar la caché DNS, reinstalar un controlador—, el programa lo
describe y lo marca, pero lo aplica usted. Tampoco eleva privilegios ni envía
nada a ningún servidor.

> **Lo más importante de esta guía:** que el análisis no encuentre anomalías
> **no** significa que el hardware esté libre de fallas. Significa que los
> indicadores consultados en ese momento no mostraron anomalías. Un fallo de
> consulta, un permiso denegado o una prueba omitida tampoco equivalen a un
> componente sano.

## 2. Requisitos

- Windows 10 o 11 de 64 bits.
- PowerShell disponible (viene con el sistema).
- No necesita instalar Python: el ejecutable lo incluye.
- Algunas consultas ofrecen más detalle si ejecuta el programa como
  administrador. Sin ese permiso la sección afectada se reporta como error de
  consulta, no como componente correcto.

## 3. Instalación

1. Descomprima `HardwareDiagnostic-0.1.0-windows-x64.zip` en una carpeta con
   permiso de escritura, por ejemplo el Escritorio o `C:\Herramientas`.
2. Abra la carpeta `HardwareDiagnostic`.
3. Ejecute `HardwareDiagnostic.exe`.

No hay instalador ni entradas en el registro: el programa es portátil.

Si Windows SmartScreen muestra un aviso, es porque el ejecutable no está
firmado digitalmente. La firma de código está prevista en la hoja de ruta
comercial y no forma parte de esta versión.

## 4. Uso

### Análisis

- **ANALIZAR EQUIPO** recorre las once áreas. Tarda unos segundos: la CPU y la
  E/S necesitan una ventana de medición real.
- El botón de la derecha analiza **sólo la sección** que tenga seleccionada.
- **Síntoma observado (opcional):** describa lo que nota, por ejemplo «se
  reinicia al jugar». Si el análisis no encuentra anomalías pero usted reporta
  un síntoma, el programa insistirá en ampliar el diagnóstico en vez de dar el
  equipo por sano. El texto se trata como dato: nunca se ejecuta ni se
  interpola en ningún comando.

### El menú

| Nº | Apartado | Qué muestra |
|---|---|---|
| 1 | Diagnóstico general | Sistema operativo, arquitectura y equipo |
| 2–3 | CPU, RAM | Medidor de uso, núcleos y asignación de memoria |
| 4–6 | PCI/PCIe, Red, USB | Dispositivos, identificadores y estado |
| 7 | Almacenamiento | Ocupación por unidad, tipo de medio y salud |
| 8–10 | GPU/vídeo, Controladores, Dispositivos con problemas | Identidad y códigos de error |
| 11 | Conectividad | Pruebas escalonadas: adaptador, IP, puerta de enlace, acceso externo y DNS |
| 12 | Monitorización | Gráficos de E/S en vivo con Iniciar, Detener y Limpiar |
| 13 | Recomendaciones | Todos los procedimientos propuestos, por gravedad |
| 14 | Exportar diagnóstico | Muestra la vista previa del reporte completo y, al pulsar «Exportar», lo guarda en disco |
| 0 | Avanzado | Estado inmediato de batería y funciones avanzadas |

### Monitorización

Pulse **Iniciar** para empezar a muestrear cada segundo. El gráfico de disco y
el de red tienen escalas independientes, porque sus tasas suelen diferir en
órdenes de magnitud. **Detener** conserva lo capturado para que pueda leerlo;
**Limpiar** lo descarta. El buffer guarda 300 muestras: al llenarse descarta las
más antiguas.

El muestreo **no** arranca solo. Nada se ejecuta en segundo plano si usted no
lo pide.

### Exportar

La opción 15 pregunta primero si desea incluir el nombre del equipo y del
usuario. Responda **No** para obtener una copia anónima, apta para compartir:
el resto del contenido es idéntico.

El formato se elige por la extensión del archivo:

| Extensión | Uso |
|---|---|
| `.html` | Lectura en navegador, con la evidencia técnica plegada |
| `.json` | Procesamiento automático; incluye `schema_version` |
| `.txt` | Lectura sin herramientas, para adjuntar en un correo |

## 5. Política de datos

- **Todo es local.** No hay telemetría, ni servidor, ni base de datos.
- Los reportes se escriben **sólo** cuando usted los exporta, en la ruta que
  elija.
- Los registros técnicos de la aplicación se guardan en
  `%LOCALAPPDATA%\AdministradorHardware\logs\app.log`, rotan al llegar a 256 KB
  y conservan dos copias. Registran qué consulta se ejecutó y cuánto tardó; no
  guardan direcciones IP, MAC ni nombres de usuario.
- Un reporte exportado **con** identidad contiene el nombre del equipo, el del
  usuario, direcciones IP y MAC de los adaptadores e identificadores de
  dispositivo. Téngalo en cuenta antes de compartirlo: para eso existe la copia
  anónima.

## 6. Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Una sección dice «Error de consulta» | Permisos insuficientes o servicio de Windows detenido | Cierre y ejecute como administrador; repita el análisis de esa sección |
| SmartScreen bloquea el ejecutable | El binario no está firmado | «Más información» → «Ejecutar de todas formas», si confía en el origen |
| El análisis tarda más de lo normal | Consultas PowerShell lentas por número de dispositivos | Espere; cada consulta tiene un límite de 15 segundos y devuelve resultados parciales |
| Los gráficos aparecen vacíos | Todavía no ha analizado esa sección | Ejecute el análisis; los gráficos leen lo último analizado |
| El gráfico de E/S no se mueve | No hay actividad de disco o red | Copie un archivo grande para generar tráfico real |
| El reporte no se guarda | Carpeta sin permiso de escritura | Elija otra ubicación, por ejemplo su carpeta de Documentos |
| La ventana no abre | Falta el runtime de Visual C++ o el ZIP se descomprimió a medias | Vuelva a descomprimir el paquete completo |

Si un problema persiste, exporte el reporte en `.txt` y adjúntelo al describir
la incidencia: contiene la cobertura del análisis y las consultas que fallaron.

## 7. Desinstalación

1. Cierre la aplicación con la opción **0. Salir**.
2. Borre la carpeta `HardwareDiagnostic`.
3. Opcionalmente, borre los registros en
   `%LOCALAPPDATA%\AdministradorHardware`.

No quedan servicios, tareas programadas ni entradas de registro.

## 8. Soporte

Este es un proyecto académico y personal. Las incidencias se registran en el
repositorio del proyecto. Al reportar una, incluya:

1. La versión que aparece en el reporte (`0.1.0`) y el `schema_version`.
2. El reporte exportado en `.txt`, preferentemente la copia anónima.
3. Qué esperaba que ocurriera y qué ocurrió.
4. Si ejecutó el programa como administrador.

## 9. Referencias técnicas

Los criterios de diagnóstico se apoyan en la documentación oficial de los
fabricantes y de Microsoft. Las fuentes consultadas, con sus fechas, están en
[RESEARCH_AI_HARDWARE.md](RESEARCH_AI_HARDWARE.md) y en las decisiones de
arquitectura de [docs/architecture](architecture/).

Los umbrales de clasificación son una **política del proyecto** para señalar
carga y ocupación, no una prueba de daño físico. Están documentados y probados
en `tests/test_rules.py`.
