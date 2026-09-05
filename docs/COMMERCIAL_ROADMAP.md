# Archivo de la hoja de ruta comercial

Estado: DIFERIDA. El plan de producto vigente está en [BUILD_PLAN.md](../BUILD_PLAN.md).
Las suscripciones solo se discutieron; no hay decisión de implementar pagos ni cuentas.
Las estimaciones siguientes son preliminares, no compromisos ni evidencia de trabajo terminado.

La ampliación RAM/GPU y la solución guiada tienen planificación vigente en
[09-diagnostic-advisor.md](architecture/09-diagnostic-advisor.md), slices E1–E8,
todos pendientes. Esa planificación prevalece sobre estimaciones históricas de
este archivo para esas funciones; no cambia el estado de las fases base ni
autoriza implementación. IA remota opcional con consentimiento no equivale a
cuentas/nube obligatoria. El núcleo y estas ampliaciones siguen sin DB propia.

# Plan de evolución: Administrador de Hardware comercial

## Estado y propósito

- Producto actual: `v0.1.0`, funcional y verificado para entrega inicial en Windows.
- Objetivo futuro: `v1.0.0`, herramienta local de diagnóstico confiable para usuarios y técnicos.
- Estado de la evolución comercial: **PLANIFICADA — NO INICIADA**.
- Restricción principal: preservar el comportamiento que ya funciona.
- Arquitectura: monolito modular de escritorio, un proceso y sin servicios obligatorios.
- Plataformas iniciales: Windows 10 y Windows 11 de 64 bits.

Este documento define el trabajo futuro. No declara como implementada ninguna capacidad
comercial y no autoriza cambios en el código actual hasta iniciar formalmente una fase.

## Decisión sobre base de datos

**La versión comercial 1.x NO usará base de datos.**

Razones:

- El diagnóstico ocurre en un solo equipo y no necesita consultas históricas para funcionar.
- Evita migraciones, corrupción de almacenamiento, respaldos y recuperación innecesarios.
- Reduce superficie de ataque, mantenimiento y problemas de privacidad.
- Permite que la aplicación siga funcionando sin Internet.
- Mantiene la distribución y el soporte técnico simples.

Persistencia permitida sin DB:

- Preferencias no sensibles en un archivo de configuración local.
- Reportes HTML, PDF o JSON únicamente cuando el usuario los exporte.
- Licencia comercial mediante un archivo firmado y verificable localmente, si se implementa.
- Manifiesto HTTPS firmado para comprobar actualizaciones, sin enviar el diagnóstico.

No se guardará automáticamente historial de diagnósticos ni evidencia técnica. La decisión
se revisará para una versión futura únicamente si aparece un requisito confirmado de cuentas,
suscripciones en línea, inventario centralizado, historial consultable o múltiples equipos.

## Línea base protegida

Las siguientes capacidades existentes se consideran la línea base y deben conservarse:

- Ventana gráfica sin consola externa.
- Navegación por los 15 apartados del proyecto más Salir.
- Análisis completo o por sección sin bloquear la interfaz.
- Recolección de sistema, CPU, RAM, discos, red, USB, PCI/PCIe, controladores,
  dispositivos con problemas, monitor/GPU y E/S.
- Evidencia técnica de solo lectura.
- Matriz de estados, conclusión y reporte HTML.
- Consultas PowerShell cerradas, con timeout y sin comandos escritos por el usuario.
- Fallos parciales aislados: un recolector no debe cancelar los demás.
- Build reproducible, pruebas, lint, tipado y empaquetado con PyInstaller.

Reglas de protección durante la evolución:

1. Crear una rama por fase y mantener `main` ejecutable.
2. Añadir primero pruebas que documenten el comportamiento que se conservará.
3. Extender contratos con campos opcionales; no romper reportes ni recolectores actuales.
4. Integrar cada capacidad verticalmente: recolección, diagnóstico, UI, reporte y pruebas.
5. No sustituir módulos estables si una extensión aislada resuelve la necesidad.
6. No ejecutar pruebas destructivas ni cambios del sistema sin consentimiento explícito.
7. Si una fase falla, revertir solo esa fase y conservar el último artefacto verificado.

## Arquitectura objetivo

Se mantendrán los límites actuales:

- `collectors`: obtiene mediciones de solo lectura.
- `diagnostics`: interpreta evidencia mediante reglas deterministas y explicables.
- `services`: coordina mediciones, cancelación, progreso y límites de tiempo.
- `domain`: contiene contratos y estados independientes de la interfaz.
- `infrastructure`: encapsula Windows, PowerShell, sensores y sistema de archivos.
- `reports`: genera entregables sin almacenar un historial interno.
- `ui`: presenta resultados y nunca ejecuta consultas del sistema directamente.

