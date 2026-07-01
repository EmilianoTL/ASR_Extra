"""Blueprint /routers — opción "Enrutadores".

Endpoints de esta fase (3a):
  GET /routers/                          lista todos los routers
  GET /routers/<hostname>/               detalle (refresca info SNMP en cada GET)
  GET /routers/<hostname>/interfaces     interfaces del router

Los endpoints de métricas (GET/POST/DELETE .../metricas/<tiempo>) se agregan en
la Fase 3b junto con PySnmpOctetos.
"""
from datetime import datetime

from flask import Blueprint, jsonify, current_app

from database.models import db, Router, MetricaInterfaz
from network_utils.PySnmpInfo import obtener_info_sistema
from network_utils.PySnmpV3 import SnmpError
from network_utils import PySnmpOctetos

routers_bp = Blueprint('routers', __name__)

# Campos de tasa que se grafican (para calcular máximo y promedio).
_CAMPOS_METRICA = (
    'bits_in', 'bits_out',
    'unicast_in', 'unicast_out',
    'non_unicast_in', 'non_unicast_out',
)


@routers_bp.route('/', methods=['GET'])
def listar_routers():
    routers = Router.query.order_by(Router.hostname).all()
    return jsonify([r.to_dict() for r in routers]), 200


@routers_bp.route('/<hostname>/', methods=['GET'])
def detalle_router(hostname):
    router = Router.query.filter_by(hostname=hostname).first()
    if router is None:
        return jsonify({'error': f"Router '{hostname}' no encontrado"}), 404

    snmp_actualizado = False
    detalle_error = None
    try:
        info = obtener_info_sistema(router.ip_admin)
        router.hardware = info.get('hardware') or router.hardware
        router.sistema_operativo = info.get('sistema_operativo') or router.sistema_operativo
        router.contacto = info.get('contacto') or router.contacto
        router.location = info.get('location') or router.location
        router.uptime = info.get('uptime') or router.uptime
        router.last_seen = datetime.utcnow()
        db.session.commit()
        snmp_actualizado = True
    except SnmpError as e:
        # Degradación elegante: devolvemos lo almacenado con la marca de fallo.
        db.session.rollback()
        detalle_error = str(e)

    respuesta = router.to_dict(incluir_interfaces=True)
    respuesta['snmp_actualizado'] = snmp_actualizado
    if detalle_error:
        respuesta['snmp_error'] = detalle_error
    return jsonify(respuesta), 200


@routers_bp.route('/<hostname>/interfaces', methods=['GET'])
def interfaces_router(hostname):
    router = Router.query.filter_by(hostname=hostname).first()
    if router is None:
        return jsonify({'error': f"Router '{hostname}' no encontrado"}), 404
    return jsonify([i.to_dict() for i in router.interfaces]), 200


# ------------------------------------------------------------------------------
# Métricas de interfaz (monitoreo en hilos + estadísticas)
# ------------------------------------------------------------------------------

@routers_bp.route('/<hostname>/interfaces/<iface>/metricas/<int:tiempo>', methods=['POST'])
def iniciar_metricas(hostname, iface, tiempo):
    """Inicia un hilo que muestrea la interfaz cada `tiempo` segundos."""
    router = Router.query.filter_by(hostname=hostname).first()
    if router is None:
        return jsonify({'error': f"Router '{hostname}' no encontrado"}), 404
    if tiempo <= 0:
        return jsonify({'error': 'El intervalo debe ser mayor a 0'}), 400

    iniciado = PySnmpOctetos.iniciar_monitoreo_hilo(
        current_app._get_current_object(),
        hostname, router.ip_admin, iface, tiempo,
    )
    if not iniciado:
        return jsonify({'mensaje': 'El monitoreo ya estaba activo',
                        'activo': True}), 200
    return jsonify({'mensaje': 'Monitoreo iniciado', 'intervalo': tiempo,
                    'activo': True}), 201


@routers_bp.route('/<hostname>/interfaces/<iface>/metricas/<int:tiempo>', methods=['DELETE'])
def detener_metricas(hostname, iface, tiempo):
    """Detiene el hilo de monitoreo de la interfaz."""
    detenido = PySnmpOctetos.detener_monitoreo_interfaz(hostname, iface)
    if not detenido:
        return jsonify({'mensaje': 'No había monitoreo activo', 'activo': False}), 404
    return jsonify({'mensaje': 'Monitoreo detenido', 'activo': False}), 200


@routers_bp.route('/<hostname>/interfaces/<iface>/metricas/<int:tiempo>', methods=['GET'])
def obtener_metricas(hostname, iface, tiempo):
    """Devuelve las muestras almacenadas + máximo y promedio por métrica."""
    muestras = (
        MetricaInterfaz.query
        .filter_by(router_hostname=hostname, interfaz_api=iface)
        .order_by(MetricaInterfaz.timestamp.asc())
        .all()
    )
    estadisticas = {}
    for campo in _CAMPOS_METRICA:
        valores = [getattr(m, campo) for m in muestras if getattr(m, campo) is not None]
        estadisticas[campo] = {
            'max': max(valores) if valores else 0,
            'promedio': (sum(valores) / len(valores)) if valores else 0,
        }

    return jsonify({
        'hostname': hostname,
        'interfaz': iface,
        'intervalo': tiempo,
        'activo': PySnmpOctetos.monitoreo_activo(hostname, iface),
        'total_muestras': len(muestras),
        'estadisticas': estadisticas,
        'muestras': [m.to_dict() for m in muestras],
    }), 200
