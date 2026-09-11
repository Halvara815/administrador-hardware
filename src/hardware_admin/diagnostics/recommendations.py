"""Procedimientos correctivos derivados del estado ya clasificado.

Este módulo no consulta Windows ni psutil: lee `ComponentResult` y decide, de
modo que se puede comprobar entero sin hardware. Tampoco reinterpreta
porcentajes; parte del estado que asignaron las reglas centrales, para que una
recomendación nunca contradiga lo que muestra la matriz.

Ninguna recomendación se ejecuta. Las que alteran el equipo van marcadas con
`modifies_system=True` para que el usuario sepa qué va a cambiar antes de
escribir el comando él mismo.
"""

from __future__ import annotations

from collections.abc import Sequence

from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    HealthStatus,
    Recommendation,
)

#: Orden de presentación: lo confirmado primero, lo no concluyente al final.
_SEVERITY_ORDER: dict[HealthStatus, int] = {
    HealthStatus.CRITICAL: 0,
    HealthStatus.WARNING: 1,
    HealthStatus.ERROR: 2,
    HealthStatus.UNKNOWN: 3,
    HealthStatus.NORMAL: 4,
}

_ALERTS = {HealthStatus.WARNING, HealthStatus.CRITICAL}


def _case(result: ComponentResult) -> str:
    return str(result.facts.get("Caso", ""))


def _cpu(result: ComponentResult) -> Recommendation:
    prob = (result.possible_problem or "").lower()
    if "térmic" in prob or "temperatura" in prob:
        return Recommendation(
            component=ComponentKind.CPU,
            title="Monitorear temperatura y refrigeración de CPU",
            cause=f"Se detectó temperatura elevada en CPU: {result.possible_problem or result.summary}.",
            steps=(
                "Comprobar que las rejillas de ventilación no estén obstruidas y que el flujo de aire sea adecuado.",
                "Verificar que los ventiladores giren de forma continua bajo carga.",
                "Cerrar procesos en segundo plano que mantengan alta exigencia de procesamiento.",
                "Si la temperatura se mantiene crítica de forma persistente, consultar con un servicio técnico calificado.",
            ),
            rationale=(
                "Una temperatura elevada sostenida reduce el rendimiento por protección térmica. "
                "No se deben realizar acciones invasivas de hardware de forma automática."
            ),
            verification="Monitorear el equipo en reposo y comprobar si la temperatura desciende a valores normales.",
        )
    return Recommendation(
        component=ComponentKind.CPU,
        title="Revisar la carga del procesador",
        cause=f"El uso de CPU está en {result.summary}, por encima del umbral normal.",
        steps=(
            "Abrir el Administrador de tareas con Ctrl+Mayús+Esc.",
            "Ordenar la pestaña Procesos por la columna CPU, de mayor a menor.",
            "Identificar el proceso que sostiene la carga y comprobar si es esperado.",
            "Revisar en la pestaña Inicio los programas que arrancan con el equipo.",
        ),
        rationale=(
            "Una carga sostenida de CPU degrada la respuesta del sistema sin implicar "
            "avería del procesador. La clasificación proviene de la regla de uso, no "
            "de una prueba de daño físico."
        ),
        verification="Repetir el análisis y comprobar que el uso baja del 70 %.",
    )


def _memory(result: ComponentResult) -> Recommendation:
    return Recommendation(
        component=ComponentKind.MEMORY,
        title="Liberar memoria RAM",
        cause=f"La memoria en uso está en {result.summary}, con poca disponible.",
        steps=(
            "Cerrar las aplicaciones que no estén en uso.",
            "Revisar en el Administrador de tareas los procesos con más memoria.",
            "Desactivar del inicio los programas que no necesite al arrancar.",
            "Si la situación se repite a diario, valorar ampliar la memoria instalada.",
        ),
        rationale=(
            "Con poca memoria disponible el sistema recurre al archivo de paginación "
            "en disco, mucho más lento que la RAM. Ampliar sólo se justifica si la "
            "saturación es recurrente, no por una medición puntual."
        ),
        verification="Repetir el análisis con las aplicaciones habituales abiertas.",
    )