Los nombres de nuevos archivos se decidirán al iniciar cada fase. No se crearán capas,
servicios remotos ni dependencias antes de demostrar que son necesarias.

## Fase 0: congelar y proteger la versión actual

Estado: **NO INICIADA**.

Objetivo: convertir `v0.1.0` en una referencia recuperable antes de agregar funciones.

Pasos:

1. Actualizar la evidencia de pruebas y la trazabilidad real.
2. Ejecutar pruebas, lint, tipado, auditoría de dependencias y build limpio.
3. Verificar arranque y análisis completo desde el ejecutable.
4. Crear el tag `v0.1.0-baseline` y conservar su hash SHA-256.
5. Definir fixtures de resultados actuales para detectar regresiones.

Criterio de aceptación: la línea base puede restaurarse y produce el mismo resultado funcional.

Rollback: volver al tag inicial; no modificar reportes creados por el usuario.

Estimación: 1–2 horas.

## Fase 1: contratos de diagnóstico profesional

Estado: **NO INICIADA**.

Objetivo: preparar contratos compatibles para mediciones más profundas.

Capacidades:

- Severidad separada de disponibilidad de la medición.
- Confianza del diagnóstico: baja, media o alta.
- Duración, unidad, valor numérico y rango esperado por medición.
- Recomendaciones vinculadas a evidencia concreta.
- Estados `PASS`, `WARNING`, `CRITICAL`, `ERROR`, `NOT_SUPPORTED` y `CANCELLED`.
- Identificación explícita de pruebas omitidas por permisos o hardware incompatible.

Pruebas:

- Compatibilidad con los resultados y reportes existentes.
- Serialización segura de caracteres y valores desconocidos.
- Ninguna conclusión sin evidencia asociada.

Criterio de aceptación: el reporte actual continúa funcionando y admite nuevos resultados.

Rollback: conservar los campos nuevos como opcionales o revertir únicamente sus consumidores.

Estimación: 1–2 horas.

## Fase 2: almacenamiento, batería y firmware

Estado: **NO INICIADA**.

Objetivo: pasar de inventario básico a salud física consultable.

Capacidades:

- SMART/NVMe cuando Windows y el dispositivo lo expongan.
- Estado, temperatura, vida útil estimada y contadores críticos de SSD/HDD.
- Capacidad, tipo de medio, bus, firmware y errores reportados.
- Batería: capacidad de diseño, capacidad actual, desgaste y ciclos disponibles.
- BIOS/UEFI, placa base, TPM y Secure Boot como información diagnóstica.

Seguridad:

- Consultas de solo lectura y allowlist cerrada.
- No ejecutar reparación de disco, actualización de firmware ni borrado seguro.
- Mostrar `NOT_SUPPORTED` cuando el fabricante no exponga una métrica.

Pruebas:

- Fixtures SATA, NVMe, equipo sin SMART y equipo sin batería.
- Valores ausentes o informados con unidades diferentes.
- Integración real sin asumir que todos los discos soportan las mismas propiedades.

Criterio de aceptación: nunca se presenta como saludable una unidad cuya salud no pudo leerse.

Rollback: desactivar cada recolector nuevo de forma independiente.

Estimación: 2–4 horas.

## Fase 3: sensores y comportamiento térmico

Estado: **NO INICIADA**.

Objetivo: medir temperatura, carga, frecuencia y posibles límites térmicos.

Pasos previos obligatorios:

1. Evaluar APIs nativas y proveedores de sensores compatibles.
2. Revisar licencia, mantenimiento, firma y arquitectura soportada de cada dependencia.
3. Elegir un proveedor reemplazable detrás de una interfaz interna.

Capacidades:

- Temperaturas disponibles de CPU, GPU y almacenamiento.
- Carga y frecuencia sostenidas en varias muestras.
- Ventiladores y voltajes únicamente cuando el hardware los exponga de forma confiable.
- Detección explicable de posible sobrecalentamiento o thermal throttling.

Pruebas:

- Sensores ausentes, nombres variables, valores imposibles y permisos insuficientes.
- Intel, AMD y, cuando corresponda, GPU Intel, NVIDIA y AMD.
- Cancelación y timeout de la lectura.

Criterio de aceptación: ninguna temperatura inventada y ningún sensor ausente interpretado como sano.

