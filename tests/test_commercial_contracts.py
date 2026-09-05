"""Pruebas unitarias para los contratos de diagnóstico profesional (Fase F1 comercial)."""

from datetime import UTC, datetime
from unittest import TestCase

from hardware_admin.diagnostics.engine import RuleBasedDiagnosticEngine
from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    ConfidenceLevel,
    DiagnosticReport,
    EvidenceRecord,
    HealthStatus,
    Measurement,
)
from hardware_admin.reports.json_report import build_payload


class CommercialContractsTests(TestCase):
    def test_default_values_preserve_existing_contracts(self) -> None:
        result = ComponentResult(
            component=ComponentKind.CPU,
            name="CPU",
            facts={"Uso": "25%"},
            summary="25% de uso",
            status=HealthStatus.NORMAL,
        )

        # Campos profesionales con valores predeterminados seguros: LOW por defecto
        self.assertEqual(result.confidence, ConfidenceLevel.LOW)
        self.assertEqual(result.measurements, ())
        self.assertTrue(result.is_supported)

    def test_measurement_structure_and_optional_duration(self) -> None:
        m_with_duration = Measurement(
            name="Temperatura CPU",
            value=65.5,
            unit="°C",
            expected_range=(30.0, 85.0),
            duration_seconds=1.0,
        )
        self.assertEqual(m_with_duration.name, "Temperatura CPU")
        self.assertEqual(m_with_duration.value, 65.5)
        self.assertEqual(m_with_duration.unit, "°C")
        self.assertEqual(m_with_duration.expected_range, (30.0, 85.0))
        self.assertEqual(m_with_duration.duration_seconds, 1.0)

        # Sin duración especificada debe ser None
        m_without_duration = Measurement(
            name="Uso de memoria",
            value=45,
            unit="%",
            expected_range=(0.0, 90.0),
        )
        self.assertIsNone(m_without_duration.duration_seconds)
        self.assertIsInstance(m_without_duration.value, int)

    def test_not_supported_and_cancelled_are_not_hardware_problems(self) -> None:
        unsupported_result = ComponentResult(
            component=ComponentKind.SYSTEM,
            name="Sensor TPM",
            facts={},
            summary="No disponible en este hardware",
            status=HealthStatus.NOT_SUPPORTED,
            is_supported=False,
            confidence=ConfidenceLevel.LOW,
        )

        cancelled_result = ComponentResult(
            component=ComponentKind.IO,
            name="Monitorización E/S",
            facts={},
            summary="Cancelada por el usuario",
            status=HealthStatus.CANCELLED,
            confidence=ConfidenceLevel.MEDIUM,
        )

        report = DiagnosticReport(
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            results=(unsupported_result, cancelled_result),
            conclusion="Análisis completado con funciones no soportadas.",
        )

        # Ninguno debe marcar el equipo como averiado
        self.assertFalse(report.has_problems)

    def test_engine_handles_not_supported_gracefully(self) -> None:
        unsupported_result = ComponentResult(
            component=ComponentKind.MONITOR_GPU,
            name="Sensores de GPU",
            facts={},
            summary="Sensor no expuesto por el driver",
            status=HealthStatus.NOT_SUPPORTED,
            is_supported=False,
        )

        engine = RuleBasedDiagnosticEngine()
        report = engine.build_report((unsupported_result,))

        self.assertFalse(report.has_problems)
        self.assertTrue(any("función no soportada" in lim for lim in report.limitations))
        self.assertIn("no son soportadas", report.conclusion)

    def test_json_payload_serialization_with_professional_fields(self) -> None:
        m = Measurement(
            name="Carga de CPU",
            value=45.2,
            unit="%",
            expected_range=(0.0, 90.0),
            duration_seconds=1.0,
        )
        result = ComponentResult(
            component=ComponentKind.CPU,
            name="CPU",
            facts={"Frecuencia": "3.6 GHz"},
            summary="45% de uso",
            status=HealthStatus.NORMAL,
            confidence=ConfidenceLevel.HIGH,
            measurements=(m,),
            is_supported=True,
            evidence=(EvidenceRecord("psutil", "cpu_percent()", "45.2%", datetime.now(UTC)),),
        )

        report = DiagnosticReport(
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            results=(result,),
            conclusion="Normal",
        )

        payload = build_payload(report, include_identity=False)
        self.assertEqual(payload["schema_version"], "1.0")
        item = payload["resultados"][0]
        self.assertEqual(item["confianza"], "high")
        self.assertTrue(item["soportado"])
        self.assertEqual(len(item["mediciones"]), 1)
        self.assertEqual(item["mediciones"][0]["nombre"], "Carga de CPU")
        self.assertEqual(item["mediciones"][0]["valor"], 45.2)
        self.assertEqual(item["mediciones"][0]["unidad"], "%")
        self.assertEqual(item["mediciones"][0]["rango_esperado"], [0.0, 90.0])
        self.assertEqual(payload["cobertura"]["componentes_no_soportados"], 0)
