"""Blueprint /enrutamiento — opción "Configurar enrutamiento".

  GET  /enrutamiento/   protocolo activo actual (rip | ospf | ninguno)
  POST /enrutamiento/   body {"protocolo": "rip"|"ospf", "metodo": "encadenado"|"ansible"}

Método por defecto: **encadenado** (SSH por saltos CDP). Resuelve el problema del
huevo y la gallina: sin enrutamiento la SME solo alcanza a R1, así que se usa cada
router como salto SSH hacia el siguiente (R1->R2->R3), configurando y descubriendo
en la misma pasada. Al terminar, sincroniza la topología descubierta en la BD.

El método "ansible" (inventario directo) solo sirve cuando TODOS los routers ya son
alcanzables desde la SME (p. ej. tras haber activado el enrutamiento).
"""
from flask import Blueprint, jsonify, request

enrutamiento_bp = Blueprint('enrutamiento', __name__)

_PLAYBOOKS = {'rip': 'configure_rip.yml', 'ospf': 'configure_ospf.yml'}

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
    metodo = (datos.get('metodo') or 'encadenado').lower()

    if protocolo not in _PLAYBOOKS:
        return jsonify({'error': "protocolo debe ser 'rip' u 'ospf'"}), 400

    if metodo == 'ansible':
        return _via_ansible(protocolo)
    return _via_encadenado(protocolo)


def _via_encadenado(protocolo):
    """Configura por saltos CDP y sincroniza la topología descubierta en la BD."""
    global _protocolo_activo
    from network_utils.enrutamiento_encadenado import configurar_red_encadenada
    from routes.topologia import sincronizar_db

    resultado = configurar_red_encadenada(protocolo)
    if not resultado['ok']:
        return jsonify({'error': 'No se pudo configurar el enrutamiento',
                        'detalle': resultado}), 502

    # Poblar la topología descubierta durante la configuración.
    try:
        sincronizar_db(resultado['red'])
    except Exception as e:  # noqa: BLE001
        resultado.setdefault('avisos', []).append(f"sync BD: {e}")

    _protocolo_activo = protocolo
    return jsonify({
        'mensaje': f"Protocolo {protocolo.upper()} activado (encadenado)",
        'protocolo': protocolo,
        'configurados': resultado['configurados'],
        'total': len(resultado['configurados']),
        'log': resultado.get('log', []),
    }), 200


def _via_ansible(protocolo):
    """Configura vía inventario Ansible (requiere routers ya alcanzables)."""
    global _protocolo_activo
    from network_utils.ansible_service import ejecutar_playbook

    resultado = ejecutar_playbook(_PLAYBOOKS[protocolo])
    if not resultado['ok']:
        return jsonify({'error': 'Falló la configuración por Ansible',
                        'detalle': resultado}), 500

    _protocolo_activo = protocolo
    return jsonify({'mensaje': f"Protocolo {protocolo.upper()} activado (ansible)",
                    'protocolo': protocolo, 'ansible': resultado}), 200
