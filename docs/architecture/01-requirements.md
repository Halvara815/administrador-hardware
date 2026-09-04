# Requisitos y alcance

## Requisitos confirmados

- Aplicación gráfica de escritorio; no se usará una interfaz de terminal.
- Una ventana principal con las doce opciones del enunciado.
- Panel de diagnóstico y panel pequeño de evidencia similar a una terminal.
- Inspección de CPU, RAM, almacenamiento, red, USB, PCI/PCIe, controladores,
  dispositivos con problemas, monitor/GPU y E/S.
- Matriz con componente, evidencia, estado y posible problema.
- Conclusión justificada por las evidencias recopiladas.
- Generación de reporte.
- Sin base de datos.

## Actor y casos de uso

- Actor: estudiante o técnico que ejecuta la aplicación en un equipo Windows.
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

- Objetivo inicial: Windows 10/11 con PowerShell disponible.
- Un usuario y un análisis activo por proceso.
- Los reportes se guardan únicamente cuando el usuario selecciona una ubicación.