Rollback: volver al proveedor nulo y mostrar la capacidad como no compatible.

Estimación: 3–6 horas más validación en hardware diferente.

## Fase 4: red y eventos críticos de Windows

Estado: **NO INICIADA**.

Objetivo: distinguir adaptador activo, red local funcional y acceso a Internet.

Capacidades:

- Comprobación separada de gateway, DNS y conectividad externa.
- Latencia, pérdida de paquetes y estadísticas de interfaz.
- Intensidad de Wi-Fi cuando esté disponible.
- Eventos recientes WHEA, errores de disco, fallos de controlador y reinicios inesperados.
- Ventana temporal visible para evitar conclusiones basadas en eventos antiguos.

Seguridad y privacidad:

- Destinos de prueba documentados y timeout corto.
- No transmitir inventario, nombres de dispositivos ni evidencia del usuario.
- Permitir omitir pruebas que requieren Internet.

Criterio de aceptación: el reporte diferencia claramente red local, DNS e Internet.

Rollback: las pruebas externas son opcionales y no afectan el diagnóstico local.

Estimación: 2–4 horas.

## Fase 5: motor de diagnóstico multimuestreo

Estado: **NO INICIADA**.

Objetivo: reducir falsos positivos y producir recomendaciones útiles.

Capacidades:

- Varias muestras de CPU, RAM, disco, red y sensores durante un intervalo visible.
- Reglas por combinación de señales, no por una sola lectura instantánea.
- Confianza calculada según cantidad y calidad de evidencia.
- Diferenciación entre síntoma, causa probable y limitación de medición.
- Recomendaciones seguras y ordenadas por impacto.

Ejemplo de correlación futura:

```text
Temperatura alta + frecuencia reducida + carga sostenida
=> posible limitación térmica, confianza alta.
```

Pruebas:

- Escenarios normales, transitorios, críticos y mediciones incompletas.
- Casos de regresión para evitar que una carga breve se marque como daño físico.
- Cada recomendación debe tener al menos una evidencia trazable.

Criterio de aceptación: las conclusiones explican qué se observó, qué significa y qué hacer.

Rollback: conservar el motor actual como implementación compatible durante la transición.

Estimación: 3–5 horas.

## Fase 6: pruebas activas seguras

Estado: **NO INICIADA**.

Objetivo: agregar pruebas cortas de CPU, RAM, disco y GPU sin arriesgar el equipo.

Controles obligatorios:

- Ejecución opcional con explicación previa.
- Duración máxima definida y cuenta regresiva visible.
- Cancelación inmediata desde la interfaz.
- Límites térmicos y de recursos; interrupción ante una señal peligrosa.
- Espacio temporal limitado, ruta validada y limpieza garantizada.
- No ejecutar pruebas destructivas, firmware, overclock ni reparación automática.

Pruebas:

- Cancelación, timeout, falta de espacio y cierre inesperado.
- Limpieza de archivos temporales.
- Comportamiento sin sensores térmicos disponibles.
- La prueba no debe bloquear la UI ni modificar archivos del usuario.

Criterio de aceptación: todas las pruebas pueden detenerse y dejan el sistema sin cambios persistentes.

Rollback: feature flag local; la aplicación conserva el diagnóstico pasivo.

Estimación: 4–8 horas más pruebas controladas.

## Fase 7: reportes y experiencia de usuario

Estado: **NO INICIADA**.

Objetivo: convertir resultados técnicos en un entregable comprensible.

Capacidades:

- Resumen ejecutivo y problemas ordenados por gravedad.
- Evidencia, confianza, limitaciones y recomendaciones por componente.
- Exportación HTML, PDF y JSON por acción explícita.
- Aviso de datos técnicos potencialmente sensibles antes de exportar.
- Barra de progreso, cancelación y estado por prueba.
- Modo básico para usuarios y modo técnico con evidencia completa.

Restricción: no habrá historial interno; el usuario administra los archivos exportados.

Criterio de aceptación: un usuario no técnico entiende el problema sin perder la evidencia profesional.

Rollback: conservar el exportador HTML actual como ruta de respaldo.

Estimación: 3–5 horas.

## Fase 8: distribución comercial

Estado: **NO INICIADA**.

Objetivo: entregar una aplicación instalable, identificable y confiable.

Capacidades:

- Versión, producto, fabricante y descripción en el ejecutable.
- Instalador MSI o MSIX con desinstalación limpia.
- Firma de código para artefactos públicos.
- Licencia de uso, privacidad, limitaciones y soporte.
- Actualización mediante manifiesto firmado o canal de distribución confiable.
- Licencia personal/técnico mediante archivo firmado, sin DB y sin conexión obligatoria.
- SBOM y hashes SHA-256 de los artefactos publicados.

