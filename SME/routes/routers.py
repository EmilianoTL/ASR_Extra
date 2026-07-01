"""Blueprint /routers — opción "Enrutadores".

Endpoints de esta fase (3a):
  GET /routers/                          lista todos los routers
  GET /routers/<hostname>/               detalle (refresca info SNMP en cada GET)
  GET /routers/<hostname>/interfaces     interfaces del router

Los endpoints de métricas (GET/POST/DELETE .../metricas/<tiempo>) se agregan en
la Fase 3b junto con PySnmpOctetos.
"""
from datetime import datetime

from flask import Blueprint, jsonify

from database.models import db, Router
from network_utils.PySnmpInfo import obtener_info_sistema
from network_utils.PySnmpV3 import SnmpError

routers_bp = Blueprint('routers', __name__)


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
