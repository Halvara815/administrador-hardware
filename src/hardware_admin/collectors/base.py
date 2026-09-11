"""Contrato común para todos los recolectores."""

from typing import Protocol, runtime_checkable

from hardware_admin.domain.models import ComponentKind, ComponentResult


@runtime_checkable
class HardwareCollector(Protocol):
    component: ComponentKind

    def collect(self) -> ComponentResult:
        """Recopila un componente sin modificar el sistema."""
        ...


@runtime_checkable
class SessionResettable(Protocol):
    """Protocolo opcional para recursos o recolectores que gestionan estado por escaneo."""

    def reset_session(self) -> None:
        """Reinicia la caché o estado interno para una nueva sesión de escaneo."""
        ...