def _disk(result: ComponentResult) -> Recommendation:
    if "salud física" in (result.possible_problem or "").lower():
        return Recommendation(
            component=ComponentKind.DISK,
            title="Revisar estado físico del disco y realizar copia de seguridad",
            cause=result.possible_problem or "Alerta de estado operativo o salud física en el disco.",
            steps=(
                "Realizar una copia de seguridad inmediata de los datos importantes.",
                "Consultar los eventos de disco en el Visor de eventos de Windows (ID 7, 11 o 51).",
                "Verificar la garantía y ejecutar la herramienta de diagnóstico oficial del fabricante.",
                "Evitar operaciones de escritura intensivas hasta asegurar el respaldo.",
            ),
            rationale=(
                "El controlador de almacenamiento o Windows reporta que la unidad física no se "
                "encuentra en estado completamente saludable, lo que puede anticipar fallos graves."
            ),
            verification="Comprobar el estado físico del disco con la utilidad del fabricante.",
        )
    return Recommendation(
        component=ComponentKind.DISK,
        title="Liberar espacio en disco",
        cause=result.possible_problem or f"Ocupación elevada: {result.summary}.",
        steps=(
            "Abrir Configuración > Sistema > Almacenamiento para ver qué ocupa espacio.",
            "Ejecutar el Liberador de espacio y vaciar la papelera de reciclaje.",
            "Desinstalar aplicaciones que ya no utilice.",
            "Mover a otra unidad o a un medio externo los archivos grandes que conserve.",
        ),
        rationale=(
            "Un volumen casi lleno impide actualizaciones, archivos temporales y "
            "paginación, y degrada el rendimiento antes de agotarse por completo. "
            "La ocupación es una medida de espacio, no un indicio de daño físico."
        ),
        verification="Repetir el análisis y comprobar que la unidad baja del 85 % ocupado.",
    )


def _usb_without_volume(result: ComponentResult) -> Recommendation:
    return Recommendation(
        component=ComponentKind.DISK,
        title="Recuperar el acceso a un medio USB sin volumen",
        cause=result.possible_problem or "Medio USB presente y sano, pero sin volumen accesible.",
        steps=(
            "Abrir Administración de discos con Win+X.",
            "Localizar el disco USB y comprobar si tiene una partición sin letra.",
            "Asignar una letra de unidad con «Cambiar letra y rutas de acceso».",
            (
                "Si aparece como RAW o sin particiones, probarlo en otro puerto u otro "
                "equipo antes de dar por perdido su contenido."
            ),
        ),
        rationale=(
            "Windows informa el medio como sano, así que el problema está en la "
            "detección o la configuración del volumen, no en el bus USB ni en el "
            "estado físico del medio."
        ),
        verification="Comprobar que la unidad aparece en el Explorador con letra asignada.",
        modifies_system=True,
    )


def _apipa(result: ComponentResult) -> Recommendation:
    return Recommendation(
        component=ComponentKind.NETWORK,
        title="Recuperar la concesión DHCP",
        cause=(
            result.possible_problem
            or "El adaptador tiene una dirección APIPA (169.254.x.x) y no hay puerta de enlace."
        ),
        steps=(
            "Comprobar que el cable de red está conectado o que el Wi-Fi está asociado.",
            "Reiniciar el router y esperar a que complete el arranque.",
            "Ejecutar «ipconfig /all» en una consola para ver el estado del adaptador.",
            (
                "Ejecutar «ipconfig /release» y después «ipconfig /renew» para pedir "
                "una dirección nueva al servidor DHCP."
            ),
        ),
        rationale=(
            "Una dirección 169.254.x.x indica que Windows se autoasignó una dirección "
            "porque ningún servidor DHCP respondió. El equipo puede estar sano y aun "
            "así quedar sin red local."
        ),
        verification="Repetir el análisis y comprobar que el adaptador obtiene IP y puerta de enlace.",
        modifies_system=True,
    )


