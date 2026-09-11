# Instrucciones canónicas para completar el proyecto

Fecha: 2026-09-05. Destinatario: cualquier agente de implementación, incluido
Antigravity. Este documento es obligatorio antes de abrir, crear o renombrar una
fase. Su objetivo es preservar el alcance del ingeniero, el código estable y las
ampliaciones de producto ya aprobadas.

## Autoridad y regla contra fases inventadas

1. **No crear, renombrar, dividir, fusionar ni reordenar fases.** Usar solamente
   los IDs existentes: fases comerciales `F0`–`F9` de
   [COMMERCIAL_ROADMAP.md](COMMERCIAL_ROADMAP.md), asesor `E1`–`E8` de
   [09-diagnostic-advisor.md](architecture/09-diagnostic-advisor.md), e IA
   `I1`–`I5` de [RESEARCH_AI_HARDWARE.md](RESEARCH_AI_HARDWARE.md).
2. Las fases 1–7 de [BUILD_PLAN.md](../BUILD_PLAN.md) ya están completadas y
   son la línea base; no se reimplementan ni se convierten en fases nuevas.
3. Si surge una idea no cubierta, registrarla como **CANDIDATO DE BACKLOG** con
   motivo, impacto, archivos previsibles, riesgos y dependencia. No escribir
   código ni crear una fase para ella hasta que el propietario lo autorice.
4. Si un requerimiento cabe dentro de una fase existente, anexarlo a esa fase y
   actualizar su aceptación/pruebas. Los requisitos del ingeniero se conservan;
   las mejoras comerciales los complementan, nunca los sustituyen.
5. No marcar `COMPLETADA` porque exista una carpeta, una maqueta, un mock o una
   prueba aislada. Sólo hacerlo cuando se cumpla toda la aceptación de la fase,
   las puertas obligatorias y la evidencia real requerida. Usar `PARCIAL` o
   `NEEDS_USER_VERIFICATION` cuando corresponda.

## Estado inicial protegido

- Código funcional: fases 1–7 de `BUILD_PLAN.md`.
- Validación automatizada actual: 179 pruebas pasadas, 8 omitidas por sesión Tk;
  ruff y mypy pasan. Repetir antes y después de cada fase.
- Verificación humana pendiente: protocolo PR-01…PR-18 y EXE en una segunda
  máquina Windows limpia. Son V-01 y V-02, no fases nuevas.
- Sin DB local/remota propia. No añadir SQLite, ORM, vector DB, servidor, cuentas
  ni telemetría remota sin decisión explícita del propietario.
- La app es diagnóstica y de solo lectura. No instalar drivers, modificar BIOS,
  reparar discos, ejecutar comandos libres, comprar componentes ni elevar
  privilegios automáticamente.

Antes de empezar: leer este documento, `BUILD_PLAN.md`,
`docs/PRODUCT_REQUIREMENTS.md`, el documento propio de la fase y
`docs/architecture/10-project-review-2026-09-05.md`; ejecutar pruebas/lint/tipado
y registrar el resultado. Corregir la colisión de `.pytest_cache` sin ocultar o
desactivar la caché, y repetir las puertas.

## Secuencia obligatoria

| Orden | ID existente | Resultado que debe completar | No hacer todavía |
|---:|---|---|---|
| 0 | V-01, V-02 | Ejecutar PR-01…PR-18 y probar EXE/ZIP en equipo limpio; documentar PASS/FAIL/NEEDS_USER_VERIFICATION | Declarar compatibilidad universal |
| 1 | F0–F1 comercial | Congelar referencia comercial, compatibilidad de contratos, calidad de evidencia, confianza y resultados `NOT_SUPPORTED`/cancelados | Romper reportes o contratos existentes |
| 2 | F2 comercial | SMART/NVMe, batería/energía, firmware/placa/TPM/Secure Boot, módulos RAM y periféricos/pantallas | Interpretar sensor/campo ausente como sano |
| 3 | F3 comercial | Sensores térmicos, ventiladores, voltajes y throttling mediante adaptador reemplazable | Instalar sensores/servicios o elevar permisos automáticamente |
| 4 | F4 comercial | Latencia/pérdida/Wi-Fi, eventos WHEA/disco/driver/BSOD y revisión de driver por dispositivo | Concluir causa por un evento 41 o fecha de driver aislada |
| 5 | F5 comercial | Motor multimuestreo, correlaciones, confianza explicable y falsa-alarma controlada | Pruebas activas de carga |
| 6 | F6 comercial | Pruebas opcionales CPU/RAM/disco/GPU, límites, cancelación, limpieza; diagnóstico Windows de memoria sólo con consentimiento | Estrés no cancelable, overclock, firmware o borrados |
| 7 | F7 comercial | PDF, vistas básica/técnica y reportes con duración, cobertura, límites y evidencias | Historial automático o DB |
| 8 | F8–F9 comercial | Instalador, firma, actualización segura, licencias, matriz Windows/hardware y lanzamiento | Declarar producto comercial sin gates |
| 9 | E1–E8 | Guía, asesores RAM/GPU/SSD, comparación/redacción, rendimiento por sesión y prioridad de compra | API IA, claves o compra automática |
| 10 | I1–I5 | Inventario/fuentes, reglas, proveedor IA opcional, UI/reporte y evaluación | Enviar datos sin consentimiento o incrustar clave del vendedor |

