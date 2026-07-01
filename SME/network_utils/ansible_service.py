"""Ejecución de playbooks Ansible con inventario dinámico desde la BD.

Las IPs de los routers se descubren en runtime, así que antes de cada ejecución
se genera un inventario INI temporal (en un directorio temporal que luego se
borra) a partir de la tabla `routers`.

`ejecutar_playbook(playbook, extra_vars, routers, limit)` devuelve
``{'ok', 'mensaje', 'rc', 'stats'}``.

Requiere la colección **cisco.ios** (la instala `start.sh`).
"""
import os
import tempfile

from database.models import Router

_SME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../SME
PLAYBOOKS_DIR = os.path.join(_SME_DIR, 'ansible', 'playbooks')

ROUTER_USER = os.getenv('ROUTER_USER', 'admin')
ROUTER_PASS = os.getenv('ROUTER_PASS', 'cisco123')
ROUTER_ENABLE = os.getenv('ROUTER_ENABLE', 'enable123')


def generar_inventario(routers) -> str:
    """Construye el contenido de un inventario INI para `routers`."""
    lineas = ['[routers]']
    for r in routers:
        lineas.append(f"{r.hostname} ansible_host={r.ip_admin}")
    lineas += [
        '',
        '[routers:vars]',
        f"ansible_user={ROUTER_USER}",
        f"ansible_password={ROUTER_PASS}",
        'ansible_become=yes',
        'ansible_become_method=enable',
        f"ansible_become_password={ROUTER_ENABLE}",
        'ansible_connection=network_cli',
        'ansible_network_os=cisco.ios.ios',
        '',
    ]
    return '\n'.join(lineas)


def ejecutar_playbook(playbook, extra_vars=None, routers=None, limit=None) -> dict:
    """Ejecuta un playbook contra el inventario dinámico.

    Parámetros
    ----------
    playbook : str   nombre del archivo dentro de ansible/playbooks/.
    extra_vars : dict variables extra para el playbook.
    routers : list    routers a incluir (por defecto, todos los de la BD).
    limit : str       restringe la ejecución a un host (ej. un hostname).
    """
    if routers is None:
        routers = Router.query.all()
    if not routers:
        return {'ok': False, 'mensaje': 'No hay routers en la base de datos',
                'rc': None, 'stats': None}

    # Import diferido: solo se necesita ansible en el entorno real de la SME.
    import ansible_runner

    inventario = generar_inventario(routers)
    with tempfile.TemporaryDirectory() as tmp:
        inv_path = os.path.join(tmp, 'inventario.ini')
        with open(inv_path, 'w') as f:
            f.write(inventario)

        resultado = ansible_runner.run(
            private_data_dir=tmp,
            playbook=os.path.join(PLAYBOOKS_DIR, playbook),
            inventory=inv_path,
            extravars=extra_vars or {},
            limit=limit,
            envvars={'ANSIBLE_HOST_KEY_CHECKING': 'False'},
            quiet=True,
        )

    ok = resultado.rc == 0 and resultado.status == 'successful'
    return {
        'ok': ok,
        'mensaje': resultado.status,
        'rc': resultado.rc,
        'stats': resultado.stats,
    }
