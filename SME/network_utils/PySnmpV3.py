"""Helper central de SNMPv3 (SHA auth + DES56 priv) sobre pysnmp 7.1 async.

Único punto del sistema que construye las credenciales `UsmUserData`: si cambia
el modo SNMP (usuario, protocolos, contraseñas) se ajusta aquí y nada más.

Expone:
  - Async:  ``snmp_get_async(ip, oid)`` y ``snmp_walk_async(ip, oid_base)``.
  - Sync :  ``snmp_get(ip, oid)`` y ``snmp_walk(ip, oid_base)`` (envuelven el async,
            utilizables desde rutas Flask y desde hilos de monitoreo).

Notas de diseño:
  - Los routers c7200 del lab solo aceptan **DES56** como protocolo de privacidad
    (no AES128); por eso ``privProtocol=usmDESPrivProtocol``.
  - ``snmp_walk_async`` limita el recorrido al subárbol del OID dado
    (``lexicographicMode=False``).
"""
import os
import asyncio
import concurrent.futures

from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    UsmUserData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    get_cmd,
    walk_cmd,
    usmHMACSHAAuthProtocol,
    usmDESPrivProtocol,
)

# --- Credenciales SNMPv3 (desde .env) ----------------------------------------
SNMP_USER = os.getenv('SNMP_USER', 'snmp_user')
SNMP_AUTH_PASS = os.getenv('SNMP_AUTH_PASS', 'authpass123')
SNMP_PRIV_PASS = os.getenv('SNMP_PRIV_PASS', 'privpass123')
SNMP_PORT = int(os.getenv('SNMP_PORT', 161))
SNMP_TIMEOUT = float(os.getenv('SNMP_TIMEOUT', 2))
SNMP_RETRIES = int(os.getenv('SNMP_RETRIES', 1))


class SnmpError(Exception):
    """Error de comunicación o respuesta SNMP."""


def credenciales_usm() -> UsmUserData:
    """Construye el `UsmUserData` SNMPv3 (SHA + DES56). Punto único de verdad."""
    return UsmUserData(
        SNMP_USER,
        authKey=SNMP_AUTH_PASS,
        privKey=SNMP_PRIV_PASS,
        authProtocol=usmHMACSHAAuthProtocol,
        privProtocol=usmDESPrivProtocol,
    )


async def _transporte(ip: str) -> UdpTransportTarget:
    return await UdpTransportTarget.create(
        (ip, SNMP_PORT), timeout=SNMP_TIMEOUT, retries=SNMP_RETRIES
    )


# ------------------------------------------------------------------------------
# API asíncrona
# ------------------------------------------------------------------------------

async def snmp_get_async(ip: str, oid: str):
    """GET de un OID escalar. Devuelve el valor (objeto pysnmp) o lanza SnmpError."""
    error_indication, error_status, error_index, var_binds = await get_cmd(
        SnmpEngine(),
        credenciales_usm(),
        await _transporte(ip),
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
    )
    if error_indication:
        raise SnmpError(f"{ip}: {error_indication}")
    if error_status:
        raise SnmpError(f"{ip}: {error_status.prettyPrint()} en índice {error_index}")
    return var_binds[0][1]


async def snmp_walk_async(ip: str, oid_base: str) -> list[tuple[str, object]]:
    """WALK del subárbol bajo ``oid_base``. Devuelve [(oid_str, valor), ...]."""
    resultados: list[tuple[str, object]] = []
    async for error_indication, error_status, error_index, var_binds in walk_cmd(
        SnmpEngine(),
        credenciales_usm(),
        await _transporte(ip),
        ContextData(),
        ObjectType(ObjectIdentity(oid_base)),
        lexicographicMode=False,   # se detiene al salir del subárbol
    ):
        if error_indication:
            raise SnmpError(f"{ip}: {error_indication}")
        if error_status:
            raise SnmpError(
                f"{ip}: {error_status.prettyPrint()} en índice {error_index}"
            )
        for var_bind in var_binds:
            resultados.append((str(var_bind[0]), var_bind[1]))
    return resultados


# ------------------------------------------------------------------------------
# Envoltorios síncronos
# ------------------------------------------------------------------------------

def _run(coro_factory):
    """Ejecuta una corutina desde código síncrono.

    Si ya hay un event loop corriendo (p. ej. dentro de un contexto async),
    delega a un hilo aparte con su propio loop para no chocar.
    """
    try:
        asyncio.get_running_loop()
        hay_loop = True
    except RuntimeError:
        hay_loop = False

    if hay_loop:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: asyncio.run(coro_factory())).result()
    return asyncio.run(coro_factory())


def snmp_get(ip: str, oid: str):
    """Versión síncrona de :func:`snmp_get_async`."""
    return _run(lambda: snmp_get_async(ip, oid))


def snmp_walk(ip: str, oid_base: str) -> list[tuple[str, object]]:
    """Versión síncrona de :func:`snmp_walk_async`."""
    return _run(lambda: snmp_walk_async(ip, oid_base))
