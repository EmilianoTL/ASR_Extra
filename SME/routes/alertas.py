"""Blueprint /alertas — opción "Relación de alertas".

  GET /alertas/   historial de eventos, con filtros opcionales:
                  ?tipo=IFACE_UP|IFACE_DOWN|CONSOLE_ACCESS|PACKET_LOSS
                  ?router=<hostname>
                  ?limit=<N>
"""
from flask import Blueprint, jsonify, request

from database.models import Alerta

alertas_bp = Blueprint('alertas', __name__)


@alertas_bp.route('/', methods=['GET'])
def listar_alertas():
    query = Alerta.query

    tipo = request.args.get('tipo')
    if tipo:
        query = query.filter_by(tipo=tipo)

    router = request.args.get('router')
    if router:
        query = query.filter_by(router_hostname=router)

    query = query.order_by(Alerta.timestamp.desc())

    limit = request.args.get('limit', type=int)
    if limit and limit > 0:
        query = query.limit(limit)

    return jsonify([a.to_dict() for a in query.all()]), 200