Seguridad:

- Secretos de firma fuera del repositorio.
- Builds reproducibles desde dependencias fijadas.
- Escaneo de dependencias y artefactos antes de publicar.
- La ausencia de conexión no debe impedir el diagnóstico local.

Criterio de aceptación: instalación y desinstalación limpias, firma válida y actualización verificable.

Rollback: conservar instalador y artefacto anterior firmado para una reversión documentada.

Estimación: 1–3 días, sin contar tiempos externos para obtener certificados o aprobar tiendas.

## Fase 9: validación comercial y lanzamiento

Estado: **NO INICIADA**.

Objetivo: demostrar compatibilidad antes de llamar al producto comercialmente confiable.

Matriz mínima:

- Windows 10 y Windows 11 soportados oficialmente.
- Usuario estándar y ejecución elevada únicamente donde esté justificado.
- Laptop y escritorio.
- CPU Intel y AMD.
- GPU integrada y dedicada de proveedores soportados.
- HDD, SSD SATA y NVMe.
- Equipo sin batería, sin sensores disponibles y sin Internet.
- Escalado visual de 100 %, 125 % y 150 %.

Gates de lanzamiento:

- Pruebas unitarias, integración, smoke y flujo completo aprobados.
- Lint, tipado, auditoría de dependencias y escaneo de secretos aprobados.
- Ningún `CRITICAL` puede originarse únicamente por una medición ausente.
- Cero comandos libres o acciones destructivas.
- Diagnóstico cancelable y UI responsiva.
- Reportes verificados visualmente y sin datos no anunciados.
- Instalador firmado, manual, licencia y procedimiento de soporte disponibles.
- Rollback probado con la última versión estable.
- Riesgos residuales publicados y aceptados.

Criterio de aceptación: el producto cumple todos los gates o registra explícitamente cada excepción.

Estimación: 2–5 días, dependiendo de la disponibilidad de equipos de prueba.

## Orden de ejecución cuando se retome el proyecto

1. Crear rama para la Fase 0 y proteger la línea base.
2. Implementar las fases 1 a 5 como slices independientes.
3. Publicar una beta técnica sin pruebas activas destructivas.
4. Implementar la Fase 6 detrás de una opción desactivable.
5. Completar experiencia, distribución y firma en las fases 7 y 8.
6. Ejecutar la matriz de la Fase 9.
7. Publicar `v1.0.0` solo después de aprobar los gates.

Las fases no se mezclarán en un único cambio. Cada una terminará con pruebas, ejecutable
de verificación, documentación actualizada y un commit recuperable.

## Definition of Done de la versión comercial 1.0

La versión se considerará comercialmente confiable cuando:

- La línea base inicial siga funcionando sin regresiones.
- Las mediciones soportadas tengan fuente, unidad, tiempo y calidad identificables.
- Las conclusiones distingan hechos, causas probables y limitaciones.
- Los fallos parciales y hardware no compatible estén claramente representados.
- Las pruebas activas sean opcionales, limitadas y cancelables.
- El producto funcione sin DB, cuenta, servidor o Internet obligatorio.
- No exista recolección remota ni telemetría oculta.
- El instalador y ejecutable estén identificados y firmados.
- La matriz mínima de Windows y hardware haya sido ejecutada.
- Existan manual, licencia, soporte, hashes y procedimiento de rollback.

## Fuera de alcance para 1.0

- Reparar automáticamente Windows o modificar controladores.
- Actualizar BIOS, firmware o drivers desde la aplicación.
- Overclock, cambios de voltaje o pruebas destructivas.
- Terminal con comandos introducidos por el usuario.
- Cuentas, nube, panel web, inventario centralizado o administración remota.
- Base de datos local o remota.
- Compatibilidad con Linux o macOS.

## Riesgos pendientes para el inicio futuro

- La lectura de sensores depende del fabricante y puede requerir una dependencia especializada.
- SMART y NVMe no exponen los mismos atributos en todos los dispositivos.
- La firma de código puede requerir costo, identidad verificada y tiempos externos.
- La validación real necesita varios equipos; mocks no reemplazan toda la matriz de hardware.
- Algunas comprobaciones requieren permisos elevados y deben degradarse de forma segura.
- “Diagnóstico completo” no significa certeza física absoluta; siempre se comunicarán límites.