E1–E8 se implementan respetando sus dependencias escritas: E1, E2, E3, E4,
E5, E6, E7, E8. No adelantar E5 sin la evidencia de sensores/F3 y monitoreo
estable; no adelantar E2/E4/I2 sin fuentes de modelo/SKU verificables.

Excepción registrada: el propietario autorizó el 2026-09-11 una integración
local **PARCIAL** de E2/E4/E7/E8 para orientar comprobaciones sin compras. No
altera la dependencia para declarar estos slices completos: usa sólo inventario
de la sesión y datos documentales introducidos por el usuario, marca datos
ausentes como `PENDIENTE DE VERIFICACIÓN` y conserva pendientes fuentes OEM,
SKU, validación física y los gates de aceptación completos.

## Procedimiento obligatorio por fase

1. Declarar el ID de fase exacto y repetir su alcance, fuera de alcance,
   dependencia y criterios de aceptación desde su documento canónico.
2. Inspeccionar los módulos y pruebas afectados; preservar cambios del usuario.
3. Diseñar un único slice vertical: contrato/dominio → recolector o servicio →
   regla → UI → reporte → prueba. No dejar directorios, botones o dependencias
   vacíos para “después”.
4. Usar consultas Windows de allowlist, `shell=False`, timeout, cancelación y
   resultados explícitos `ERROR`/`NOT_SUPPORTED` para permisos, sensores o
   hardware no disponibles. Nunca tratar ausencia de dato como salud.
5. Para toda dependencia nueva: validar upstream, versión, licencia, terceros,
   Windows objetivo, empaquetado PyInstaller, cancelación y pruebas. Justificarla
   en documentación antes de agregarla al lockfile.
6. Añadir tests de regla/contrato, fixtures normal/ausente/permiso/fallo y una
   integración proporcionada por Windows cuando aplique. Para acciones activas,
   probar cancelación, timeout, limpieza y cierre de ventana.
7. Ejecutar `pytest -q`, `ruff check .`, `mypy`, y el build cuando cambie el
   artefacto. No reducir asserts, saltar gates ni sustituir resultados reales
   por mocks para declarar éxito.
8. Actualizar `PRODUCT_REQUIREMENTS.md`, el documento de la fase, `BUILD_PLAN.md`,
   guía/notas de versión y la revisión de arquitectura. Indicar evidencia, fecha,
   riesgos y recuperación. Sólo entonces actualizar el estado de la fase.

## Mapa de requisitos que debe preservarse

- El enunciado original está cubierto por P01–P12 y sus casos C1–C5: conservar
  interfaz, CPU/RAM, discos, red, USB, PCI/PCIe, GPU, drivers, motor, reportes,
  ejecutable y ausencia de DB.
- P13–P28 no se eliminan ni se renombran: IA opcional, RAM, drivers OEM, guía,
  compra responsable, comparación, privacidad, GPU, refresco, SSD y prioridad.
- F2–F7 comercial incorpora diagnóstico profundo: SMART, batería, BIOS/UEFI,
  TPM/Secure Boot, sensores, red/eventos, multimuesta, pruebas seguras y PDF.
- F8–F9 incorporan el trabajo necesario para distribución comercial; no confundir
  el ZIP actual con instalador firmado, actualización segura o activación.

## Límites de datos, IA y seguridad

- Reportes: sólo por acción del usuario. Antes de compartir, depurar usuario,
  hostname, seriales, IP/MAC, rutas y claves; mantener el original intacto.
- IA: usarla sólo en I3, tras consentimiento y perfil mínimo. Reglas y fuentes
  verificables deciden compatibilidad; la IA explica y debe poder abstenerse.
- Claves: nunca dentro del EXE, repositorio, logs o JSON. API comercial del
  vendedor implica backend/custodia y una decisión de persistencia futura.
- Temperatura, SMART, voltaje, VRAM, eventos y compatibilidad no son universales:
  mostrar fuente, momento, unidad y cobertura. Ante incertidumbre, explicar la
  comprobación faltante y cuándo acudir a un técnico.

## Cierre, rollback y comunicación

Al finalizar cada fase, informar: ID, archivos modificados, pruebas ejecutadas y
resultado, evidencia física pendiente, dependencia agregada/licencia, riesgo
residual y rollback. Crear un commit recuperable sólo cuando el propietario lo
solicite o el flujo de trabajo lo requiera. Si una prueba no puede ejecutarse,
usar `NOT_RUN_ENV_LIMITATION` o `NEEDS_USER_VERIFICATION`; nunca `PASS` sin
evidencia.

La única forma de cambiar esta secuencia, introducir una fase o adoptar DB/nube
es una instrucción explícita del propietario y una actualización coordinada de
este documento, `BUILD_PLAN.md`, requisitos y ADR correspondiente.
