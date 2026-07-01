"""Blueprint /topologia — opción "Explorar la red".

  GET  /topologia/   routers + enlaces + figura Plotly del grafo
  POST /topologia/   lanza el descubrimiento BFS por CDP desde el router semilla

El descubrimiento abre UNA sesión SSH (Netmiko) por router, lee hostname, versión,
interfaces y vecinos CDP, y recorre la red en anchura (BFS). Luego sincroniza la
BD (crea/actualiza/borra routers e interfaces y sus adyacencias).

Netmiko se importa de forma diferida para que la app arranque aunque la
dependencia no esté instalada (p. ej. en pruebas).
"""
import os
import re
import socket
import struct
from collections import deque

from flask import Blueprint, jsonify, request, Response

from database.models import db, Router, Interface
from viz.grafo_topologia import (
    construir_figura, construir_enlaces, construir_resumen,
    construir_html, construir_svg,
)

topologia_bp = Blueprint('topologia', __name__)

SEED_ROUTER_IP = os.getenv('SEED_ROUTER_IP', '148.204.56.1')
ROUTER_USER = os.getenv('ROUTER_USER', 'admin')
ROUTER_PASS = os.getenv('ROUTER_PASS', 'cisco123')
ROUTER_ENABLE = os.getenv('ROUTER_ENABLE', 'enable123')


# ------------------------------------------------------------------------------
# Helpers de parseo
# ------------------------------------------------------------------------------

def normalizar_interfaz(nombre: str) -> str:
    """'FastEthernet1/0' -> 'f1_0', 'GigabitEthernet0/1' -> 'g0_1'."""
    n = nombre.strip()
    prefijos = [
        ('fastethernet', 'f'), ('gigabitethernet', 'g'),
        ('tengigabitethernet', 't'), ('ethernet', 'e'),
        ('serial', 's'), ('loopback', 'lo'),
    ]
    low = n.lower()
    for prefijo, abrev in prefijos:
        if low.startswith(prefijo):
            return abrev + n[len(prefijo):].replace('/', '_')
    m = re.match(r'([A-Za-z]+)(\d.*)', n)
    if m:
        return m.group(1)[0].lower() + m.group(2).replace('/', '_')
    return low.replace('/', '_')


def _prefijo_a_mascara(prefijo: int) -> str:
    bits = 0xFFFFFFFF ^ ((1 << (32 - prefijo)) - 1)
    return socket.inet_ntoa(struct.pack('>I', bits))


# ------------------------------------------------------------------------------
# Recolección por SSH (una conexión por router)
# ------------------------------------------------------------------------------

def _recolectar_info_router(ip: str) -> dict:
    """Abre una sesión SSH y devuelve hostname, SO, interfaces y vecinos CDP."""
    from netmiko import ConnectHandler   # import diferido

    device = {
        'device_type': 'cisco_ios',
        'host': ip,
        'username': ROUTER_USER,
        'password': ROUTER_PASS,
        'secret': ROUTER_ENABLE,
        'timeout': 30,
    }
    with ConnectHandler(**device) as conn:
        conn.enable()
        s_hostname = conn.send_command('show running-config | include ^hostname')
        s_version = conn.send_command('show version')
        s_intfs = conn.send_command('show interfaces')
        s_cdp = conn.send_command('show cdp neighbors detail')

    return _parsear_info(ip, s_hostname, s_version, s_intfs, s_cdp)


def _parsear_info(ip, s_hostname, s_version, s_intfs, s_cdp) -> dict:
    """Parsea las salidas de los comandos (separado para poder probarlo)."""
    m = re.search(r'^hostname\s+(\S+)', s_hostname, re.MULTILINE)
    hostname = m.group(1) if m else ip

    m_so = re.search(r'Cisco IOS.*?Version\s+(\S+)', s_version)
    sistema_operativo = f"Cisco IOS {m_so.group(1).rstrip(',')}" if m_so else 'Cisco IOS'

    interfaces = []
    actual = None
    for linea in s_intfs.splitlines():
        m_i = re.match(r'^(\S+)\s+is\s+(up|down|administratively down)', linea, re.I)
        if m_i:
            actual = normalizar_interfaz(m_i.group(1))
            estado = 'up' if m_i.group(2).lower() == 'up' else 'down'
            if not any(i['nombre_api'] == actual for i in interfaces):
                interfaces.append({'nombre_api': actual, 'ip_address': None,
                                   'mascara': None, 'estado': estado})
            continue
        m_ip = re.match(r'\s+Internet address is (\d+\.\d+\.\d+\.\d+)/(\d+)', linea)
        if m_ip and actual:
            for i in interfaces:
                if i['nombre_api'] == actual:
                    i['ip_address'] = m_ip.group(1)
                    i['mascara'] = _prefijo_a_mascara(int(m_ip.group(2)))
                    break

    vecinos_cdp = []
    for bloque in re.split(r'(?=Device ID:)', s_cdp):
        m_dev = re.search(r'Device ID:\s*(\S+)', bloque)
        if not m_dev:
            continue
        vecino = m_dev.group(1).split('.')[0]
        ips = re.findall(r'IP address:\s*(\d+\.\d+\.\d+\.\d+)', bloque)
        m_intf = re.search(r'Interface:\s*([\w/]+)', bloque)
        m_port = re.search(r'Port ID \(outgoing port\):\s*([\w/]+)', bloque)
        if vecino and m_intf and ips:
            vecinos_cdp.append({
                'vecino': vecino,
                'interfaz_local': normalizar_interfaz(m_intf.group(1)),
                'interfaz_remota': normalizar_interfaz(m_port.group(1)) if m_port else None,
                'ip_vecino': ips[0],
            })

    return {
        'hostname': hostname,
        'ip_admin': ip,
        'sistema_operativo': sistema_operativo,
        'interfaces': interfaces,
        'vecinos_cdp': vecinos_cdp,
    }


