"""Monitor de pérdida de paquetes R1 -> R2 (hilo daemon).

Cada ``PACKET_LOSS_INTERVAL`` segundos entra por SSH a R1 y ejecuta un ping hacia
la IP de R2; parsea el "Success rate" de IOS para obtener el % de pérdida. Si
supera ``PACKET_LOSS_THRESHOLD`` crea una ``Alerta(PACKET_LOSS)``.

Se mide desde R1 (no desde la SME) para reflejar realmente el enlace R1<->R2,
como pide el examen.
"""
import os
import re
import threading

from database.models import db, Router, Alerta

THRESHOLD = float(os.getenv('PACKET_LOSS_THRESHOLD', 25))
INTERVAL = int(os.getenv('PACKET_LOSS_INTERVAL', 30))
COUNT = int(os.getenv('PACKET_LOSS_COUNT', 10))
ROUTER_USER = os.getenv('ROUTER_USER', 'admin')
ROUTER_PASS = os.getenv('ROUTER_PASS', 'cisco123')
ROUTER_ENABLE = os.getenv('ROUTER_ENABLE', 'enable123')

_stop = threading.Event()
_iniciado = False
_lock = threading.Lock()


def parsear_perdida(salida_ping: str):
    """Extrae el % de pérdida del 'Success rate is X percent' de IOS.

    Devuelve el porcentaje de pérdida (0-100) o None si no se pudo parsear.
    """
    m = re.search(r'Success rate is (\d+) percent', salida_ping)
    if not m:
        return None
    return 100 - int(m.group(1))


def _medir_perdida(ip_r1: str, ip_r2: str):
    """SSH a R1, hace ping a R2 y devuelve el % de pérdida (o None)."""
    from netmiko import ConnectHandler   # import diferido

    device = {
        'device_type': 'cisco_ios',
        'host': ip_r1,
        'username': ROUTER_USER,
        'password': ROUTER_PASS,
        'secret': ROUTER_ENABLE,
        'timeout': 30,
    }
    with ConnectHandler(**device) as conn:
        conn.enable()
        salida = conn.send_command(f'ping {ip_r2} repeat {COUNT}', read_timeout=60)
    return parsear_perdida(salida)


def _bucle(app):
    while not _stop.wait(INTERVAL):
        with app.app_context():
            r1 = Router.query.filter_by(hostname='R1').first()
            r2 = Router.query.filter_by(hostname='R2').first()
            if not r1 or not r2:
                continue
            try:
                perdida = _medir_perdida(r1.ip_admin, r2.ip_admin)
            except Exception as e:  # noqa: BLE001
                print(f"[ping] error midiendo R1->R2: {type(e).__name__}: {e}")
                continue
            if perdida is not None and perdida > THRESHOLD:
                db.session.add(Alerta(
                    tipo=Alerta.PACKET_LOSS,
                    router_hostname='R1',
                    descripcion=f"Pérdida R1->R2 {perdida}% (umbral {THRESHOLD}%)",
                ))
                db.session.commit()
                print(f"[ping] ALERTA pérdida R1->R2 {perdida}%")


def iniciar_monitor(app):
    """Arranca el hilo del monitor una sola vez (idempotente)."""
    global _iniciado
    with _lock:
        if _iniciado:
            return
        _iniciado = True
    threading.Thread(
        target=_bucle, args=(app,), daemon=True, name='ping-monitor'
    ).start()
