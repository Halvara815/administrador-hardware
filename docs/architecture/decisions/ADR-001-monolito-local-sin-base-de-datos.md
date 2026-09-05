# ADR-001: Monolito local sin base de datos

- Estado: aceptado
- Fecha: 2026-09-04
- Responsables: equipo del proyecto

## Contexto

La aplicación analiza un solo computador, es ejecutada por un usuario local y debe
entregarse como programa gráfico. El usuario confirmó que no habrá base de datos.

## Drivers

- Facilidad de desarrollo y validación del producto.
- Acceso directo y controlado a APIs locales de Windows.
- Ejecución sin servidor ni conexión a Internet.
- Distribución simple y decisiones reversibles.

## Alternativas

### A. Script monolítico en un archivo

Es rápido al inicio, pero mezcla interfaz, comandos y reglas, dificulta las pruebas
y tiende a congelar o romper toda la aplicación ante un fallo parcial.

### B. Monolito modular de escritorio

Mantiene un único ejecutable lógico, separa responsabilidades y permite sustituir
recolectores o la UI sin introducir servicios distribuidos.

### C. Aplicación cliente-servidor con base de datos

Permitiría inventario histórico, pero añade red, autenticación, despliegue y
migraciones que no resuelven un requisito actual.

## Decisión

Adoptar la alternativa B. Los resultados viven en memoria y sólo se exportan a un
archivo cuando el usuario lo solicita.

## Consecuencias

- Menor complejidad operativa y mejor capacidad de prueba que un script único.
- No existe historial interno ni análisis de múltiples equipos.
- La UI debe manejar trabajos en segundo plano dentro del mismo proceso.

## Trigger de revisión

Reconsiderar persistencia o separación cliente-servidor únicamente si aparece un
requisito confirmado de historial consultable, múltiples equipos o usuarios.
