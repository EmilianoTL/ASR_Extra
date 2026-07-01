# Pruebas del backend (endpoint por endpoint)

Kit para ir verificando el backend sin frontend. Dos piezas:

- **`datos_prueba.py`** — inserta routers/interfaces/métricas/alertas a mano
  (útil mientras el descubrimiento CDP no existe).
- **`probar_endpoints.sh`** — recorre todos los endpoints con `curl`.

## 0. Arrancar el backend

Desde `SME/`, con el venv activo:

```sh
. .venv/bin/activate
python app.py            # queda escuchando en el puerto 5000
```

En **otra terminal** (o con `python app.py &`) corre las pruebas.

## 1. Poblar datos de prueba

```sh
# Un router con su IP real (para probar el refresco SNMP contra el equipo real)
python pruebas/datos_prueba.py router R1 148.204.56.1 \
    --iface f0_0:148.204.56.1:255.255.255.0:up \
    --iface f1_0:8.8.8.1:255.255.255.252:up

# Muestras de métricas de ejemplo (para ver estadísticas sin equipo real)
python pruebas/datos_prueba.py metricas R1 f0_0 --n 10

# Una alerta de ejemplo
python pruebas/datos_prueba.py alerta IFACE_DOWN R1 --iface f0_0 --desc "prueba manual"

python pruebas/datos_prueba.py listar     # resumen de la BD
python pruebas/datos_prueba.py limpiar    # borrar todo
```

## 2. Probar los endpoints

```sh
# Solo lecturas (seguro, no toca los routers):
sh pruebas/probar_endpoints.sh

# Apuntando a otro host/interfaz:
HOST=R2 IFACE=f1_1 sh pruebas/probar_endpoints.sh

# Incluyendo operaciones que ACTÚAN sobre los routers vía Ansible
# (inicia monitoreo real, activa OSPF, cambia location/interfaz):
ESCRIBIR=1 sh pruebas/probar_endpoints.sh
```

> ⚠️ `ESCRIBIR=1` ejecuta POST `/enrutamiento/` (reconfigura TODOS los routers) y
> los PUT de `/cambios/` (reconfiguran el router). Úsalo solo cuando quieras probar
> de verdad contra la topología. Sin ese flag, el script solo hace lecturas y una
> validación 400 de ejemplo.

## 3. Probar SNMP directo contra un router (opcional)

Para aislar si un problema es de SNMP o del endpoint:

```sh
python -c "from network_utils.PySnmpInfo import obtener_info_sistema; \
print(obtener_info_sistema('148.204.56.1'))"
```

## Qué verificar en cada endpoint

| Endpoint | Qué esperar |
|----------|-------------|
| `GET /` , `GET /health` | 200, estado Online / BD conectada |
| `GET /routers/` | lista (vacía o con lo insertado) |
| `GET /routers/<h>/` | 200; `snmp_actualizado:true` si el equipo responde, o datos guardados + `snmp_error` si no |
| `GET /routers/<h>/interfaces` | interfaces del router |
| `GET .../metricas/<t>` | `estadisticas` (máx/promedio) + `muestras` |
| `POST/DELETE .../metricas/<t>` | inicia/detiene el hilo de monitoreo |
| `GET /alertas/` | historial; filtros `?tipo=`, `?router=`, `?limit=` |
| `GET/POST /enrutamiento/` | protocolo activo / activa RIP-OSPF |
| `PUT /cambios/<h>/...` | cambia hostname/location/interfaz (Ansible) |
