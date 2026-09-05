# Requisitos y aceptación del producto

Estado: capacidades actuales y ampliaciones por fases. El plan registra la Fase 1
completada; los demás resultados se verificarán antes de cada distribución.
La tabla expresa criterios de aceptación, no una certificación de funciones pendientes.

| ID | Capacidad | Aceptación | Fase |
|---|---|---|---|
| P01 | Interfaz y resumen | Navegación clara, conteos únicos, estados y evidencia | 4–5 |
| P02 | CPU/RAM | Umbrales sin huecos; carga alta no equivale a daño físico | 1 |
| P03 | PCI/PCIe | Nombre, clase, ID, driver; localizar fallo en un dispositivo | 3 |
| P04 | USB | Distinguir ausencia, error del periférico y falta de volumen | 3 |
| P05 | Red | IPv4/IPv6, gateway, DNS y alcance de conectividad | 2 |
| P06 | Almacenamiento | Medio/bus/volumen, capacidad y recomendaciones por espacio | 3 |
| P07 | GPU/drivers | Identidad, versión y límites de un estado OK | 3 |
| P08 | Motor | Evidencia, causas posibles, siguiente comprobación y recomendaciones | 1–4 |
| P09 | Monitorización/gráficos | Muestras acotadas, fecha, unidades y parada | 4 |
| P10 | Exportación | HTML y futuros JSON/TXT; datos personales identificados | 5 |
| P11 | Documentación | Instalación, uso, límites, soporte, dependencias y fuentes | 6 |
| P12 | Distribución | EXE probado en equipo limpio, versión y dependencias completas | 7 |
| P13 | IA opcional | Fuentes comprobadas, abstención, consentimiento y fallback | I1–I5 |
| P14 | Asesor RAM | Instalada, máximo reportado/verificado, soldada, ranuras y configuración añadir/reemplazar; abstención ante límites contradictorios | E2; I1–I5 opcional |
| P15 | Asesor drivers | Aplicabilidad Windows/OEM; ninguna instalación automática | I1–I5 |
| P16 | Guía por síntoma | C1–C5, cambios recientes declarados, evidencia y siguiente prueba; no confundir cronología con causa | E1 |
| P17 | Antes de comprar / ¿Por qué? | Ficha común SKU, compatibilidad, accesorios, costes/fuentes y datos faltantes; priorizar comprobaciones gratuitas | E1–E2, E8 |
| P18 | Verificación y cambios | Verificar ampliación esperada y repetir pruebas; comparar JSON sin certificar estabilidad ni mejora sin baseline comparable | E3 |
| P19 | Compartir con técnico | Vista previa depurada; originales intactos; validar importación y esquema | E3 |
| P20 | Compatibilidad GPU | Fuente, conectores, espacio, ranura y SO; datos desconocidos no equivalen a incompatibilidad | E4 |
| P21 | Limitación por sesión | Contexto y métricas reales, cancelación; sin porcentaje universal CPU/GPU | E5 |
| P22 | Refresco de pantalla | Modos disponibles para conexión/resolución actuales; no modificar configuración | E6 |
| P23 | Recomendar GPU concreta | SKU y compatibilidad, uso/resolución/FPS objetivo, presupuesto y fuentes; justificar compra o no compra; sin prometer eliminar todo cuello de botella | E4–E5 |

| P24 | Qué actualizar primero | Prioridad RAM/GPU/almacenamiento según evidencia, objetivo y coste total; no comprar como resultado válido | E8 |
| P25 | Asesor SSD | Interfaz/protocolo/formato y ranuras verificados; añadir/reemplazar, capacidad y accesorios; no clonar/formatear | E7 |
| P26 | Velocidad RAM | Unidades y configuración frente a límites verificables; sin garantizar perfiles ni cambiar BIOS | E2 |
| P27 | GPU por aplicación | Proceso/periodo/adaptador observados; multi-GPU y desconocido explícitos; sin cambios automáticos | E5 |
| P28 | Cuándo acudir a técnico | Criterios de parada y límites; orientación sin declarar seguridad ante ausencia de datos | E1 |

E1–E8 están **NO INICIADOS**. Contratos, dependencias, escenarios adversos y gates:
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
