# Protocolo de pruebas reales

Las pruebas automatizadas usan fixtures **simulados**: comprueban que la lógica
reacciona como se espera, pero no demuestran que el programa se comporte bien
frente a hardware real. Este protocolo cubre esa diferencia.

**Estado: pendiente de ejecución.** Requiere manipular dispositivos físicos y
no puede automatizarse. Una prueba que no se pueda realizar se registra como
**no ejecutada**, nunca como superada.

## Reglas de registro

1. Anote **entorno, versión, procedimiento, resultado esperado y obtenido**.
2. Los fixtures de fallo están etiquetados como simulados y **no sustituyen**
   estas pruebas.
3. Retire los dispositivos de prueba de forma segura («Quitar hardware con
   seguridad») antes de desconectarlos.
4. Exporte el reporte en `.txt` como evidencia de cada caso y guárdelo junto a
   la ficha, preferentemente en su versión anónima.
5. Si un resultado obtenido no coincide con el esperado, **no lo ajuste**:
   regístrelo tal cual y abra la incidencia.

## Ficha por prueba

```text
Prueba      : PR-00
Fecha       :
Equipo      : (modelo, SO y compilación)
Versión app : 0.1.0    schema_version: 1.0
Admin       : sí / no
Procedimiento:
Esperado    :
Obtenido    :
Evidencia   : (archivo .txt exportado)
Resultado   : superada / fallida / NO EJECUTADA
```

## Casos

| ID | Escenario | Resultado esperado |
|---|---|---|
| PR-01 | USB conectado antes del análisis | Aparece en el apartado USB con su identificador de instancia |
| PR-02 | USB retirado y análisis repetido | Desaparece del inventario; **no** se afirma que nunca existió |
| PR-03 | Análisis sin ningún USB conectado | Caso «USB ausente»: se advierte que la lista vacía no prueba ausencia física |
| PR-04 | Memoria USB con partición sin letra | Caso «USB sin volumen»: advertencia y sugerencia de asignar letra, sin condenar el bus |
| PR-05 | Cable de red desconectado | Adaptador desconectado; conectividad falla en la etapa de adaptador |
| PR-06 | Router apagado con cable conectado | Dirección APIPA (169.254.x.x); caso C1 con procedimiento DHCP marcado como modificador |
| PR-07 | DNS inválido configurado a mano | Conectividad IP correcta y resolución fallida; propone `ipconfig /flushdns` |
| PR-08 | Red normal | Las cinco etapas en OK; se conserva el aviso de que un ping sin respuesta puede ser ICMP bloqueado |
| PR-09 | Disco casi lleno (>95 %) | Estado crítico y recomendación de liberar espacio |
| PR-10 | Copia de archivo grande durante la monitorización | El gráfico de disco refleja la actividad; el de red permanece en su escala |
| PR-11 | Monitorización durante 6 minutos | El buffer se detiene en 300 muestras y descarta las antiguas |
| PR-12 | Cerrar con la opción 0 durante el muestreo | La ventana cierra y el proceso termina sin quedar en memoria |
| PR-13 | Ejecución **sin** privilegios de administrador | Las secciones afectadas informan error de consulta, no componente sano |
| PR-14 | Dispositivo con código de error en el Administrador de dispositivos | Aparece en «Dispositivos con problemas» con su código |
| PR-15 | Exportar en HTML, JSON y TXT | Los tres se abren correctamente y coinciden en conclusión y cobertura |
| PR-16 | Exportar copia anónima | Equipo y usuario aparecen como `(omitido)`; se redactan IP, MAC, seriales y rutas personales en contexto, nombre del resultado, resumen, problemas, nombre de error de consulta, errores de consulta, recomendaciones, conclusión y limitaciones; la salida de evidencia cruda se reemplaza con `(omitido)` conservando fuente, consulta y fecha; las máscaras de red matemáticamente válidas se conservan; las versiones permitidas se conservan únicamente si no representan una IPv4 válida; el fallo de consulta de actualizaciones de controladores se refleja como consulta no completada (`errores_de_consulta`) y estado de error |
| PR-17 | Síntoma con caracteres de shell (`lento & dir`) | Se conserva como texto en el reporte y no se ejecuta nada |
| PR-18 | Guardar en carpeta sin permiso de escritura | Mensaje de error claro; la aplicación sigue funcionando |

## Consentimiento

Si alguna evidencia procede de un equipo que no es suyo, recabe permiso antes
de guardarla y exporte siempre la copia anónima. No incluya reportes con
identidad en el repositorio.
