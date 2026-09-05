# ADR-002: Nuevo alcance académico sobre la base existente

- Fecha: 2026-09-04.
- Estado: decisión de planificación; implementación pendiente.
- Alcance: enunciado Hardware Diagnostic & Repair Assistant, secciones 1–46.

## Contexto y drivers

La app actual ya reúne interfaz, recolectores, motor y HTML. El enunciado nuevo
exige conectividad, reglas diferentes, recomendaciones localizadas, JSON/TXT,
investigación y dossier. La planificación comercial no reemplaza la rúbrica.
El usuario pidió conservar el programa funcional y preparar la estructura.

## Alternativas

1. Reescritura literal en carpetas españolas: coincide visualmente con la guía,
   pero rompe importaciones sin mejorar el objetivo pedagógico.
2. Extensión del monolito existente: reutiliza UI, contratos y empaquetado,
   permite demostrar las mismas responsabilidades y probar cada caso.
3. Producto comercial con DB/cuentas: añade costes y dependencias no exigidos.

## Decisión

Elegir 2. BUILD_PLAN.md es el diseño canónico del nuevo alcance; conservar la
hoja comercial en docs/COMMERCIAL_ROADMAP.md como etapa diferida.
Conservar ADR-001: sin DB. Persistir reportes solo por elección del usuario.
Mantener lectura y recomendación; no implementar reparación automática.
No crear archivos Python ni mover módulos durante esta etapa documental.

## Consecuencias

La evaluación medirá comportamientos y evidencia, no coincidencia de nombres
de carpetas. Se necesita nueva evidencia para el nuevo enunciado; los gates
académicos previos no se heredan como aprobados. Las extracciones desde core.py
serán graduales, con fixtures y compatibilidad antes de retirar código.

## Trigger de revisión

Revisar si el docente impone una estructura literal o el usuario aprueba iniciar
la implementación. Revisar DB únicamente ante un requisito confirmado de
persistencia consultable centralizada; la discusión comercial no lo aprueba.
