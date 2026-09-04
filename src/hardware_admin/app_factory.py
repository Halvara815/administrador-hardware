"""Composición explícita de las dependencias de la aplicación."""

from hardware_admin.collectors.core import build_default_collectors
from hardware_admin.diagnostics.engine import RuleBasedDiagnosticEngine
from hardware_admin.services.scan_service import ScanService


def build_scan_service() -> ScanService:
    return ScanService(
        collectors=build_default_collectors(),  # type: ignore[arg-type]
        diagnostic_engine=RuleBasedDiagnosticEngine(),
    )
