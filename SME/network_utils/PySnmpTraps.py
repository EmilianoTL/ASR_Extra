"""Receptor de traps SNMPv3 (hilo daemon) que genera Alertas.

Escucha en el puerto de traps (162) con un usuario SNMPv3 (SHA + DES) y mapea:
  LinkUp   (1.3.6.1.6.3.1.1.5.4)          -> Alerta IFACE_UP
  LinkDown (1.3.6.1.6.3.1.1.5.3)          -> Alerta IFACE_DOWN
  TTY/console (1.3.6.1.4.1.9.9.41.*)      -> Alerta CONSOLE_ACCESS

Singleton: ``asegurar_receptor_corriendo(app)`` arranca el hilo una sola vez.
"""
import os
import asyncio
import threading

from pysnmp.entity import engine, config
from pysnmp.entity.rfc3413 import ntfrcv
from pysnmp.carrier.asyncio.dgram import udp

from database.models import db, Alerta

SNMP_USER = os.getenv('SNMP_USER', 'snmp_user')
SNMP_AUTH_PASS = os.getenv('SNMP_AUTH_PASS', 'authpass123')
SNMP_PRIV_PASS = os.getenv('SNMP_PRIV_PASS', 'privpass123')
TRAP_PORT = int(os.getenv('TRAP_PORT', 162))

OID_SNMP_TRAP_OID = '1.3.6.1.6.3.1.1.4.1.0'
OID_LINKDOWN = '1.3.6.1.6.3.1.1.5.3'
OID_LINKUP = '1.3.6.1.6.3.1.1.5.4'
OID_IF_INDEX = '1.3.6.1.2.1.2.2.1.1'
PREFIJO_TTY = '1.3.6.1.4.1.9.9.41'    # traps de syslog/consola de Cisco

# Estado del singleton.
_RECEPTOR_INICIADO = False
_LOCK = threading.Lock()
# Última dirección de origen observada (para mapear el trap a un router).
_ULTIMA_FUENTE = None
_LOCK_FUENTE = threading.Lock()


def _tipo_por_trap_oid(trap_oid: str):
    if trap_oid == OID_LINKUP:
        return Alerta.IFACE_UP
    if trap_oid == OID_LINKDOWN:
        return Alerta.IFACE_DOWN
    if trap_oid.startswith(PREFIJO_TTY):
        return Alerta.CONSOLE_ACCESS
    return None


def _hostname_por_ip(ip):
    """Mapea la IP de origen a un hostname de router; si no, devuelve la IP."""
    if not ip:
        return None
    from database.models import Router, Interface
    r = Router.query.filter_by(ip_admin=ip).first()
    if r:
        return r.hostname
    iface = Interface.query.filter_by(ip_address=ip).first()
    if iface and iface.router:
        return iface.router.hostname
    return ip


def guardar_alerta(app, tipo, router_hostname, interfaz_api, descripcion):
    """Persiste una Alerta (función aislada para poder probarla sin red)."""
    with app.app_context():
        db.session.add(Alerta(
            tipo=tipo,
            router_hostname=router_hostname,
            interfaz_api=interfaz_api,
            descripcion=descripcion,
        ))
        db.session.commit()


def _procesar_trap(app, var_binds):
    """Extrae el tipo de trap y datos relevantes y crea la Alerta."""
    trap_oid = None
    if_index = None
    for oid, valor in var_binds:
        oid_s = str(oid)
        if oid_s == OID_SNMP_TRAP_OID:
            trap_oid = str(valor)
        elif oid_s.startswith(OID_IF_INDEX + '.') or oid_s == OID_IF_INDEX:
            if_index = str(valor)

    tipo = _tipo_por_trap_oid(trap_oid) if trap_oid else None
    if tipo is None:
        return  # trap no relevante para el sistema

    with _LOCK_FUENTE:
        ip = _ULTIMA_FUENTE
    with app.app_context():
        hostname = _hostname_por_ip(ip)
        interfaz = f"ifIndex {if_index}" if if_index else None
        db.session.add(Alerta(
            tipo=tipo,
            router_hostname=hostname,
            interfaz_api=interfaz,
            descripcion=f"Trap {trap_oid} desde {ip or 'origen desconocido'}",
        ))
        db.session.commit()


def _correr_receptor(app):
    asyncio.set_event_loop(asyncio.new_event_loop())
    snmp_engine = engine.SnmpEngine()

    # Observa la dirección de origen de cada mensaje recibido.
    def _observador(snmp_eng, execpoint, variables, cb_ctx):
        global _ULTIMA_FUENTE
        direccion = variables.get('transportAddress')
        if direccion:
            with _LOCK_FUENTE:
                _ULTIMA_FUENTE = str(direccion[0])

    snmp_engine.observer.register_observer(
        _observador, 'rfc3412.receiveMessage:request'
    )

    config.add_transport(
        snmp_engine,
        udp.DOMAIN_NAME,
        udp.UdpTransport().open_server_mode(('0.0.0.0', TRAP_PORT)),
    )
    config.add_v3_user(
        snmp_engine,
        SNMP_USER,
        config.USM_AUTH_HMAC96_SHA, SNMP_AUTH_PASS,
        config.USM_PRIV_CBC56_DES, SNMP_PRIV_PASS,
    )

    def _cb(snmp_eng, state_ref, ctx_engine_id, ctx_name, var_binds, cb_ctx):
        try:
            _procesar_trap(app, var_binds)
        except Exception as e:  # noqa: BLE001
            print(f"[traps] error procesando trap: {e}")

    ntfrcv.NotificationReceiver(snmp_engine, _cb)
    snmp_engine.transport_dispatcher.job_started(1)
    print(f"[traps] receptor SNMPv3 escuchando en udp/{TRAP_PORT}")
    try:
        snmp_engine.transport_dispatcher.run_dispatcher()
    except Exception as e:  # noqa: BLE001
        print(f"[traps] receptor detenido: {e}")
        snmp_engine.transport_dispatcher.close_dispatcher()


def asegurar_receptor_corriendo(app):
    """Arranca el hilo receptor una sola vez (idempotente)."""
    global _RECEPTOR_INICIADO
    with _LOCK:
        if _RECEPTOR_INICIADO:
            return
        _RECEPTOR_INICIADO = True
    hilo = threading.Thread(
        target=_correr_receptor, args=(app,), daemon=True, name='snmp-traps'
    )
    hilo.start()
