# ADR-002: Evolución modular de un producto personal

- Estado: decisión de diseño; implementación por fases.
- Fecha: 2026-09-04.
- Objetivo: ampliar Hardware Diagnostic & Repair Assistant preservando la base funcional.

## Contexto

La aplicación reúne interfaz, recolectores, motor y HTML. Su siguiente etapa
amplía conectividad, recomendaciones, gráficos y formatos de exportación.
El proyecto se orienta a uso personal y futura comercialización.

## Alternativas y decisión

Reescribir la estructura rompe importaciones sin beneficio demostrado.
Un cliente-servidor agrega operación sin requisito actual.
Se elige extender el monolito por funcionalidades verificables y conservar
la separación entre medición, diagnóstico, interfaz y exportación.

## Consecuencias

BUILD_PLAN.md dirige las fases; PRODUCT_REQUIREMENTS.md define aceptación.
La hoja comercial y la investigación de IA complementan el plan.
Se mantiene ADR-001: sin DB propia para el diagnóstico local.
Los resultados históricos no certifican funcionalidades nuevas.
La distribución para usuarios no incluye por defecto el código fuente privado.

## Revisión

Revisar la persistencia si se aprueban cuentas, cuotas o historial consultable.
Los nombres de archivos existentes se migran gradualmente sin romper enlaces.
