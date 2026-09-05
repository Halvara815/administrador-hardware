# Fase 4C — Recomendaciones estructuradas

Fecha: 2026-09-05. Estado: diseño aprobado, pendiente de implementar.
Rebanada 3 de 4 de la Fase 4. La 4D (menú de 15 opciones y Salir) va aparte.

## Problema

El motor entrega hoy una frase suelta por componente en `possible_problem`.
El plan exige recomendaciones con causa, pasos ordenados, fundamento,
comprobación posterior y si el procedimiento modifica el sistema.

## Alcance

Entra: `domain/models.py` (contrato `Recommendation` y campo nuevo en
`DiagnosticReport`), `diagnostics/recommendations.py`, el cableado en
`diagnostics/engine.py`, la sección del reporte HTML y la ficha de la interfaz.

No entra: la pantalla dedicada del menú (4D), la exportación JSON/TXT (fase 5)
y la asesoría de compra E1-E8, que sigue sin iniciar.

## Decisiones y fundamento

**El contrato vive en `domain`.** `DiagnosticReport` transporta las
recomendaciones y la fase 5 las exportará; ponerlas en `diagnostics` obligaría
a que el reporte dependiera del motor.

**`modifies_system` es obligatorio y por defecto `False`.** Separa comprobar de
alterar. El plan es explícito: «Repair Assistant significa proponer
procedimientos correctivos, no reparar automáticamente. No se ejecutarán
release/renew, limpieza DNS o cambios de drivers». La aplicación nunca ejecuta
una recomendación; el campo existe para que el usuario sepa qué va a cambiar en
su equipo antes de escribirlo él mismo.

**Campo nuevo opcional en `DiagnosticReport`.** `recommendations` con tupla
vacía por defecto: ninguna construcción existente se rompe.

**El generador es una función pura sobre los resultados.** No consulta Windows
ni psutil: lee `ComponentResult` y decide. Así se prueba entero sin hardware.

**Las recomendaciones se derivan del estado ya clasificado**, no de umbrales
propios. Reutiliza la clasificación que produjeron las reglas de la fase 1 en
lugar de reinterpretar porcentajes, para que la vista nunca contradiga la matriz.

**Un fallo de consulta genera recomendación propia.** Dato ausente no es
hardware sano: si una comprobación no se completó, la salida es repetir con
permisos suficientes, no silencio.

## Contrato

```text
Recommendation (inmutable)
    component        ComponentKind
    title            qué hacer, en una línea
    cause            por qué se propone, ligado a la evidencia observada
    steps            tuple[str, ...] pasos ordenados
    rationale        fundamento técnico
    verification     cómo comprobar que se resolvió
    modifies_system  bool; False = sólo consulta

DiagnosticReport.recommendations: tuple[Recommendation, ...] = ()

build_recommendations(results, symptom=None, expected_device=None)
    -> tuple[Recommendation, ...]
```

## Cobertura de casos

Una recomendación por situación ya documentada: CPU alta, RAM alta, disco sin
espacio, APIPA (C1), fallo DNS, NIC PCIe (C2), periférico USB (C3), USB sano sin
volumen, GPU con síntoma y estado OK, síntoma persistente sin anomalías (C5) y
consulta fallida. Los procedimientos que alteran el equipo —`ipconfig /release`,
`/renew`, `/flushdns`, reinstalar controladores— van marcados con
`modifies_system=True` y jamás se ejecutan.

## Invariantes

- Un equipo sin anomalías y sin síntoma no genera recomendaciones.
- Ninguna recomendación se ejecuta: la aplicación sólo la describe.
- Toda recomendación tiene al menos un paso y una comprobación posterior.
- Las recomendaciones se ordenan por gravedad: primero CRÍTICO, luego
  ADVERTENCIA, luego las derivadas de fallo de consulta y síntoma.
- El síntoma del usuario se trata como dato, nunca como instrucción: no se
  interpola en ningún comando.

## Pruebas de aceptación

Que cada caso documentado produzca su recomendación con los cinco campos
poblados; que los procedimientos que alteran el equipo estén marcados y los de
sólo consulta no; que un equipo limpio no genere ninguna; que el orden respete
la gravedad; que el reporte HTML muestre la sección y escape el contenido; y que
un síntoma con caracteres de shell no llegue a ningún comando.

Gates: pytest, ruff y mypy en verde.

## Recuperación

El campo es opcional y el generador independiente: si falla, el reporte sigue
mostrando la conclusión y los problemas posibles como hasta ahora.
