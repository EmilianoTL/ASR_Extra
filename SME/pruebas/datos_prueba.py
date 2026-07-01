#!/usr/bin/env python3
"""Utilidad de datos de prueba para la BD (mientras no hay descubrimiento).

Permite insertar routers, interfaces, métricas y alertas a mano para poder
probar los endpoints de lectura sin depender del descubrimiento CDP.

Ejecutar desde la carpeta SME con el venv activo:

  python pruebas/datos_prueba.py router R1 148.204.56.1
  python pruebas/datos_prueba.py router R1 148.204.56.1 --iface f0_0:148.204.56.1:255.255.255.0:up
  python pruebas/datos_prueba.py metricas R1 f0_0 --n 10
  python pruebas/datos_prueba.py alerta IFACE_DOWN R1 --iface f0_0 --desc "prueba"
  python pruebas/datos_prueba.py listar
  python pruebas/datos_prueba.py limpiar
"""
import sys
import os
import argparse
import random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
from database.models import db, Router, Interface, MetricaInterfaz, Alerta  # noqa: E402


def cmd_router(args):
    with app.app_context():
        r = Router.query.filter_by(hostname=args.hostname).first()
        if r is None:
            r = Router(hostname=args.hostname, ip_admin=args.ip)
            db.session.add(r)
            db.session.commit()
            print(f"[+] Router {args.hostname} ({args.ip}) creado (id={r.id})")
        else:
            r.ip_admin = args.ip
            db.session.commit()
            print(f"[=] Router {args.hostname} ya existía; ip_admin actualizada")

        for spec in args.iface or []:
            partes = spec.split(':')
            nombre = partes[0]
            ip = partes[1] if len(partes) > 1 else None
            mascara = partes[2] if len(partes) > 2 else None
            estado = partes[3] if len(partes) > 3 else 'down'
            existente = Interface.query.filter_by(router_id=r.id, nombre_api=nombre).first()
            if existente is None:
                db.session.add(Interface(nombre_api=nombre, ip_address=ip,
                                         mascara=mascara, estado=estado, router_id=r.id))
                print(f"    [+] interfaz {nombre} ({ip}/{mascara}, {estado})")
            else:
                existente.ip_address, existente.mascara, existente.estado = ip, mascara, estado
                print(f"    [=] interfaz {nombre} actualizada")
        db.session.commit()


def cmd_metricas(args):
    with app.app_context():
        base = datetime.utcnow() - timedelta(seconds=20 * args.n)
        for i in range(args.n):
            db.session.add(MetricaInterfaz(
                router_hostname=args.hostname, interfaz_api=args.iface,
                timestamp=base + timedelta(seconds=20 * i),
                bits_in=random.uniform(1e5, 1e6), bits_out=random.uniform(1e5, 1e6),
                unicast_in=random.uniform(10, 200), unicast_out=random.uniform(10, 200),
                non_unicast_in=random.uniform(0, 20), non_unicast_out=random.uniform(0, 20),
            ))
        db.session.commit()
        print(f"[+] {args.n} muestras de métricas para {args.hostname}/{args.iface}")


def cmd_alerta(args):
    with app.app_context():
        db.session.add(Alerta(tipo=args.tipo, router_hostname=args.hostname,
                              interfaz_api=args.iface, descripcion=args.desc,
                              timestamp=datetime.utcnow()))
        db.session.commit()
        print(f"[+] Alerta {args.tipo} para {args.hostname} creada")


def cmd_listar(args):
    with app.app_context():
        print("Routers:")
        for r in Router.query.all():
            print(f"  - {r.hostname} ({r.ip_admin}) | {len(r.interfaces)} interfaz(es)")
        print(f"Métricas: {MetricaInterfaz.query.count()} filas")
        print(f"Alertas: {Alerta.query.count()} filas")


def cmd_limpiar(args):
    with app.app_context():
        for modelo in (MetricaInterfaz, Alerta, Interface, Router):
            n = modelo.query.delete()
            print(f"  - {modelo.__tablename__}: {n} borradas")
        db.session.commit()
        print("[+] BD limpia")


def main():
    p = argparse.ArgumentParser(description="Datos de prueba para la BD")
    sub = p.add_subparsers(dest='cmd', required=True)

    pr = sub.add_parser('router', help='crea/actualiza un router (+interfaces)')
    pr.add_argument('hostname'); pr.add_argument('ip')
    pr.add_argument('--iface', action='append',
                    help='nombre:ip:mascara:estado (repetible)')
    pr.set_defaults(func=cmd_router)

    pm = sub.add_parser('metricas', help='inserta N muestras de métricas')
    pm.add_argument('hostname'); pm.add_argument('iface')
    pm.add_argument('--n', type=int, default=10)
    pm.set_defaults(func=cmd_metricas)

    pa = sub.add_parser('alerta', help='inserta una alerta')
    pa.add_argument('tipo', help='IFACE_UP|IFACE_DOWN|CONSOLE_ACCESS|PACKET_LOSS')
    pa.add_argument('hostname')
    pa.add_argument('--iface', default=None); pa.add_argument('--desc', default='')
    pa.set_defaults(func=cmd_alerta)

    sub.add_parser('listar', help='resumen de la BD').set_defaults(func=cmd_listar)
    sub.add_parser('limpiar', help='borra todo').set_defaults(func=cmd_limpiar)

    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
