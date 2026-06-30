"""Modelos SQLAlchemy del sistema de monitoreo de red.

Cuatro entidades:
  - Router            : un dispositivo Cisco descubierto/monitoreado.
  - Interface         : una interfaz de un router (y a qué vecino se conecta).
  - MetricaInterfaz   : una muestra de métricas de tráfico de una interfaz.
  - Alerta            : un evento (interfaz up/down, acceso por consola, pérdida).

La BD arranca vacía y se puebla dinámicamente al "Explorar la red" (no hay seed).
"""
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Router(db.Model):
    __tablename__ = 'routers'

    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(50), unique=True, nullable=False)
    ip_admin = db.Column(db.String(15), unique=True, nullable=False)
    location = db.Column(db.String(100))
    hardware = db.Column(db.String(100))
    sistema_operativo = db.Column(db.String(100))
    contacto = db.Column(db.String(100))
    uptime = db.Column(db.String(50))
    last_seen = db.Column(db.DateTime)

    # Un router tiene muchas interfaces.
    interfaces = db.relationship(
        'Interface',
        foreign_keys='Interface.router_id',
        backref='router',
        lazy=True,
        cascade='all, delete-orphan',
    )

    def to_dict(self, incluir_interfaces=False):
        datos = {
            'id': self.id,
            'hostname': self.hostname,
            'ip_admin': self.ip_admin,
            'location': self.location,
            'hardware': self.hardware,
            'sistema_operativo': self.sistema_operativo,
            'contacto': self.contacto,
            'uptime': self.uptime,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
        }
        if incluir_interfaces:
            datos['interfaces'] = [i.to_dict() for i in self.interfaces]
        return datos


class Interface(db.Model):
    __tablename__ = 'interfaces'

    id = db.Column(db.Integer, primary_key=True)
    nombre_api = db.Column(db.String(20))          # ej. 'f0_0'
    ip_address = db.Column(db.String(15))
    mascara = db.Column(db.String(15))
    estado = db.Column(db.String(10), default='down')   # 'up' | 'down'

    # A qué router pertenece (obligatorio).
    router_id = db.Column(db.Integer, db.ForeignKey('routers.id'), nullable=False)
    # A qué router vecino se conecta físicamente (lo llena el descubrimiento CDP).
    conectado_a_router_id = db.Column(
        db.Integer, db.ForeignKey('routers.id'), nullable=True
    )

    def to_dict(self):
        return {
            'id': self.id,
            'nombre_api': self.nombre_api,
            'ip_address': self.ip_address,
            'mascara': self.mascara,
            'estado': self.estado,
            'router_id': self.router_id,
            'conectado_a_router_id': self.conectado_a_router_id,
        }


class MetricaInterfaz(db.Model):
    __tablename__ = 'metrica_interfaz'

    id = db.Column(db.Integer, primary_key=True)
    router_hostname = db.Column(db.String(50), nullable=False)   # relación lógica
    interfaz_api = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # Tráfico (bits/s).
    bits_in = db.Column(db.Float)
    bits_out = db.Column(db.Float)
    # Paquetes unicast (paquetes/s).
    unicast_in = db.Column(db.Float)
    unicast_out = db.Column(db.Float)
    # Paquetes no-unicast (paquetes/s).
    non_unicast_in = db.Column(db.Float)
    non_unicast_out = db.Column(db.Float)

    def to_dict(self):
        return {
            'id': self.id,
            'router_hostname': self.router_hostname,
            'interfaz_api': self.interfaz_api,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'bits_in': self.bits_in,
            'bits_out': self.bits_out,
            'unicast_in': self.unicast_in,
            'unicast_out': self.unicast_out,
            'non_unicast_in': self.non_unicast_in,
            'non_unicast_out': self.non_unicast_out,
        }


class Alerta(db.Model):
    __tablename__ = 'alertas'

    # Tipos de alerta admitidos.
    IFACE_UP = 'IFACE_UP'
    IFACE_DOWN = 'IFACE_DOWN'
    CONSOLE_ACCESS = 'CONSOLE_ACCESS'
    PACKET_LOSS = 'PACKET_LOSS'

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    tipo = db.Column(db.String(20), nullable=False)
    router_hostname = db.Column(db.String(50))
    interfaz_api = db.Column(db.String(20))     # nullable
    descripcion = db.Column(db.String(255))

    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'tipo': self.tipo,
            'router_hostname': self.router_hostname,
            'interfaz_api': self.interfaz_api,
            'descripcion': self.descripcion,
        }
