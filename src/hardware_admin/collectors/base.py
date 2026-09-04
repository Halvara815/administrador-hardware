"""Contrato común para todos los recolectores."""

from typing import Protocol

from hardware_admin.domain.models import ComponentKind, ComponentResult


class HardwareCollector(Protocol):
    component: ComponentKind

    def collect(self) -> ComponentResult:
        """Recopila un componente sin modificar el sistema."""
        ...