def _dns(result: ComponentResult) -> Recommendation:
    return Recommendation(
        component=ComponentKind.NETWORK,
        title="Restablecer la resolución de nombres",
        cause=result.possible_problem or "Hay conectividad IP, pero la resolución DNS falla.",
        steps=(
            "Comprobar los servidores DNS configurados con «ipconfig /all».",
            "Ejecutar «ipconfig /flushdns» para vaciar la caché de resolución.",
            "Probar la resolución con «nslookup google.com».",
            (
                "Si persiste, configurar temporalmente un DNS alternativo conocido y "
                "repetir la prueba."
            ),
        ),
        rationale=(
            "Que responda una IP externa y falle el nombre sitúa el problema en la "
            "resolución, no en la conectividad física ni en el adaptador."
        ),
        verification="Comprobar que «nslookup google.com» devuelve una dirección.",
        modifies_system=True,
    )


def _pci_nic(result: ComponentResult) -> Recommendation:
    return Recommendation(
        component=ComponentKind.PCI,
        title="Revisar el adaptador de red PCIe",
        cause=result.possible_problem or "Un adaptador de red PCIe presenta un código de error.",
        steps=(
            "Abrir el Administrador de dispositivos y localizar el adaptador marcado.",
            "Anotar el código de error que muestra en sus propiedades.",
            (
                "Con el equipo apagado y desconectado, comprobar que la tarjeta está "
                "bien insertada en su ranura PCIe."
            ),
            "Actualizar el controlador desde la web del fabricante si el código lo justifica.",
            "Reiniciar y repetir el análisis.",
        ),
        rationale=(
            "El resto de dispositivos se reporta con normalidad, así que el problema "
            "está localizado en ese adaptador y no en el bus PCIe completo."
        ),
        verification="Repetir el análisis y comprobar que el dispositivo deja de reportar error.",
        modifies_system=True,
    )


def _usb_peripheral(result: ComponentResult) -> Recommendation:
    return Recommendation(
        component=ComponentKind.USB,
        title="Revisar el periférico USB con error",
        cause=result.possible_problem or "Un periférico USB reporta error con el bus operativo.",
        steps=(
            "Desconectar el periférico y probarlo en otro puerto USB.",
            "Probarlo en otro equipo para separar el fallo del periférico del de este equipo.",
            "Revisar su código de error en el Administrador de dispositivos.",
            "Reinstalar el controlador específico del periférico si el código lo indica.",
        ),
        rationale=(
            "El controlador anfitrión USB funciona correctamente, de modo que el bus "
            "no está degradado: la falla es del periférico concreto y no procede "
            "condenar el resto de dispositivos conectados."
        ),
        verification="Comprobar que el periférico deja de aparecer con error tras reconectarlo.",
        modifies_system=True,
    )


def _generic(result: ComponentResult) -> Recommendation:
    return Recommendation(
        component=result.component,
        title=f"Revisar {result.name}",
        cause=result.possible_problem or f"El componente reporta: {result.summary}.",
        steps=(
            "Abrir el Administrador de dispositivos y localizar el elemento afectado.",
            "Consultar el estado y el código que informa Windows en sus propiedades.",
            "Comprobar si existe un controlador más reciente del fabricante.",
        ),
        rationale=(
            "El estado proviene de lo que informa Windows sobre el dispositivo; "
            "conviene confirmarlo antes de sustituir hardware."
        ),
        verification="Repetir el análisis y comparar el estado del componente.",
    )


def _failed_query(result: ComponentResult) -> Recommendation:
    return Recommendation(
        component=result.component,
        title=f"Repetir la consulta de {result.name}",
        cause=result.possible_problem or "La consulta no pudo completarse.",
        steps=(
            "Cerrar la aplicación y volver a abrirla con permiso de administrador.",
            "Repetir el análisis de esa sección concreta.",
            "Si vuelve a fallar, anotar el detalle del error que muestra la evidencia técnica.",
        ),
        rationale=(
            "Una consulta que no se completa deja el componente sin evaluar. Un dato "
            "ausente no equivale a hardware sano, así que no debe interpretarse como "
            "ausencia de problemas."
        ),
        verification="Comprobar que la sección deja de reportar error de consulta.",
    )


