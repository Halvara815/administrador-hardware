# Hardware Diagnostic & Repair Assistant

Proyecto personal de diagnóstico de hardware para Windows, orientado a usuarios
y técnicos. Recopila información real, presenta evidencia comprensible y ayuda
a investigar posibles problemas. Su evolución comercial se desarrolla por fases.

La aplicación actual funciona localmente y **no utiliza base de datos**.
Las funciones de IA, recomendación de compras y actualización asistida de
controladores están en investigación; todavía no están integradas.

![Interfaz](docs/ui-live.png)

## Funciones disponibles

- Información del sistema, CPU, RAM, almacenamiento y red.
- Dispositivos USB y PCI/PCIe, controladores y monitor/GPU.
- Detección de estados problemáticos y análisis por sección.
- Matriz de resultados, conclusiones y consola de evidencia de solo lectura.
- Muestra de actividad de E/S y exportación HTML.

Consultar el [plan de desarrollo](BUILD_PLAN.md) para el estado de cada fase.
Las capturas y el paquete existente pueden corresponder a una revisión anterior
al código fuente; cada distribución debe identificar su versión y pruebas.

## Ejecutar

Extraer la carpeta completa del paquete y abrir:

```text
dist/AdministradorDeHardware/AdministradorDeHardware.exe
```

Conservar las dependencias junto al ejecutable. Pulsar **ANALIZAR EQUIPO**,
seleccionar un componente y utilizar la opción de reporte para exportar HTML.
No hace falta instalar Python para usar la distribución empaquetada.

## Desarrollo

Se requiere Windows y un Python compatible con pyproject.toml.
Ejecutar run.cmd para desarrollo o build.cmd para reconstruir.
El build instala requirements.lock, ejecuta pruebas, lint y tipado y genera
el ejecutable con PyInstaller. Los paquetes quedan en release/.

Bibliotecas principales: CustomTkinter para la interfaz, psutil para métricas
y Pillow para recursos visuales. Las consultas Windows usan subprocess y
PowerShell. Las versiones están registradas en requirements.lock.

## Arquitectura y documentación

- [Plan por fases](BUILD_PLAN.md): alcance, gráficos, casos y aceptación.
- [Requisitos del producto](docs/PRODUCT_REQUIREMENTS.md): capacidades y pruebas previstas.
- [Arquitectura](docs/architecture/03-system-design.md): responsabilidades y contratos.
- [Investigación de IA y hardware](docs/RESEARCH_AI_HARDWARE.md): fuentes y compatibilidad.
- [Diseño del asesor](docs/architecture/09-diagnostic-advisor.md): ampliación de RAM,
  compatibilidad y rendimiento GPU, solución guiada y comparación; pendiente de implementar.
- [Evolución comercial](docs/COMMERCIAL_ROADMAP.md): distribución, soporte y validación.
- [Verificación histórica](docs/architecture/08-production-readiness.md): evidencia con alcance limitado.

## Datos y límites

Las consultas son de solo lectura y pertenecen a un catálogo cerrado.
Un fallo parcial conserva resultados válidos; un estado OK no descarta todos
los problemas físicos. La aplicación no instala drivers ni repara automáticamente.

Los resultados permanecen en memoria y los reportes se guardan a petición del
usuario; pueden incluir datos del equipo. Revisarlos antes de compartirlos.
Existen logs técnicos locales para investigar fallos. La compatibilidad depende
de Windows, los permisos y la información que exponga cada fabricante.

La IA futura será opcional. El diseño contempla consentimiento para consultas
remotas y fuentes verificables para recomendaciones. La gestión de cuentas,
pagos o cuotas comerciales requerirá una decisión independiente.

## Distribución y soporte

El repositorio contiene código, pruebas y documentación de desarrollo.
Los paquetes para usuarios incluirán ejecutable, dependencias, guía de uso,
notas de versión y avisos de terceros. No se declara todavía una versión
comercial validada en todos los equipos.

Para reportar problemas, incluir versión, Windows, pasos de reproducción y
mensaje de error; evitar adjuntar seriales, claves o reportes personales completos.
