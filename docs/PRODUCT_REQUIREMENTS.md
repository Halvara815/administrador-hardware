# Requisitos y aceptación del producto

Estado: capacidades actuales y ampliaciones por fases. El plan registra la Fase 1
completada; los demás resultados se verificarán antes de cada distribución.
La tabla expresa criterios de aceptación, no una certificación de funciones pendientes.

| ID | Capacidad | Estado | Aceptación | Fase |
|---|---|---|---|
| P01 | Interfaz y resumen | COMPLETADA | Navegación clara, conteos únicos, estados y evidencia | 4–5 |
| P02 | CPU/RAM | COMPLETADA | Umbrales sin huecos; carga alta no equivale a daño físico | 1 |
| P03 | PCI/PCIe | COMPLETADA | Nombre, clase, ID, driver; localizar fallo en un dispositivo | 3 |
| P04 | USB | COMPLETADA | Distinguir ausencia, error del periférico y falta de volumen | 3 |
| P05 | Red | COMPLETADA | IPv4/IPv6, gateway, DNS y alcance de conectividad | 2 |
| P06 | Almacenamiento | COMPLETADA | Medio/bus/volumen, capacidad y recomendaciones por espacio | 3 |
| P07 | GPU/drivers | COMPLETADA (inventario) | Identidad, versión y límites de un estado OK | 3 |
| P08 | Motor | COMPLETADA (reglas base) | Evidencia, causas posibles, siguiente comprobación y recomendaciones | 1–4 |
| P09 | Monitorización/gráficos | COMPLETADA (E/S) | Muestras acotadas, fecha, unidades y parada | 4 |
| P10 | Exportación | COMPLETADA | HTML, JSON/TXT, identidad opcional y limitaciones | 5 |
| P11 | Documentación | COMPLETADA | Instalación, uso, límites, soporte, dependencias y fuentes | 6 |
| P12 | Distribución | PARCIAL | EXE/ZIP/versionado completos; falta equipo limpio | 7 |
| P13 | IA opcional | NO INICIADA | Fuentes comprobadas, abstención, consentimiento y fallback | I1–I5 |
| P14 | Asesor RAM | PARCIAL | Inventario local y regla de abstención; faltan fuentes OEM verificadas, configuraciones por ranura y validación física | E2; I1–I5 opcional |
| P15 | Asesor drivers | NO INICIADA | Aplicabilidad Windows/OEM; ninguna instalación automática | I1–I5 |
| P16 | Guía por síntoma | NO INICIADA | C1–C5, cambios recientes declarados, evidencia y siguiente prueba; no confundir cronología con causa | E1 |
| P17 | Antes de comprar / ¿Por qué? | NO INICIADA | Ficha común SKU, compatibilidad, accesorios, costes/fuentes y datos faltantes; priorizar comprobaciones gratuitas | E1–E2, E8 |
| P18 | Verificación y cambios | NO INICIADA | Verificar ampliación esperada y repetir pruebas; comparar JSON sin certificar estabilidad ni mejora sin baseline comparable | E3 |
| P19 | Compartir con técnico | NO INICIADA | Vista previa depurada; originales intactos; validar importación y esquema | E3 |
| P20 | Compatibilidad GPU | PARCIAL | Regla local sobre fuente, conectores, espacio y ranura declarados; faltan fuentes/SKU verificados y validación física | E4 |
| P21 | Limitación por sesión | NO INICIADA | Contexto y métricas reales, cancelación; sin porcentaje universal CPU/GPU | E5 |
| P22 | Refresco de pantalla | NO INICIADA | Modos disponibles para conexión/resolución actuales; no modificar configuración | E6 |
| P23 | Recomendar GPU concreta | NO INICIADA | SKU y compatibilidad, uso/resolución/FPS objetivo, presupuesto y fuentes; justificar compra o no compra; sin prometer eliminar todo cuello de botella | E4–E5 |

| P24 | Qué actualizar primero | PARCIAL | Orden local de comprobaciones y alternativa sin compra; falta evidencia de rendimiento y costes/fuentes verificadas | E8 |
| P25 | Asesor SSD | PARCIAL | Regla local para protocolo/formato/bahía declarados y añadir/reemplazar; faltan fuente OEM y comprobación física | E7 |
| P26 | Velocidad RAM | NO INICIADA | Unidades y configuración frente a límites verificables; sin garantizar perfiles ni cambiar BIOS | E2 |
| P27 | GPU por aplicación | NO INICIADA | Proceso/periodo/adaptador observados; multi-GPU y desconocido explícitos; sin cambios automáticos | E5 |
| P28 | Cuándo acudir a técnico | NO INICIADA | Criterios de parada y límites; orientación sin declarar seguridad ante ausencia de datos | E1 |

E1, E3, E5, E6 siguen **NO INICIADOS**. E2, E4, E7 y E8 tienen una implementación
local **PARCIAL** autorizada el 2026-09-11: usa inventario de la sesión y datos
documentales declarados por el usuario, se abstiene cuando falta evidencia y no
consulta tiendas/fuentes ni declara los slices completos. Contratos, dependencias,
escenarios adversos y gates completos:
[diseño del asesor](architecture/09-diagnostic-advisor.md). Las pruebas históricas
no validan estas capacidades. I1–I5 es la integración IA, no un requisito para
ejecutar los recorridos deterministas.

## Casos de regresión prioritarios

- APIPA 169.254.x.x sin gateway: investigar DHCP, configuración y conexión local.
- IP externa accesible pero resolución fallida: posible problema DNS.
- NIC PCIe con error y resto normal: diagnóstico localizado.
- Controlador USB normal, periférico con error y sin disco: investigar periférico/driver.
- CPU97/RAM91 con resto normal: recursos elevados; revisar procesos, servicios e inicio.
- Todo OK con reinicios al jugar: diagnóstico adicional, sin declarar el equipo sano.
- CPU98/RAM52: investigar carga CPU; RAM95/CPU30: investigar presión de memoria.
- Disco96 %: espacio insuficiente; orientar limpieza sin borrar automáticamente.

Conservar fixtures reproducibles y separarlos de pruebas reales. Las evidencias
reales registran versión, entorno, procedimiento y resultado; se anonimizan para compartir.

## Preparación para distribución

Exigir pruebas relevantes, lint/tipado, revisión de dependencias, arranque del EXE,
validación de reportes y prueba en equipo limpio. Documentar límites pendientes.
Distribuir manual y avisos de terceros; conservar código y evidencia de desarrollo
en el repositorio privado. Firma, actualizaciones y licencia comercial se completan
según la hoja comercial; su planificación no implica que ya estén disponibles.

## Decisión de datos

Sin DB para el diagnóstico local. Reportes explícitos y logs mínimos.
Cuentas, cuotas y pagos son una decisión futura de arquitectura.
En el diseño de exportación, permitir omitir identificadores personales;
la implementación de esa opción se verificará antes de anunciarla como disponible.
