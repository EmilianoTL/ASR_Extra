"""Información de la MIB System vía SNMPv3 (hardware, SO, contacto, uptime, location).

Usado por la opción "Enrutadores": cada GET de detalle refresca estos datos desde
el dispositivo y los persiste en la BD.

OIDs (RFC 1213, grupo system 1.3.6.1.2.1.1):
  sysDescr    .1.0   descripción (de aquí se derivan hardware y SO)
  sysUpTime   .3.0   tiempo de actividad (TimeTicks, centésimas de segundo)
  sysContact  .4.0   contacto
  sysName     .5.0   hostname
  sysLocation .6.0   ubicación
"""
import re
import asyncio

from network_utils.PySnmpV3 import snmp_get_async, SnmpError

OID_SYS_DESCR = '1.3.6.1.2.1.1.1.0'
OID_SYS_UPTIME = '1.3.6.1.2.1.1.3.0'
OID_SYS_CONTACT = '1.3.6.1.2.1.1.4.0'
OID_SYS_NAME = '1.3.6.1.2.1.1.5.0'
OID_SYS_LOCATION = '1.3.6.1.2.1.1.6.0'


def _formatear_uptime(ticks: int) -> str:
    """Convierte TimeTicks (centésimas de segundo) a 'Xd Yh Zm Ws'."""
    total_seg = int(ticks) // 100
    dias, resto = divmod(total_seg, 86400)
    horas, resto = divmod(resto, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{dias}d {horas}h {minutos}m {segundos}s"


def _derivar_hardware(sys_descr: str) -> str:
    """Extrae el modelo del equipo desde sysDescr (ej. 'Cisco 7200')."""
    m = re.search(r'\b(C?7[0-9]{3})\b', sys_descr)
    if m:
        return f"Cisco {m.group(1).lstrip('C')}"
    if 'cisco' in sys_descr.lower():
        return 'Cisco'
    return sys_descr[:60] if sys_descr else 'Desconocido'


def _derivar_so(sys_descr: str) -> str:
    """Extrae la versión de IOS desde sysDescr."""
    m = re.search(r'Version\s+([^\s,]+)', sys_descr)
    if m:
        return f"Cisco IOS {m.group(1)}"
    return 'Cisco IOS' if 'ios' in sys_descr.lower() else (sys_descr[:60] or 'Desconocido')


async def obtener_info_sistema_async(ip: str) -> dict:
    """Lee el grupo system y devuelve un dict con los campos de interés.

    Lanza :class:`SnmpError` si el dispositivo no responde a ninguno de los OIDs.
    """
    oids = [
        OID_SYS_DESCR, OID_SYS_UPTIME, OID_SYS_CONTACT,
        OID_SYS_NAME, OID_SYS_LOCATION,
    ]
    resultados = await asyncio.gather(
        *(snmp_get_async(ip, oid) for oid in oids),
        return_exceptions=True,
    )
    descr, uptime, contacto, nombre, location = resultados

    # Si todo falló, el dispositivo no respondió: propagamos el error.
    if all(isinstance(r, Exception) for r in resultados):
        raise SnmpError(f"{ip}: sin respuesta SNMP en el grupo system")

    def _txt(v):
        return None if isinstance(v, Exception) else str(v)

    sys_descr = _txt(descr) or ''
    return {
        'hardware': _derivar_hardware(sys_descr) if sys_descr else None,
        'sistema_operativo': _derivar_so(sys_descr) if sys_descr else None,
        'contacto': _txt(contacto),
        'location': _txt(location),
        'hostname': _txt(nombre),
        'uptime': (
            _formatear_uptime(uptime) if not isinstance(uptime, Exception) else None
        ),
    }


def obtener_info_sistema(ip: str) -> dict:
    """Versión síncrona de :func:`obtener_info_sistema_async`."""
    return asyncio.run(obtener_info_sistema_async(ip))