def _symptom(symptom: str) -> Recommendation:
    return Recommendation(
        component=ComponentKind.SYSTEM,
        title="Ampliar el diagnóstico ante un síntoma persistente",
        cause=(
            "El usuario reporta un síntoma que persiste aunque los indicadores "
            "consultados no muestran anomalías."
        ),
        steps=(
            "Vigilar la temperatura de CPU y GPU durante el uso que provoca el síntoma.",
            "Revisar la capacidad y el estado de la fuente de alimentación.",
            "Revisar el Visor de eventos de Windows en torno a la hora del incidente.",
            "Comprobar la memoria RAM con la herramienta de diagnóstico de Windows.",
            "Actualizar los controladores de GPU con una instalación limpia.",
        ),
        rationale=(
            "Que los indicadores básicos figuren correctos no demuestra que el "
            "hardware esté sano: temperatura, alimentación y estabilidad bajo carga "
            "no se miden en un análisis puntual."
        ),
        verification="Reproducir la situación que provoca el síntoma y comprobar si persiste.",
    )


def _system_events(result: ComponentResult) -> Recommendation:
    prob = (result.possible_problem or "").lower()
    if "whea" in prob:
        return Recommendation(
            component=ComponentKind.SYSTEM,
            title="Investigar error de arquitectura de hardware WHEA en el visor de eventos",
            cause=result.possible_problem or "Error crítico de hardware WHEA reportado por Windows.",
            steps=(
                "Abrir el Visor de eventos de Windows (eventvwr.msc) y navegar a Registros del sistema.",
                "Filtrar por origen WHEA-Logger para identificar el componente (CPU, memoria caché, bus PCIe o memoria física).",
                "Verificar temperaturas operativas y estabilidad de voltajes en el BIOS/UEFI.",
                "Si los errores persisten, contactar al servicio de soporte técnico del fabricante del procesador o placa base.",
            ),
            rationale=(
                "Los eventos WHEA (Windows Hardware Error Architecture) provienen directamente de los mecanismos de comprobación "
                "del procesador y chipset. Señalan anomalías físicas de integridad eléctrica o lógica de hardware."
            ),
            verification="Comprobar en el visor de eventos que no se registren nuevos eventos WHEA bajo uso estándar.",
        )
    if "reinicio" in prob or "kernel-power" in prob or "41" in prob:
        return Recommendation(
            component=ComponentKind.SYSTEM,
            title="Monitorear reinicios inesperados (Kernel-Power 41)",
            cause="reinicio inesperado detectado, causa no determinada (Event ID 41).",
            steps=(
                "Comprobar el suministro eléctrico, estado de la toma de corriente y cable de alimentación o batería.",
                "Verificar que el equipo no haya sufrido cortes abruptos de suministro eléctrico.",
                "Revisar si los reinicios ocurren bajo carga térmica elevada.",
                "Evitar forzar apagados manteniendo presionado el botón de encendido salvo bloqueo total.",
            ),
            rationale=(
                "El evento Kernel-Power 41 únicamente indica que el sistema no se apagó de forma limpia previamente. "
                "No identifica por sí mismo la causa raíz física, por lo que no debe atribuirse a fallo de un componente concreto sin evidencia adicional."
            ),
            verification="Confirmar que el equipo complete sesiones de trabajo y apagados limpios sin generar nuevos registros de Event ID 41.",
        )
    return _generic(result)


def _driver(result: ComponentResult) -> Recommendation:
    return Recommendation(
        component=ComponentKind.DRIVER,
        title="Revisar controladores en el sitio de soporte del fabricante (OEM)",
        cause=result.possible_problem or "Controlador no firmado o correlacionado con código de error PnP activo.",
        steps=(
            "Identificar el identificador de hardware (DeviceID/InstanceId) del dispositivo afectado.",
            "Descargar el controlador oficial exclusivamente desde la página web del fabricante del equipo o componente (OEM).",
            "Evitar instaladores automáticos de controladores de terceros no verificados.",
            "Instalar el paquete del controlador firmado por Microsoft WHQL y reiniciar el equipo.",
        ),
        rationale=(
            "Solo se aconseja intervenir controladores cuando existe un fallo PnP confirmado, estado deshabilitado por error o firma ausente. "
            "Una versión o fecha antigua por sí sola no justifica actualizar si el controlador funciona correctamente."
        ),
        verification="Comprobar en el Administrador de dispositivos que el dispositivo opere con estado 'Este dispositivo funciona correctamente' (código 0).",
    )


