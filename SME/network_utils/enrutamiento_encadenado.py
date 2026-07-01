"""Configuración de enrutamiento ENCADENADA por CDP (SSH anidado / jump host).

Resuelve el problema del huevo y la gallina: al inicio los routers no tienen
enrutamiento, así que la SME solo alcanza a R1 (directamente conectado). Para
llegar a R2/R3 se usa cada router como **salto SSH** hacia el siguiente:

    SME --ssh--> R1 --ssh--> R2 --ssh--> R3

Cada enlace es directo (R1-R2, R2-R3 son /30 conectados), así que el SSH anidado
funciona aunque no exista aún ninguna ruta hacia la red de gestión de la SME.

En cada router: aplica el protocolo (RIP u OSPF), guarda, y lee sus vecinos CDP
para saltar a los que falten (DFS). Devuelve además la topología descubierta
(hostname, interfaces, vecinos) para poblar la BD en la misma pasada.

Nota: es SSH interactivo sobre IOS; requiere pruebas/ajuste de tiempos contra el
equipo real (banners, prompt yes/no, latencia). Variables de tiempo por .env:
JUMP_MAX_ESPERA, JUMP_PAUSA.
"""
import os
import time

from routes.topologia import _parsear_info

ROUTER_USER = os.getenv('ROUTER_USER', 'admin')
ROUTER_PASS = os.getenv('ROUTER_PASS', 'cisco123')
ROUTER_ENABLE = os.getenv('ROUTER_ENABLE', 'enable123')
SEED_ROUTER_IP = os.getenv('SEED_ROUTER_IP', '148.204.56.1')

_JUMP_MAX_ESPERA = int(os.getenv('JUMP_MAX_ESPERA', 15))   # iteraciones de lectura
_JUMP_PAUSA = float(os.getenv('JUMP_PAUSA', 1.0))          # seg entre lecturas

_COMANDOS = {
    'rip': ['router rip', 'version 2', 'network 8.0.0.0',
            'network 148.204.0.0', 'no auto-summary'],
    'ospf': ['router ospf 1', 'network 0.0.0.0 255.255.255.255 area 0'],
}


def _leer_hasta(conn, marcadores, max_iter=_JUMP_MAX_ESPERA):
    """Lee del canal hasta ver alguno de los marcadores o agotar intentos."""
    buffer = ''
    for _ in range(max_iter):
        time.sleep(_JUMP_PAUSA)
        buffer += conn.read_channel()
        if any(m.lower() in buffer.lower() for m in marcadores):
            break
    return buffer


def _saltar(conn, ip, log):
    """Desde la sesión actual abre SSH al `ip` (salto). Devuelve True si entró."""
    conn.write_channel(f'ssh -l {ROUTER_USER} {ip}\n')
    salida = _leer_hasta(conn, ['assword', 'yes/no', 'yes/no)?'])

    if 'yes/no' in salida.lower():   # confirmación de host key
        conn.write_channel('yes\n')
        salida += _leer_hasta(conn, ['assword'])

    if 'assword' not in salida:
        log(f"salto a {ip}: no llegó el prompt de contraseña")
        return False

    conn.write_channel(ROUTER_PASS + '\n')
    _leer_hasta(conn, ['#', '>'])

    from netmiko import redispatch
    redispatch(conn, device_type='cisco_ios')
    try:
        conn.enable()
    except Exception:  # noqa: BLE001 (usuario priv 15 ya entra en enable)
        pass
    return True


def _volver(conn, log):
    """Sale de la sesión anidada y vuelve al router padre."""
    from netmiko import redispatch
    try:
        conn.write_channel('exit\n')
        _leer_hasta(conn, ['#', '>'])
        redispatch(conn, device_type='cisco_ios')
    except Exception as e:  # noqa: BLE001
        log(f"aviso al volver: {type(e).__name__}: {e}")


def _recolectar(conn, ip_conexion):
    """Ejecuta los comandos show y parsea hostname/SO/interfaces/vecinos."""
    sh = conn.send_command('show running-config | include ^hostname')
    sv = conn.send_command('show version')
    si = conn.send_command('show interfaces')
    sc = conn.send_command('show cdp neighbors detail')
    return _parsear_info(ip_conexion, sh, sv, si, sc)


def _configurar(conn, comandos):
    conn.send_config_set(comandos)
    conn.save_config()


def _procesar(conn, ip_conexion, comandos, visitados, red, configurados, log):
    """DFS: recolecta, configura y salta a vecinos no visitados."""
    info = _recolectar(conn, ip_conexion)
    host = info['hostname']
    if host in visitados:
        return
    visitados.add(host)
    red[host] = info
    log(f"en {host} ({ip_conexion}): aplicando enrutamiento...")

    try:
        _configurar(conn, comandos)
        configurados.append(host)
        log(f"{host}: enrutamiento aplicado y guardado")
    except Exception as e:  # noqa: BLE001
        log(f"{host}: error al configurar: {type(e).__name__}: {e}")

    for vecino in info['vecinos_cdp']:
        if vecino['vecino'] in visitados:
            continue
        ip_v = vecino['ip_vecino']
        log(f"{host}: saltando a vecino {vecino['vecino']} ({ip_v})...")
        if _saltar(conn, ip_v, log):
            _procesar(conn, ip_v, comandos, visitados, red, configurados, log)
            _volver(conn, log)
        else:
            log(f"{host}: no se pudo saltar a {ip_v}; se omite esa rama")


def configurar_red_encadenada(protocolo: str) -> dict:
    """Configura el protocolo en toda la red por saltos CDP desde el semilla.

    Devuelve {'ok', 'protocolo', 'configurados', 'red', 'log'}.
    `red` es {hostname: info} para poder sincronizar la BD (topología).
    """
    protocolo = (protocolo or '').lower()
    if protocolo not in _COMANDOS:
        return {'ok': False, 'error': "protocolo debe ser 'rip' u 'ospf'"}

    from netmiko import ConnectHandler

    mensajes = []
    def log(m):
        print(f"[enrutamiento] {m}")
        mensajes.append(m)

    visitados, red, configurados = set(), {}, []
    try:
        conn = ConnectHandler(
            device_type='cisco_ios', host=SEED_ROUTER_IP,
            username=ROUTER_USER, password=ROUTER_PASS, secret=ROUTER_ENABLE,
            timeout=30,
        )
        conn.enable()
    except Exception as e:  # noqa: BLE001
        return {'ok': False, 'error': f"No se pudo conectar al semilla "
                f"{SEED_ROUTER_IP}: {type(e).__name__}: {e}"}

    try:
        _procesar(conn, SEED_ROUTER_IP, _COMANDOS[protocolo],
                  visitados, red, configurados, log)
    finally:
        try:
            conn.disconnect()
        except Exception:  # noqa: BLE001
            pass

    return {'ok': bool(configurados), 'protocolo': protocolo,
            'configurados': configurados, 'red': red, 'log': mensajes}
