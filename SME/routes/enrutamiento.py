"""Blueprint /enrutamiento — opción "Configurar enrutamiento".

  GET  /enrutamiento/   protocolo activo actual (rip | ospf | ninguno)
  POST /enrutamiento/   body {"protocolo": "rip"|"ospf"} -> Ansible en todos
"""
from flask import Blueprint, jsonify, request

from network_utils.ansible_service import ejecutar_playbook

enrutamiento_bp = Blueprint('enrutamiento', __name__)

_PLAYBOOKS = {
    'rip': 'configure_rip.yml',
    'ospf': 'configure_ospf.yml',
}

# Estado en memoria del último protocolo activado con éxito.
_protocolo_activo = 'ninguno'


@enrutamiento_bp.route('/', methods=['GET'])
def obtener_protocolo():
    return jsonify({'protocolo': _protocolo_activo}), 200


@enrutamiento_bp.route('/', methods=['POST'])
def configurar_protocolo():
    global _protocolo_activo
    datos = request.get_json(silent=True) or {}
    protocolo = (datos.get('protocolo') or '').lower()

    if protocolo not in _PLAYBOOKS:
        return jsonify({'error': "protocolo debe ser 'rip' u 'ospf'"}), 400

    resultado = ejecutar_playbook(_PLAYBOOKS[protocolo])
    if not resultado['ok']:
        return jsonify({'error': 'Falló la configuración por Ansible',
                        'detalle': resultado}), 500

    _protocolo_activo = protocolo
    return jsonify({'mensaje': f"Protocolo {protocolo.upper()} activado",
                    'protocolo': protocolo, 'ansible': resultado}), 200
