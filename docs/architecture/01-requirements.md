# Requisitos y alcance

> Alcance histórico v0.1.0. El alcance del producto sustituye las doce opciones por
> quince más Salir y amplía los casos y entregables. Consultar el
> [plan vigente](../../BUILD_PLAN.md) y la
> [trazabilidad actual](../PRODUCT_REQUIREMENTS.md).
> Las nuevas capacidades están pendientes; se conserva la decisión sin DB.

## Requisitos confirmados

- Aplicación gráfica de escritorio; no se usará una interfaz de terminal.
- Una ventana principal con las doce opciones del producto.
- Panel de diagnóstico y panel pequeño de evidencia similar a una terminal.
- Inspección de CPU, RAM, almacenamiento, red, USB, PCI/PCIe, controladores,
  dispositivos con problemas, monitor/GPU y E/S.
- Matriz con componente, evidencia, estado y posible problema.
- Conclusión justificada por las evidencias recopiladas.
- Generación de reporte.
- Sin base de datos.

## Actor y casos de uso

- Actor: usuario o técnico que ejecuta la aplicación en un equipo Windows.
- Analizar el equipo completo.
- Consultar el detalle de un componente.
- Ver y copiar evidencia técnica de solo lectura.
- Exportar un reporte para entrega o soporte.

## Fuera de alcance

- Modificar controladores, reparar dispositivos o cambiar configuración del sistema.
- Ejecutar comandos escritos por el usuario.
- Inventario centralizado, cuentas, sincronización, servidor web o nube.
- Historial interno persistente; no existen esquemas ni migraciones de base de datos.
- Compatibilidad inicial con Linux o macOS.

## Supuestos

Ampliaciones confirmadas para planificación, no implementadas: máximo RAM verificado
y configuraciones de ampliación; compatibilidad GPU separada del rendimiento por
sesión; guía por síntoma; comprobación posterior; comparación y exportación depurada;
revisión del refresco disponible. Véanse P14 y P16–P22 en
[requisitos del producto](../PRODUCT_REQUIREMENTS.md) y
[slices E1–E8](09-diagnostic-advisor.md), incluyendo P23–P28 y ampliaciones de P16–P18.
No cambia la exclusión de reparaciones
automáticas, comandos libres, historial interno ni DB. IA remota opcional requiere
consentimiento; la exclusión histórica de nube se refiere a servicios obligatorios.

- Objetivo inicial: Windows 10/11 con PowerShell disponible.
- Un usuario y un análisis activo por proceso.
- Los reportes se guardan únicamente cuando el usuario selecciona una ubicación.
