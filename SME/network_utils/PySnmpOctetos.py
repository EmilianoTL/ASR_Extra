"""Monitoreo de métricas de interfaz vía SNMPv3 (6 contadores, en hilos daemon).

Por cada interfaz monitoreada se lanza un hilo daemon que cada ``intervalo``
segundos lee 6 contadores de ifTable, calcula tasas (bits/s y paquetes/s) contra
la muestra anterior — manejando el wrap-around de Counter32 — y guarda una fila
``MetricaInterfaz``.

Contadores (ifTable 1.3.6.1.2.1.2.2.1.<col>.<ifIndex>):
  ifInOctets .10   ifOutOctets .16     -> bits_in / bits_out
  ifInUcastPkts .11  ifOutUcastPkts .17 -> unicast_in / unicast_out
  ifInNUcastPkts .12 ifOutNUcastPkts .18 -> non_unicast_in / non_unicast_out

API pública:
  iniciar_monitoreo_hilo(app, hostname, ip_admin, interfaz_api, intervalo)
  detener_monitoreo_interfaz(hostname, interfaz_api)
  monitoreo_activo(hostname, interfaz_api)
"""
import time
import asyncio
import threading

from database.models import db, MetricaInterfaz
from network_utils.PySnmpV3 import snmp_get_async, snmp_walk_async, SnmpError

OID_IF_DESCR = '1.3.6.1.2.1.2.2.1.2'
_OID_COLS = {
    'in_octets': '1.3.6.1.2.1.2.2.1.10',
    'out_octets': '1.3.6.1.2.1.2.2.1.16',
    'in_ucast': '1.3.6.1.2.1.2.2.1.11',
    'out_ucast': '1.3.6.1.2.1.2.2.1.17',
    'in_nucast': '1.3.6.1.2.1.2.2.1.12',
    'out_nucast': '1.3.6.1.2.1.2.2.1.18',
}

COUNTER32_MAX = 2 ** 32

# Registro de hilos activos: clave "{hostname}_{interfaz}" -> threading.Event de parada
_HILOS: dict[str, threading.Event] = {}
_LOCK = threading.Lock()


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def _clave(hostname: str, interfaz: str) -> str:
    return f"{hostname}_{interfaz}"


def estandarizar_nombre_interfaz(interfaz_api: str) -> str:
    """'f0_0' -> 'fastethernet0/0' (para comparar contra ifDescr)."""
    nombre = interfaz_api.lower().replace('_', '/')
    if nombre.startswith('f') and not nombre.startswith('fastethernet'):
        nombre = nombre.replace('f', 'fastethernet', 1)
    return nombre


def _delta(actual: int, previo: int) -> int:
    """Diferencia de dos Counter32 consecutivos, manejando wrap-around."""
    if actual >= previo:
        return actual - previo
    return (COUNTER32_MAX - previo) + actual


async def _obtener_indice(ip: str, interfaz_api: str):
    """Devuelve el ifIndex de la interfaz recorriendo ifDescr, o None."""
    buscado = estandarizar_nombre_interfaz(interfaz_api)
    for oid, valor in await snmp_walk_async(ip, OID_IF_DESCR):
        if buscado in str(valor).lower():
            return int(oid.split('.')[-1])
    return None


async def _leer_contadores(ip: str, indice: int) -> dict:
    """Lee los 6 contadores en el índice dado (en paralelo)."""
    claves = list(_OID_COLS.keys())
    valores = await asyncio.gather(
        *(snmp_get_async(ip, f"{_OID_COLS[k]}.{indice}") for k in claves)
    )
    return {k: int(v) for k, v in zip(claves, valores)}


# ------------------------------------------------------------------------------
# API pública de estado
# ------------------------------------------------------------------------------

def monitoreo_activo(hostname: str, interfaz_api: str) -> bool:
    with _LOCK:
        return _clave(hostname, interfaz_api) in _HILOS


def detener_monitoreo_interfaz(hostname: str, interfaz_api: str) -> bool:
    """Señala al hilo para que termine. Devuelve True si existía."""
    clave = _clave(hostname, interfaz_api)
    with _LOCK:
        evento = _HILOS.pop(clave, None)
    if evento is None:
        return False
    evento.set()
    return True


def iniciar_monitoreo_hilo(app, hostname, ip_admin, interfaz_api, intervalo) -> bool:
    """Lanza el hilo de muestreo. Devuelve False si ya estaba activo."""
    clave = _clave(hostname, interfaz_api)
    with _LOCK:
        if clave in _HILOS:
            return False
        evento = threading.Event()
        _HILOS[clave] = evento

    hilo = threading.Thread(
        target=_bucle_monitoreo,
        args=(app, hostname, ip_admin, interfaz_api, int(intervalo), evento),
        daemon=True,
        name=f"snmp-{clave}",
    )
    hilo.start()
    return True


# ------------------------------------------------------------------------------
# Bucle del hilo
# ------------------------------------------------------------------------------

def _bucle_monitoreo(app, hostname, ip_admin, interfaz_api, intervalo, evento):
    """Muestrea contadores cada `intervalo`s y guarda tasas en la BD."""
    clave = _clave(hostname, interfaz_api)
    try:
        indice = asyncio.run(_obtener_indice(ip_admin, interfaz_api))
        if indice is None:
            print(f"[octetos] {clave}: interfaz no encontrada; hilo termina")
            return

        previo = asyncio.run(_leer_contadores(ip_admin, indice))
        t_previo = time.monotonic()

        while not evento.wait(intervalo):
            try:
                actual = asyncio.run(_leer_contadores(ip_admin, indice))
            except SnmpError as e:
                print(f"[octetos] {clave}: fallo de lectura ({e}); reintenta")
                continue
            ahora = time.monotonic()
            dt = ahora - t_previo
            if dt <= 0:
                continue

            fila = MetricaInterfaz(
                router_hostname=hostname,
                interfaz_api=interfaz_api,
                bits_in=_delta(actual['in_octets'], previo['in_octets']) * 8 / dt,
                bits_out=_delta(actual['out_octets'], previo['out_octets']) * 8 / dt,
                unicast_in=_delta(actual['in_ucast'], previo['in_ucast']) / dt,
                unicast_out=_delta(actual['out_ucast'], previo['out_ucast']) / dt,
                non_unicast_in=_delta(actual['in_nucast'], previo['in_nucast']) / dt,
                non_unicast_out=_delta(actual['out_nucast'], previo['out_nucast']) / dt,
            )
            with app.app_context():
                db.session.add(fila)
                db.session.commit()

            previo, t_previo = actual, ahora
    except SnmpError as e:
        print(f"[octetos] {clave}: error inicial ({e}); hilo termina")
    finally:
        # Auto-limpieza del registro si el hilo muere solo.
        with _LOCK:
            if _HILOS.get(clave) is evento:
                _HILOS.pop(clave, None)
