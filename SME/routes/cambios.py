"""Blueprint /cambios — opción "Cambio de datos".

  PUT /cambios/<hostname>/hostname            body {"hostname": "nuevo"}
  PUT /cambios/<hostname>/location            body {"location": "nueva"}
  PUT /cambios/<hostname>/interfaces/<iface>  body {"accion": "up"|"down"}

Convierte el nombre de interfaz de la API (f0_0) al de IOS (FastEthernet0/0)
antes de pasarlo a Ansible.
"""
from flask import Blueprint, jsonify, request

from database.models import db, Router, Interface
from network_utils.ansible_service import ejecutar_playbook

cambios_bp = Blueprint('cambios', __name__)


def _api_a_ios(nombre_api: str) -> str:
    """'f0_0' -> 'FastEthernet0/0', 'g0_1' -> 'GigabitEthernet0/1'."""
    nombre = nombre_api.lower().replace('_', '/')
    if nombre.startswith('fastethernet'):
        return 'FastEthernet' + nombre[len('fastethernet'):]
    if nombre.startswith('gigabitethernet'):
        return 'GigabitEthernet' + nombre[len('gigabitethernet'):]
    if nombre.startswith('f'):
        return 'FastEthernet' + nombre[1:]
    if nombre.startswith('g'):
        return 'GigabitEthernet' + nombre[1:]
    return nombre_api


def _buscar_router(hostname):
    return Router.query.filter_by(hostname=hostname).first()


@cambios_bp.route('/<hostname>/hostname', methods=['PUT'])
def cambiar_hostname(hostname):
    router = _buscar_router(hostname)
    if router is None:
        return jsonify({'error': f"Router '{hostname}' no encontrado"}), 404

    datos = request.get_json(silent=True) or {}
    nuevo = (datos.get('hostname') or '').strip()
    if not nuevo:
        return jsonify({'error': 'Falta el campo hostname'}), 400

    resultado = ejecutar_playbook(
        'change_hostname.yml',
        extra_vars={'nuevo_hostname': nuevo},
        routers=[router], limit=hostname,
    )
    if not resultado['ok']:
        return jsonify({'error': 'Falló el cambio por Ansible', 'detalle': resultado}), 500

    router.hostname = nuevo
    db.session.commit()
    return jsonify({'mensaje': 'Hostname actualizado', 'hostname': nuevo,
                    'ansible': resultado}), 200


@cambios_bp.route('/<hostname>/location', methods=['PUT'])
def cambiar_location(hostname):
    router = _buscar_router(hostname)
    if router is None:
        return jsonify({'error': f"Router '{hostname}' no encontrado"}), 404

    datos = request.get_json(silent=True) or {}
    nueva = (datos.get('location') or '').strip()
    if not nueva:
        return jsonify({'error': 'Falta el campo location'}), 400

    resultado = ejecutar_playbook(
        'change_location.yml',
        extra_vars={'nueva_location': nueva},
        routers=[router], limit=hostname,
    )
    if not resultado['ok']:
        return jsonify({'error': 'Falló el cambio por Ansible', 'detalle': resultado}), 500

    router.location = nueva
    db.session.commit()
    return jsonify({'mensaje': 'Location actualizada', 'location': nueva,
                    'ansible': resultado}), 200


@cambios_bp.route('/<hostname>/interfaces/<iface>', methods=['PUT'])
def cambiar_interfaz(hostname, iface):
    router = _buscar_router(hostname)
    if router is None:
        return jsonify({'error': f"Router '{hostname}' no encontrado"}), 404

    datos = request.get_json(silent=True) or {}
    accion = (datos.get('accion') or '').lower()
    if accion not in ('up', 'down'):
        return jsonify({'error': "accion debe ser 'up' o 'down'"}), 400

    nombre_ios = _api_a_ios(iface)
    resultado = ejecutar_playbook(
        'toggle_interface.yml',
        extra_vars={'nombre_interfaz': nombre_ios, 'accion': accion},
        routers=[router], limit=hostname,
    )
    if not resultado['ok']:
        return jsonify({'error': 'Falló el cambio por Ansible', 'detalle': resultado}), 500

    # Refleja el estado en la BD si la interfaz existe.
    interfaz = Interface.query.filter_by(router_id=router.id, nombre_api=iface).first()
    if interfaz:
        interfaz.estado = 'up' if accion == 'up' else 'down'
        db.session.commit()

    return jsonify({'mensaje': f"Interfaz {iface} -> {accion}",
                    'interfaz_ios': nombre_ios, 'ansible': resultado}), 200
