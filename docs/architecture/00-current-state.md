# Architecture 0

## Evidencia observada

- La carpeta del proyecto estaba vacía al iniciar la estructuración.
- El producto requiere una aplicación Python que inspeccione hardware real en Windows.
- La interfaz acordada es una sola ventana con navegación lateral, diagnóstico,
  matriz de hallazgos y panel de evidencia técnica.
- El usuario confirmó que no habrá base de datos.
- No se observó repositorio Git, pipeline, código, pruebas ni configuración previa.
- El runtime de Python no pudo verificarse en este entorno por una limitación de acceso.

## Flujo crítico propuesto

Usuario → Analizar equipo → servicio de análisis → recolectores locales → reglas →
matriz y conclusión → interfaz → exportación opcional de reporte.

## Restricciones y riesgos visibles

- Algunas consultas PnP/CIM varían según Windows y los permisos disponibles.
- Las consultas no deben bloquear el hilo de la interfaz.
- La salida de PowerShell debe tratarse como dato no confiable y normalizarse.
- El ejecutable debe construirse y validarse en Windows; PyInstaller no es un
  compilador cruzado.