def _network(result: ComponentResult) -> Recommendation:
    case = _case(result)
    prob = (result.possible_problem or "").lower()
    if case == "C1" or "apipa" in prob:
        return _apipa(result)
    if case == "dns" or "dns" in prob:
        return _dns(result)
    if "pérdida" in prob or "latencia" in prob:
        return Recommendation(
            component=ComponentKind.NETWORK,
            title="Diagnosticar pérdida de paquetes o degradación de latencia de red",
            cause=result.possible_problem or "Pérdida de paquetes o latencia anormal detectada en la red local/externa.",
            steps=(
                "Comprobar el cable Ethernet o verificar si la señal Wi-Fi presenta atenuación o interferencias.",
                "Comprobar si hay aplicaciones realizando descargas masivas o saturando el ancho de banda.",
                "Reiniciar el módem/enrutador de la red local.",
                "Verificar con el proveedor de Internet (ISP) la estabilidad del enlace si el fallo es persistente.",
            ),
            rationale=(
                "La pérdida sostenida de paquetes deteriora la comunicación y provoca desconexiones en protocolos orientados a conexión."
            ),
            verification="Ejecutar una nueva comprobación de red y verificar 0% de pérdida de paquetes hacia el gateway.",
        )
    return _generic(result)


def _for_alert(result: ComponentResult) -> Recommendation:
    """Elige el procedimiento que corresponde a un componente con anomalía."""
    case = _case(result)
    if result.component is ComponentKind.SYSTEM:
        return _system_events(result)
    if result.component is ComponentKind.CPU:
        return _cpu(result)
    if result.component is ComponentKind.MEMORY:
        return _memory(result)
    if result.component is ComponentKind.DISK:
        return _usb_without_volume(result) if case == "USB-SIN-VOLUMEN" else _disk(result)
    if result.component is ComponentKind.NETWORK:
        return _network(result)
    if result.component is ComponentKind.DRIVER:
        return _driver(result)
    if result.component is ComponentKind.PCI and case == "C2":
        return _pci_nic(result)
    if result.component is ComponentKind.USB and case == "C3":
        return _usb_peripheral(result)
    return _generic(result)


def build_recommendations(
    results: Sequence[ComponentResult],
    symptom: str | None = None,
    expected_device: str | None = None,
) -> tuple[Recommendation, ...]:
    """Deriva procedimientos correctivos del diagnóstico ya clasificado.

    Un equipo sin anomalías y sin síntoma no genera ninguna: no se inventan
    recomendaciones sin motivo. El síntoma se trata como dato y jamás se
    interpola en un procedimiento.
    """
    ordered = sorted(results, key=lambda item: _SEVERITY_ORDER.get(item.status, 9))

    recommendations: list[Recommendation] = []
    for result in ordered:
        if result.status in _ALERTS:
            recommendations.append(_for_alert(result))
        elif result.status is HealthStatus.ERROR:
            recommendations.append(_failed_query(result))

    has_alerts = any(result.status in _ALERTS for result in results)
    if symptom and not has_alerts:
        recommendations.append(_symptom(symptom))

    if expected_device and not has_alerts:
        recommendations.append(
            Recommendation(
                component=ComponentKind.USB,
                title="Confirmar por identificador el dispositivo esperado",
                cause=(
                    "El usuario esperaba encontrar un dispositivo que no aparece en el "
                    "inventario consultado."
                ),
                steps=(
                    (
                        "Abrir el Administrador de dispositivos y activar «Mostrar "
                        "dispositivos ocultos»."
                    ),
                    (
                        "Buscar el dispositivo por su identificador de instancia, no "
                        "por su nombre comercial."
                    ),
                    "Probarlo en otro puerto y en otro equipo para separar medio de puerto.",
                ),
                rationale=(
                    "Una lista vacía no demuestra que el dispositivo no exista ni que "
                    "nunca haya estado conectado; sin confirmación por identificador no "
                    "procede condenar el bus."
                ),
                verification="Comprobar si el dispositivo aparece al reconectarlo en otro puerto.",
            )
        )

    return tuple(recommendations)