# ------------------------------------------------------------------------------
# BFS de descubrimiento
# ------------------------------------------------------------------------------

def descubrir_topologia(seed_ip: str) -> dict:
    """BFS desde `seed_ip` recorriendo la red por CDP. Devuelve {hostname: info}."""
    visitados_ip = set()
    visitados_host = set()
    cola = deque([seed_ip])
    red = {}

    while cola:
        ip = cola.popleft()
        if ip in visitados_ip:
            continue
        visitados_ip.add(ip)

        try:
            info = _recolectar_info_router(ip)
        except Exception as e:  # noqa: BLE001 (netmiko/timeout/auth)
            print(f"[topologia] {ip} omitido: {type(e).__name__}: {e}")
            continue

        if info['hostname'] in visitados_host:
            continue
        visitados_host.add(info['hostname'])
        red[info['hostname']] = info

        for vecino in info['vecinos_cdp']:
            if vecino['ip_vecino'] not in visitados_ip:
                cola.append(vecino['ip_vecino'])

    return red


# ------------------------------------------------------------------------------
# Sincronización con la BD
# ------------------------------------------------------------------------------

def sincronizar_db(red: dict) -> None:
    """Refleja en la BD exactamente la red descubierta (upsert + borrado)."""
    # 1) Upsert de routers e interfaces.
    for hostname, info in red.items():
        router = Router.query.filter_by(hostname=hostname).first()
        if router is None:
            router = Router(hostname=hostname, ip_admin=info['ip_admin'])
            db.session.add(router)
        else:
            router.ip_admin = info['ip_admin']
        router.sistema_operativo = info.get('sistema_operativo') or router.sistema_operativo

        for datos in info['interfaces']:
            iface = Interface.query.filter_by(
                router=router, nombre_api=datos['nombre_api']
            ).first() if router.id else None
            if iface is None:
                iface = Interface(nombre_api=datos['nombre_api'], router=router)
                db.session.add(iface)
            iface.ip_address = datos['ip_address']
            iface.mascara = datos['mascara']
            iface.estado = datos['estado']
    db.session.commit()

    # 2) Adyacencias (ya existen todos los routers).
    por_host = {r.hostname: r for r in Router.query.all()}
    for hostname, info in red.items():
        router = por_host.get(hostname)
        for vecino in info['vecinos_cdp']:
            r_vecino = por_host.get(vecino['vecino'])
            if not r_vecino:
                continue
            iface = Interface.query.filter_by(
                router=router, nombre_api=vecino['interfaz_local']
            ).first()
            if iface:
                iface.conectado_a_router_id = r_vecino.id
    db.session.commit()

    # 3) Borrar routers que ya no aparecen.
    descubiertos = set(red.keys())
    for router in Router.query.all():
        if router.hostname not in descubiertos:
            db.session.delete(router)
    db.session.commit()


# ------------------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------------------

@topologia_bp.route('/', methods=['GET'])
def obtener_topologia():
    """Grafo actual. ?formato=json (def) | html | fragmento | svg | resumen."""
    formato = (request.args.get('formato') or 'json').lower()
    routers = Router.query.all()

    if formato == 'html':
        return Response(construir_html(routers), mimetype='text/html')
    if formato in ('fragmento', 'fragment'):
        return Response(construir_html(routers, fragmento=True), mimetype='text/html')
    if formato == 'svg':
        return Response(construir_svg(routers), mimetype='image/svg+xml')
    if formato == 'resumen':
        return jsonify(construir_resumen(routers)), 200

    return jsonify({
        'routers': [r.to_dict(incluir_interfaces=True) for r in routers],
        'enlaces': construir_enlaces(routers),
        'figura_plotly': construir_figura(routers),
    }), 200


@topologia_bp.route('/', methods=['POST'])
def lanzar_descubrimiento():
    red = descubrir_topologia(SEED_ROUTER_IP)
    if not red:
        return jsonify({
            'error': 'No se descubrió ningún router',
            'seed': SEED_ROUTER_IP,
            'pista': 'Verifica SSH/credenciales y que el enrutamiento esté activo',
        }), 502
    sincronizar_db(red)

    # Resumen simplista: cada router y con quién quedó conectado.
    conexiones = {
        host: sorted({v['vecino'] for v in info['vecinos_cdp']})
        for host, info in red.items()
    }
    enlaces, vistos = [], set()
    for host, vecinos in conexiones.items():
        for vecino in vecinos:
            par = tuple(sorted((host, vecino)))
            if par not in vistos:
                vistos.add(par)
                enlaces.append(f"{par[0]} <-> {par[1]}")

    return jsonify({
        'mensaje': 'Topología actualizada',
        'total': len(red),
        'conexiones': conexiones,
        'enlaces': sorted(enlaces),
    }), 200
