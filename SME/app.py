"""Aplicación Flask del sistema de monitoreo de red (ASR).

Fase 1 (cimientos): inicializa Flask + CORS + base de datos SQLite y expone
rutas básicas (`/` y `/health`). Los blueprints REST y los hilos de monitoreo
(traps SNMPv3 y ping) se registran en fases posteriores; sus puntos de enganche
quedan marcados con TODO para no romper el arranque mientras no existan.
"""
import os

from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import text

from database.models import db

load_dotenv()


def crear_app():
    """App factory: construye y configura la aplicación Flask."""
    app = Flask(__name__)
    CORS(app)

    # Registro de hilos de monitoreo de métricas por interfaz (Fase 3).
    app.hilos_snmp_activos = {}

    # --- Base de datos (SQLite local) ---
    nombre_db = os.getenv('DB_NAME', 'red_asr.db')
    basedir = os.path.abspath(os.path.dirname(__file__))
    ruta_db = os.path.join(basedir, 'database', nombre_db)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + ruta_db
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    with app.app_context():
        # La BD arranca vacía; se puebla al "Explorar la red" (sin seed).
        db.create_all()
    print(f"[DB] Base de datos lista en: {ruta_db}")

    _registrar_rutas_base(app)

    # --- Blueprints REST ---
    from routes.routers import routers_bp
    app.register_blueprint(routers_bp, url_prefix='/routers')

    # TODO (Fase 3): registrar blueprints restantes conforme se implementen
    #   from routes.topologia import topologia_bp
    #   from routes.enrutamiento import enrutamiento_bp
    #   from routes.cambios import cambios_bp
    #   from routes.alertas import alertas_bp
    #   app.register_blueprint(topologia_bp, url_prefix='/topologia')
    #   app.register_blueprint(enrutamiento_bp, url_prefix='/enrutamiento')
    #   app.register_blueprint(cambios_bp, url_prefix='/cambios')
    #   app.register_blueprint(alertas_bp, url_prefix='/alertas')

    # TODO (Fase 3/8): iniciar hilos de monitoreo en background
    #   from network_utils.PySnmpTraps import asegurar_receptor_corriendo
    #   from network_utils.ping_monitor import iniciar_monitor
    #   asegurar_receptor_corriendo(app)
    #   iniciar_monitor(app)

    return app


def _registrar_rutas_base(app):
    """Rutas mínimas de estado del servicio."""

    @app.route('/')
    def index():
        return jsonify({
            'proyecto': 'Sistema de Monitoreo de Red ASR',
            'version': '0.1.0',
            'status': 'Online',
        })

    @app.route('/health', methods=['GET'])
    def health_check():
        try:
            db.session.execute(text('SELECT 1'))
            return jsonify({
                'api_status': 'Online',
                'database_status': 'Conectada',
                'motor': 'SQLite',
            }), 200
        except Exception as e:  # noqa: BLE001
            return jsonify({
                'api_status': 'Online',
                'database_status': 'Error',
                'error_detalle': str(e),
            }), 500


app = crear_app()


if __name__ == '__main__':
    puerto = int(os.getenv('FLASK_PUERTO', 5000))
    modo_debug = os.getenv('FLASK_DEBUG', 'False') == 'True'
    app.run(host='0.0.0.0', port=puerto, debug=modo_debug)
