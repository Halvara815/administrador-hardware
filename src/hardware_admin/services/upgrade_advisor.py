"""Asesores locales y conservadores para ampliaciones de hardware.

No consulta tiendas, manuales ni servicios externos.  El inventario de Windows
aporta hechos locales y las comprobaciones físicas/documentales las declara el
usuario.  Por eso una ausencia de dato siempre queda como pendiente: nunca se
convierte en una compatibilidad inventada.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from hardware_admin.domain.models import ComponentKind, ComponentResult, HealthStatus

PENDING = "PENDIENTE DE VERIFICACIÓN"
DECLARED_COMPATIBLE = "COMPATIBLE SEGÚN DATOS DECLARADOS"
DECLARED_INCOMPATIBLE = "NO COMPATIBLE SEGÚN DATOS DECLARADOS"
CONTRADICTORY = "DATOS CONTRADICTORIOS"


@dataclass(frozen=True, slots=True)
class UpgradePreferences:
    """Contexto voluntario, mantenido solamente en memoria durante la sesión."""

    goal: str = ""
    budget: str = ""
    currency: str = ""
    equipment_form: str = "No indicado"
    ram_manual_reference: str = ""
    ram_verified_max_gb: str = ""
    ram_total_slots: str = ""
    ram_soldered: str = "No indicado"
    ssd_mode: str = "Añadir"
    ssd_target: str = ""
    ssd_target_capacity: str = ""
    ssd_target_protocol: str = ""
    ssd_target_form_factor: str = ""
    ssd_supported_protocols: str = ""
    ssd_supported_form_factors: str = ""
    ssd_available_bays_or_slots: str = ""
    ssd_manual_reference: str = ""
    gpu_target: str = ""
    gpu_required_psu_watts: str = ""
    gpu_required_connectors: str = ""
    gpu_length_mm: str = ""
    gpu_current_psu_watts: str = ""
    gpu_current_connectors: str = ""
    gpu_clearance_mm: str = ""
    gpu_pcie_slot_note: str = ""
    gpu_manual_reference: str = ""

    def public_context(self) -> dict[str, str]:
        """Devuelve únicamente los datos declarados que explican una conclusión."""

        return {key: value for key, value in asdict(self).items() if str(value).strip()}


def _result_for(
    results: Iterable[ComponentResult], component: ComponentKind
) -> ComponentResult | None:
    return next((item for item in results if item.component is component), None)


def _number(value: object) -> float | None:
    try:
        number = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _contains_declared(values: str, expected: str) -> bool:
    return bool(expected.strip()) and expected.casefold().strip() in values.casefold()


# Factores de forma SMBIOS DMTF de chips soldados
_SOLDERED_FORM_FACTORS = {
    "TSOP",
    "SMD",
    "SSMP",
    "QFP",
    "TQFP",
    "SOIC",
    "BGA",
    "FPBGA",
    "LGA",
    "DIP",
    "SIP",
    "SOJ",
}


def _machine_identification(results: Iterable[ComponentResult]) -> str | None:
    system = _result_for(results, ComponentKind.SYSTEM)
    if system is None:
        return None
    parts: list[str] = []
    mfg = str(system.facts.get("Fabricante") or "").strip()
    model = str(system.facts.get("Modelo") or "").strip()
    board = str(system.facts.get("Placa base") or "").strip()
    bios = str(system.facts.get("BIOS / UEFI") or "").strip()

    if mfg and mfg.lower() not in {"no disponible", "system manufacturer", "to be filled by o.e.m."}:
        parts.append(mfg)
    if model and model.lower() not in {"no disponible", "system product name", "to be filled by o.e.m."}:
        parts.append(model)
    if board and board.lower() not in {"no disponible"}:
        parts.append(f"Placa base: {board}")
    if bios and bios.lower() not in {"no disponible"}:
        parts.append(f"BIOS: {bios}")

    return " · ".join(parts) if parts else None


def _memory_inventory(memory: ComponentResult | None) -> tuple[float | None, int, list[str], list[str]]:
    if memory is None:
        return None, 0, [], []
    raw = memory.facts.get("_memoria")
    total_bytes = raw.get("total") if isinstance(raw, dict) else None
    total_gb = float(total_bytes) / (1024**3) if isinstance(total_bytes, (int, float)) else None
    modules = memory.facts.get("Módulos físicos")
    if not isinstance(modules, list):
        return total_gb, 0, [], []
    details = []
    form_factors: list[str] = []
    for module in modules:
        if isinstance(module, dict):
            slot = str(module.get("Ranura") or "Ranura no identificada")
            capacity = str(module.get("Capacidad") or "No disponible")
            memory_type = str(module.get("Tipo / Generación") or "No disponible")
            ff = str(module.get("Factor de forma") or "No disponible")
            form_factors.append(ff)
            details.append(f"{slot}: {capacity} · {memory_type} ({ff})")
    return total_gb, len(modules), details, form_factors


def _ram_advice(results: Iterable[ComponentResult], preferences: UpgradePreferences) -> dict[str, Any]:
    memory = _result_for(results, ComponentKind.MEMORY)
    installed_gb, occupied_slots, modules, module_ffs = _memory_inventory(memory)
    facts: list[str] = []

    machine_id = _machine_identification(results)
    if machine_id:
        facts.append(f"Equipo identificado: {machine_id} (inventario de Windows)")
    elif preferences.ram_manual_reference.strip():
        facts.append(f"Referencia documental: {preferences.ram_manual_reference.strip()} (declarado por usted)")
    else:
        facts.append("Identificación de placa/equipo: no disponible (inventario de Windows incompleto)")

    if installed_gb is not None:
        facts.append(f"RAM detectada: {installed_gb:.1f} GB (inventario de Windows)")
    if modules:
        facts.append(f"Módulos detectados ({len(modules)}): {', '.join(modules)} (inventario de Windows)")

    # Ranuras firmware
    firmware_slots_val = memory.facts.get("Ranuras RAM reportadas por firmware") if memory else None
    fw_slots: int | None = None
    if isinstance(firmware_slots_val, int) and firmware_slots_val > 0:
        fw_slots = firmware_slots_val
        facts.append(f"Ranuras reportadas por firmware: {fw_slots} (inventario de Windows)")
    elif preferences.ram_total_slots.strip():
        declared_slots_num = _number(preferences.ram_total_slots)
        if declared_slots_num is not None:
            facts.append(f"Ranuras totales verificadas: {int(declared_slots_num)} (declarado por usted)")
        else:
            facts.append("Ranuras totales verificadas: dato declarado no válido")

    # Máximo firmware
    firmware_info = memory.facts.get("_ampliacion_ram") if memory is not None else None
    fw_max_gb: float | None = None
    if isinstance(firmware_info, dict):
        firmware_max = firmware_info.get("maximo_firmware_bytes")
        firmware_margin = firmware_info.get("margen_teorico_bytes")
        if isinstance(firmware_max, (int, float)) and firmware_max > 0:
            fw_max_gb = float(firmware_max) / (1024**3)
            facts.append(f"Máximo reportado por firmware: {fw_max_gb:.1f} GB (inventario de Windows)")
        if isinstance(firmware_margin, (int, float)) and firmware_margin >= 0:
            facts.append(f"Margen teórico según firmware: {float(firmware_margin) / (1024**3):.1f} GB (inventario de Windows)")

    # Máximo declarado (si existe)
    declared_max_gb = _number(preferences.ram_verified_max_gb)
    if declared_max_gb is not None:
        facts.append(f"Máximo documentado declarado: {declared_max_gb:.1f} GB (declarado por usted)")

    # Indicio de soldadura por formato SMBIOS
    has_soldered_modules = any(ff in _SOLDERED_FORM_FACTORS for ff in module_ffs)
    if has_soldered_modules:
        facts.append("Indicio de memoria integrada/soldada por encapsulado SMBIOS (inventario de Windows; confirme con el fabricante)")
    elif preferences.ram_soldered != "No indicado":
        facts.append(f"Memoria soldada: {preferences.ram_soldered} (declarado por usted)")

    missing: list[str] = []
    if memory is None:
        missing.append("Ejecutar el análisis de RAM para obtener el inventario SMBIOS.")

    # Ranuras: si el firmware no las reporta y el usuario no las declaró -> pendiente con motivo
    effective_slots = _number(preferences.ram_total_slots) if preferences.ram_total_slots.strip() else (float(fw_slots) if fw_slots is not None else None)
    if effective_slots is None or effective_slots <= 0:
        missing.append("Número total de ranuras de memoria no reportado por firmware ni declarado en manual OEM.")

    # Máximo: si firmware no reporta y usuario no declara -> pendiente
    effective_max = declared_max_gb if declared_max_gb is not None else fw_max_gb
    if effective_max is None:
        missing.append("Capacidad máxima de RAM no reportada por firmware ni declarada en manual OEM.")

    # Memoria soldada: si no indicada
    if preferences.ram_soldered == "No indicado" and not has_soldered_modules:
        missing.append("Si la memoria está soldada, ampliable o parcialmente soldada.")

    # Comprobación de contradicción
    contradiction_reason: str | None = None
    if installed_gb is not None and effective_max is not None and effective_max < installed_gb:
        contradiction_reason = (
            f"El máximo reportado o declarado ({effective_max:.1f} GB) es menor que la RAM detectada ({installed_gb:.1f} GB). "
            "Revise modelo, revisión y unidad del manual antes de decidir una ampliación."
        )
    elif effective_slots is not None and effective_slots < occupied_slots:
        contradiction_reason = (
            f"Las ranuras totales ({int(effective_slots)}) son menos que los módulos detectados ({occupied_slots}); "
            "revise la evidencia física."
        )

    if contradiction_reason is not None:
        status = CONTRADICTORY
        conclusion = contradiction_reason
    elif preferences.ram_soldered == "Sí" or has_soldered_modules:
        status = PENDING
        conclusion = (
            "Hay indicio o declaración de memoria soldada. No se afirma que pueda añadirse o sustituirse RAM "
            "sin la configuración exacta admitida por el fabricante."
        )
    elif not missing and installed_gb is not None and effective_max is not None and effective_slots is not None:
        if effective_max == installed_gb:
            status = DECLARED_COMPATIBLE
            conclusion = (
                "La configuración actual coincide con el máximo documentado; una ampliación no "
                "queda justificada sin revisar configuraciones alternativas del manual."
            )
        else:
            status = DECLARED_COMPATIBLE
            conclusion = (
                f"El margen aritmético es {effective_max - installed_gb:.1f} GB. No equivale "
                "a un módulo que se pueda añadir: confirme kit, capacidad por ranura y si hay que sustituir módulos."
            )
    else:
        status = PENDING
        conclusion = (
            "El inventario local describe lo instalado, pero no certifica capacidad máxima, ranuras "
            "libres ni la configuración admitida."
        )

    return {
        "titulo": "Compatibilidad y ampliación de RAM",
        "estado": status,
        "hechos": facts or ["Sin inventario de RAM para esta sesión."],
        "conclusion": conclusion,
        "comprobaciones_pendientes": missing,
        "antes_de_comprar": [
            "Confirmar modelo y revisión exactos en el manual OEM.",
            "Comprobar DDR, formato, ECC/buffering y las configuraciones admitidas.",
            "No asumir doble canal, XMP/EXPO ni una velocidad comercial garantizada.",
        ],
    }


def _storage_advice(results: Iterable[ComponentResult], preferences: UpgradePreferences) -> dict[str, Any]:
    storage = _result_for(results, ComponentKind.DISK)
    system = _result_for(results, ComponentKind.SYSTEM)
    facts: list[str] = []

    machine_id = _machine_identification(results)
    if machine_id:
        facts.append(f"Equipo identificado: {machine_id} (inventario de Windows)")
    elif preferences.ssd_manual_reference.strip():
        facts.append(f"Referencia documental: {preferences.ssd_manual_reference.strip()} (declarado por usted)")
    else:
        facts.append("Identificación de placa/equipo: no disponible (inventario de Windows incompleto)")

    has_nvme_disk = False
    if storage is not None:
        physical = storage.facts.get("Discos físicos")
        if isinstance(physical, list):
            for disk in physical:
                if isinstance(disk, dict):
                    bus = str(disk.get("Bus") or "")
                    if "NVME" in bus.upper():
                        has_nvme_disk = True
                    facts.append(
                        " · ".join(
                            str(disk.get(key) or "No disponible")
                            for key in ("Dispositivo", "Tipo de medio", "Bus", "Capacidad")
                        ) + " (inventario de Windows)"
                    )

    if has_nvme_disk:
        facts.append("Se detecta una unidad NVMe activa en el inventario; el equipo admite el bus NVMe de facto (inventario de Windows)")

    # Inspección de ranuras del sistema Win32_SystemSlot como indicio
    system_slots = system.facts.get("Ranuras del sistema (Win32_SystemSlot)") if system else None
    if isinstance(system_slots, list) and system_slots:
        slot_summaries = [
            f"{s.get('Ranura', 'Ranura')}: uso={s.get('Uso actual', 'No disponible')}, estado={s.get('Estado', 'No disponible')}"
            for s in system_slots
            if isinstance(s, dict)
        ]
        facts.append(
            f"Ranuras del sistema (Win32_SystemSlot) como indicio: {', '.join(slot_summaries)} "
            "(inventario de Windows; no certifica bahía física ni ranura M.2 libre)"
        )

    # Campos objetivo declarados
    if preferences.ssd_target.strip():
        facts.append(f"SSD objetivo: {preferences.ssd_target.strip()} (declarado por usted)")
    if preferences.ssd_target_capacity.strip():
        facts.append(f"Capacidad objetivo: {preferences.ssd_target_capacity.strip()} (declarado por usted)")
    if preferences.ssd_target_protocol.strip():
        facts.append(f"Protocolo objetivo: {preferences.ssd_target_protocol.strip()} (declarado por usted)")
    if preferences.ssd_target_form_factor.strip():
        facts.append(f"Formato objetivo: {preferences.ssd_target_form_factor.strip()} (declarado por usted)")

    # 4 comprobaciones pendientes declaradas
    missing: list[str] = []
    if storage is None:
        missing.append("Ejecutar el análisis de almacenamiento para identificar la unidad actual.")
    if not preferences.ssd_target.strip():
        missing.append("Modelo o familia del SSD objetivo.")
    if not preferences.ssd_target_capacity.strip():
        missing.append("Capacidad objetivo de almacenamiento (por ejemplo, 2 TB).")
    if not preferences.ssd_target_protocol.strip():
        missing.append("Protocolo del SSD objetivo (por ejemplo, NVMe o SATA).")
    if not preferences.ssd_target_form_factor.strip():
        missing.append("Formato y dimensiones del SSD objetivo (por ejemplo, M.2 2280 o 2.5 pulgadas).")

    # En modo Añadir, si ya se indicaron datos del objetivo pero no la ranura/bahía libre
    if preferences.ssd_mode == "Añadir" and preferences.ssd_target.strip() and not preferences.ssd_available_bays_or_slots.strip():
        missing.append("Bahía o ranura libre verificada en manual OEM o inspección física; Windows no puede inferirla.")

    target_protocol = preferences.ssd_target_protocol.strip()
    target_form = preferences.ssd_target_form_factor.strip()

    # Contradicción / Incompatibilidad demostrada
    protocol_incompatible = False
    if target_protocol and preferences.ssd_supported_protocols.strip():
        protocol_incompatible = not _contains_declared(preferences.ssd_supported_protocols, target_protocol)

    form_incompatible = False
    if target_form and preferences.ssd_supported_form_factors.strip():
        form_incompatible = not _contains_declared(preferences.ssd_supported_form_factors, target_form)

    if protocol_incompatible or form_incompatible:
        status = DECLARED_INCOMPATIBLE
        conclusion = (
            "Los protocolos o formatos declarados para la ranura no incluyen el SSD objetivo. "
            "Revise ambos modelos exactos antes de comprar."
        )
    elif not missing:
        status = DECLARED_COMPATIBLE
        conclusion = (
            "La coincidencia se basa en los datos documentales declarados y el inventario. Planifique respaldo y "
            "traslado de datos; la aplicación no clona, particiona ni formatea unidades."
        )
    else:
        status = PENDING
        conclusion = (
            "El tipo de unidad detectado por Windows no revela por sí mismo una bahía/ranura libre ni permite "
            "garantizar compatibilidad física sin el modelo o formato objetivo."
        )

    return {
        "titulo": "Compatibilidad de SSD",
        "estado": status,
        "modo": preferences.ssd_mode,
        "capacidad_objetivo": preferences.ssd_target_capacity or "No indicada",
        "hechos": facts or ["Sin inventario de almacenamiento para esta sesión."],
        "conclusion": conclusion,
        "comprobaciones_pendientes": missing,
        "antes_de_comprar": [
            "Distinguir añadir capacidad de reemplazar la unidad actual.",
            "Confirmar protocolo, formato, longitud, bahía/ranura y accesorios necesarios.",
            "Preparar una copia de seguridad antes de cualquier traslado manual de datos.",
        ],
    }


def _gpu_advice(results: Iterable[ComponentResult], preferences: UpgradePreferences) -> dict[str, Any]:
    gpu = _result_for(results, ComponentKind.MONITOR_GPU)
    detected: list[str] = []
    facts: list[str] = []

    machine_id = _machine_identification(results)
    if machine_id:
        facts.append(f"Equipo identificado: {machine_id} (inventario de Windows)")
    elif preferences.gpu_manual_reference.strip():
        facts.append(f"Referencia documental: {preferences.gpu_manual_reference.strip()} (declarado por usted)")
    else:
        facts.append("Identificación de placa/equipo: no disponible (inventario de Windows incompleto)")

    if gpu is not None:
        adapters = gpu.facts.get("Adaptadores de vídeo (GPU)")
        if isinstance(adapters, list):
            for item in adapters:
                if isinstance(item, dict):
                    name = str(item.get("Nombre") or "GPU no identificada")
                    detected.append(name)
                    facts.append(f"GPU detectada: {name} (inventario de Windows)")

    if preferences.gpu_target.strip():
        facts.append(f"GPU objetivo: {preferences.gpu_target.strip()} (declarado por usted)")

    missing: list[str] = []
    if gpu is None:
        missing.append("Ejecutar el análisis de GPU/vídeo para obtener el inventario actual.")
    if not preferences.gpu_target.strip():
        missing.append("Modelo/SKU exacto de la GPU objetivo.")
    if not preferences.gpu_manual_reference.strip():
        missing.append("Especificación de la GPU objetivo y manual del equipo/gabinete.")
    for value, label in (
        (preferences.gpu_required_psu_watts, "Potencia mínima recomendada para la GPU objetivo (W)."),
        (preferences.gpu_required_connectors, "Conectores de alimentación requeridos por la GPU objetivo."),
        (preferences.gpu_length_mm, "Longitud de la GPU objetivo (mm)."),
        (preferences.gpu_current_psu_watts, "Potencia real de la fuente instalada (W)."),
        (preferences.gpu_current_connectors, "Conectores PCIe realmente disponibles en la fuente."),
        (preferences.gpu_clearance_mm, "Espacio útil del gabinete hasta la GPU (mm)."),
        (preferences.gpu_pcie_slot_note, "Ranura PCIe y restricciones físicas documentadas."),
    ):
        if not str(value).strip():
            missing.append(label)

    required_watts = _number(preferences.gpu_required_psu_watts)
    current_watts = _number(preferences.gpu_current_psu_watts)
    target_length = _number(preferences.gpu_length_mm)
    clearance = _number(preferences.gpu_clearance_mm)
    connector_ok = (
        _contains_declared(preferences.gpu_current_connectors, preferences.gpu_required_connectors)
        if preferences.gpu_current_connectors.strip() and preferences.gpu_required_connectors.strip()
        else None
    )

    power_incompatible = current_watts is not None and required_watts is not None and current_watts < required_watts
    clearance_incompatible = clearance is not None and target_length is not None and clearance < target_length
    connector_incompatible = connector_ok is False

    if preferences.equipment_form == "Portátil":
        status = PENDING
        conclusion = (
            "Una GPU interna de portátil no se declara reemplazable por detectarse en Windows. "
            "Confirme expresamente soporte OEM para el modelo exacto."
        )
    elif power_incompatible or clearance_incompatible or connector_incompatible:
        status = DECLARED_INCOMPATIBLE
        conclusion = (
            "La fuente, conectores o espacio declarados no alcanzan el requisito de la GPU objetivo. "
            "No se recomienda comprarla con estos datos."
        )
    elif not missing:
        if any(value is None for value in (required_watts, current_watts, target_length, clearance)):
            status = PENDING
            conclusion = "Las medidas o la potencia declaradas no son números válidos; revíselas."
        else:
            status = DECLARED_COMPATIBLE
            conclusion = (
                "Fuente, conectores, espacio y ranura cumplen según los datos declarados. Confirme SKU, "
                "cableado y requisitos del fabricante antes de instalar; Windows no verifica estabilidad eléctrica."
            )
    else:
        status = PENDING
        conclusion = (
            "El inventario de Windows identifica la GPU actual, pero no verifica fuente, cableado, espacio "
            "ni compatibilidad completa de una tarjeta futura."
        )

    return {
        "titulo": "Compatibilidad de GPU, fuente y espacio",
        "estado": status,
        "hechos": facts or ["Sin inventario de GPU para esta sesión."],
        "conclusion": conclusion,
        "comprobaciones_pendientes": missing,
        "antes_de_comprar": [
            "Confirmar el SKU exacto de la tarjeta, no sólo el nombre comercial.",
            "Revisar fuente, conectores, cableado y medidas del gabinete.",
            "No interpretar una generación PCIe distinta como incompatibilidad automática.",
        ],
    }


def _maximum_usage(result: ComponentResult | None, key: str) -> float | None:
    if result is None:
        return None
    value = result.facts.get(key)
    if isinstance(value, (float, int)):
        return float(value)
    return None


def _priority_advice(
    results: Iterable[ComponentResult],
    preferences: UpgradePreferences,
    ram: dict[str, Any],
    storage: dict[str, Any],
    gpu: dict[str, Any],
) -> dict[str, Any]:
    result_list = tuple(results)
    memory = _result_for(result_list, ComponentKind.MEMORY)
    disk = _result_for(result_list, ComponentKind.DISK)
    gpu_result = _result_for(result_list, ComponentKind.MONITOR_GPU)
    actions: list[dict[str, str]] = [
        {
            "orden": "1",
            "área": "Sin compra",
            "acción": "Confirmar el síntoma y las comprobaciones pendientes antes de gastar.",
            "fundamento": "Es la alternativa válida cuando la evidencia o la compatibilidad no están completas.",
        }
    ]
    memory_usage = _maximum_usage(memory, "_uso")
    disk_usage = max(
        (
            _number(item.get("porcentaje")) or 0.0
            for item in (disk.facts.get("_volumenes", []) if disk else [])
            if isinstance(item, dict)
        ),
        default=0.0,
    )
    if memory_usage is not None and memory_usage >= 90:
        actions.append(
            {
                "orden": str(len(actions) + 1),
                "área": "RAM",
                "acción": "Medir si la presión de memoria se repite con el uso habitual.",
                "fundamento": f"Uso de RAM observado: {memory_usage:.1f}%. Estado del asesor: {ram['estado']}.",
            }
        )
    if disk_usage >= 85:
        actions.append(
            {
                "orden": str(len(actions) + 1),
                "área": "Almacenamiento",
                "acción": "Liberar espacio y decidir si hace falta ampliar capacidad o reemplazar la unidad.",
                "fundamento": f"Máximo uso de volumen observado: {disk_usage:.1f}%. Estado del asesor: {storage['estado']}.",
            }
        )
    if gpu_result is not None and gpu_result.status in {HealthStatus.WARNING, HealthStatus.CRITICAL}:
        actions.append(
            {
                "orden": str(len(actions) + 1),
                "área": "GPU",
                "acción": "Resolver primero la advertencia observada y repetir la medición antes de plantear una GPU nueva.",
                "fundamento": f"El inventario actual tiene estado {gpu_result.status.value}. Estado del asesor: {gpu['estado']}.",
            }
        )

    context_missing = []
    if not preferences.goal.strip():
        context_missing.append("Objetivo de uso (por ejemplo, oficina, edición o juego y resolución).")
    if not preferences.budget.strip():
        context_missing.append("Presupuesto total y moneda; un precio desconocido no equivale a cero.")

    return {
        "titulo": "Qué conviene actualizar primero",
        "estado": PENDING if context_missing else "ORIENTACIÓN CON EVIDENCIA PARCIAL",
        "acciones": actions,
        "conclusion": (
            "No hay una prioridad de compra demostrada sin objetivo, presupuesto y compatibilidades completas. "
            "La lista ordena comprobaciones y decisiones, no promete beneficios universales."
        ),
        "comprobaciones_pendientes": context_missing,
        "alternativa_sin_compra": "Mantener el equipo actual, confirmar el síntoma y repetir mediciones comparables.",
    }


def build_upgrade_advice(
    results: Iterable[ComponentResult], preferences: UpgradePreferences | None = None
) -> dict[str, Any]:
    """Compone las cuatro fichas de asesoría sin acceder a Windows, red o tiendas."""

    result_list = tuple(results)
    preferences = preferences or UpgradePreferences()
    ram = _ram_advice(result_list, preferences)
    storage = _storage_advice(result_list, preferences)
    gpu = _gpu_advice(result_list, preferences)
    priority = _priority_advice(result_list, preferences, ram, storage, gpu)
    return {
        "schema_version": "1.0",
        "origen": "Reglas locales; inventario Windows y datos declarados por el usuario durante esta sesión.",
        "contexto_declarado": preferences.public_context(),
        "ram": ram,
        "ssd": storage,
        "gpu": gpu,
        "priorización": priority,
        "limitaciones": [
            "No se consulta Internet, catálogos, precios ni disponibilidad.",
            "No se compran componentes ni se modifica BIOS, controladores, discos o configuración.",
            "Los datos declarados por el usuario requieren confirmación contra el modelo/SKU y manual exactos.",
        ],
    }


def format_upgrade_advice(advice: dict[str, Any]) -> str:
    """Representación estable para la vista de recomendaciones y el TXT."""

    if not advice:
        return "ASESOR DE AMPLIACIONES\n=======================\nSin datos de esta sesión."
    lines = ["ASESOR DE AMPLIACIONES", "=======================", "", str(advice.get("origen", "")), ""]
    for key in ("ram", "ssd", "gpu", "priorización"):
        section = advice.get(key)
        if not isinstance(section, dict):
            continue
        lines.extend(
            [
                str(section.get("titulo", key)).upper(),
                "-" * len(str(section.get("titulo", key))),
                f"Estado: {section.get('estado', PENDING)}",
            ]
        )
        for fact in section.get("hechos", []):
            lines.append(f"  · {fact}")
        for action in section.get("acciones", []):
            if isinstance(action, dict):
                lines.append(f"  {action.get('orden')}. {action.get('área')}: {action.get('acción')}")
                lines.append(f"     {action.get('fundamento')}")
        lines.extend(["", str(section.get("conclusion", ""))])
        pending = section.get("comprobaciones_pendientes", [])
        if pending:
            lines.append("Pendiente:")
            lines.extend(f"  - {item}" for item in pending)
        if section.get("alternativa_sin_compra"):
            lines.append(f"Alternativa sin compra: {section['alternativa_sin_compra']}")
        lines.append("")
    limitations = advice.get("limitaciones", [])
    if limitations:
        lines.extend(["LÍMITES", "-------"])
        lines.extend(f"  - {item}" for item in limitations)
    return "\n".join(lines)
