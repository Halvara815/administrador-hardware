# Notas de versión

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Las versiones se numeran según [SemVer](https://semver.org/lang/es/).

## [0.1.0] — 2026-09-05

Primera versión funcional completa: diagnóstico, monitorización, gráficos,
recomendaciones y exportación.

### Añadido

**Diagnóstico (fases 1–3)**

- Clasificación central por umbrales: CPU normal ≤70 %, advertencia >70 % y
  crítico ≥90 %; RAM advertencia desde 70 %; disco 85 % / 95 %. La regla es
  continua y cubre valores decimales sin huecos.
- Once áreas: sistema, CPU, RAM, discos, red, USB, PCI/PCIe, controladores,
  dispositivos con problemas, GPU/vídeo y E/S.
- Consultas nativas por catálogo cerrado: PowerShell con JSON, y `ipconfig`,
  `ping`, `nslookup` y `arp` con argumentos validados y `shell=False`.
- Conectividad escalonada: adaptador → IP → puerta de enlace → acceso externo
  → DNS, con detección de APIPA (169.254.x.x) y de fallo de resolución.
- Asociación de discos y volúmenes mediante `Get-Disk`/`Get-Partition`, por la
  relación que reporta Windows y no por coincidencia de nombres.
- Casos integradores documentados: CPU, RAM, disco, DNS, C1–C5, USB ausente,
  USB con error y USB sano sin volumen.

**Monitorización y gráficos (fase 4)**

- Muestreo periódico de E/S con buffer de 300 muestras, arranque y parada
  explícitos, y dos gráficos de series de tiempo con escala independiente.
- Medidor de uso y barras por núcleo lógico en CPU; asignación de capacidad en
  RAM; ocupación por unidad en discos; velocidad de enlace por adaptador.
- Recomendaciones estructuradas con causa, pasos ordenados, fundamento,
  comprobación posterior y aviso de si el procedimiento modifica el sistema.
- Menú de 15 apartados más Salir, con pantallas propias de Conectividad y
  Recomendaciones, y cierre ordenado que detiene el muestreo.

**Exportación (fase 5)**

- Reportes HTML, JSON y TXT en UTF-8. El JSON lleva `schema_version` 1.0.
- Opción de omitir el nombre del equipo y del usuario para compartir la copia.

### Limitaciones conocidas

- **La ausencia de anomalías no equivale a hardware sin fallas.** El programa
  informa sobre los indicadores que pudo consultar en ese momento.
- No mide temperatura ni voltajes: requieren sensores y controladores
  específicos que no están disponibles de forma homogénea en todos los equipos.
- La memoria de vídeo que informa WMI no representa la VRAM exacta garantizada.
- Los catálogos de dispositivos están limitados a 100 entradas y el de
  controladores a 150. Un equipo con más dispositivos mostrará un subconjunto.
- Un `ping` sin respuesta puede reflejar ICMP bloqueado: el resultado no es
  concluyente sin pruebas complementarias.
- `arp -a` sólo muestra vecinos ya conocidos, no todos los equipos de la red.
- Algunas consultas requieren permisos de administrador. Sin ellos, la sección
  se reporta como error de consulta y **no** como componente sano.
- El programa **no repara**: propone procedimientos y los marca cuando alteran
  el sistema, pero nunca los ejecuta.
- Sin base de datos ni telemetría: los reportes se guardan sólo si usted los
  exporta explícitamente.

### Pendiente

Detallado por fases en el [trabajo pendiente](README.md#trabajo-pendiente).
Las fases 8 (validación del JSON) y 9 (pruebas de los controles
declarados y registro de exportaciones) ya están completadas.

- **Fase 10:** límite total de escaneo de 60 s, presupuesto de red de 30 s e
  identificador de sesión en los registros.
- **Fase 11:** escalado 100/125/150 %, escaneo de dependencias, protocolo de
  pruebas reales y validación en equipo limpio.
- Asesoría de compra y ampliación (slices E1–E8) e integración de IA (I1–I5),
  diseñadas y no iniciadas; no son requisito del enunciado.
