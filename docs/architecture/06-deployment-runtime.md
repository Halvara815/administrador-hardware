# Ejecución y distribución

## Runtime

- Desarrollo: entorno virtual de Python en Windows.
- Distribución: paquete de escritorio generado con PyInstaller en Windows.
- Configuración: constantes seguras incluidas; sin secretos ni variables de servidor.
- Red: no se requiere acceso a Internet para ejecutar diagnósticos.

## Archivos

- Recursos visuales empaquetados con la aplicación.
- Logs locales mínimos para errores técnicos, sin guardar evidencia sensible completa.
- Reportes escritos únicamente en una ruta elegida por el usuario.

## Release y rollback

1. Ejecutar formato, tipos y pruebas.
2. Construir primero en modo carpeta para diagnosticar recursos faltantes.
3. Ejecutar smoke test del artefacto en una máquina Windows limpia.
4. Distribuir la carpeta versionada comprimida.
5. Rollback: volver a distribuir la última versión verificada.

No hay migraciones, backup de servidor ni recuperación de base de datos.

