# Comandos curl para probar el backend (copiar y pegar)

Prueba endpoint por endpoint, sin Python. Desde la SME (o donde corra el backend).

Arranca el backend primero (en `SME/`, venv activo):

```sh
. .venv/bin/activate
SKIP_MONITOR=1 python app.py     # solo la API (sin traps/ping, no requiere root)
```

Define la URL base una vez:

```sh
BASE=http://127.0.0.1:5000
```

> Notas:
> - `-w '\nHTTP %{http_code}\n'` imprime el código HTTP al final.
> - Las URLs con `&` van **entre comillas**.
> - Los endpoints marcados con ⚠️ ACTÚAN sobre los routers (Ansible / hilos).

---

## 1. Estado del servicio

```sh
curl -s -w '\nHTTP %{http_code}\n' $BASE/
```
```sh
curl -s -w '\nHTTP %{http_code}\n' $BASE/health
```

## (Opcional) Insertar un router sin Python

Si aún no hay descubrimiento, mete datos con `sqlite3` (instala con `apk add sqlite`
si falta). Ejecuta desde `SME/`:

```sh
sqlite3 database/red_asr.db "INSERT INTO routers (hostname, ip_admin) VALUES ('R1','148.204.56.1');"
```
```sh
sqlite3 database/red_asr.db "INSERT INTO interfaces (nombre_api, ip_address, mascara, estado, router_id) VALUES ('f0_0','148.204.56.1','255.255.255.0','up',1);"
```


## 1b. Explorar la topología (Fase "Explorar la red")

Ver el grafo actual desde la BD. Formatos con `?formato=`:
```sh
curl -s -w '\nHTTP %{http_code}\n' $BASE/topologia/                 # JSON completo (def)
curl -s -w '\nHTTP %{http_code}\n' "$BASE/topologia/?formato=resumen"  # router: con quién conecta
curl -s "$BASE/topologia/?formato=svg" -o topologia.svg             # imagen estática SVG
curl -s "$BASE/topologia/?formato=fragmento" -o topologia_frag.html # fragmento HTML (div Plotly)
curl -s "$BASE/topologia/?formato=html" -o topologia.html           # página HTML completa
```
⚠️ Lanzar el DESCUBRIMIENTO por CDP (SSH a los routers, puebla la BD). Regresa un
resumen simplista de qué router quedó conectado con quién:
```sh
curl -s -X POST -w '\nHTTP %{http_code}\n' $BASE/topologia/
```

> El descubrimiento es lo que PUEBLA la BD. Si `/enrutamiento/` o `/routers/`
> salen vacíos, corre primero el POST de topología (o siembra con sqlite3).

## 1c. Documentación automática de la API
```sh
curl -s $BASE/docs/rutas            # lista de endpoints en JSON
```
Y en el navegador: `http://<IP-SME>:5000/docs` (tabla HTML de todos los endpoints).

## 2. Routers

```sh
curl -s -w '\nHTTP %{http_code}\n' $BASE/routers/
```
```sh
curl -s -w '\nHTTP %{http_code}\n' $BASE/routers/R1/
```
```sh
curl -s -w '\nHTTP %{http_code}\n' $BASE/routers/R1/interfaces
```

## 3. Métricas

```sh
curl -s -w '\nHTTP %{http_code}\n' $BASE/routers/R1/interfaces/f0_0/metricas/20
```
⚠️ inicia el hilo de monitoreo (SNMP real cada 20s):
```sh
curl -s -X POST -w '\nHTTP %{http_code}\n' $BASE/routers/R1/interfaces/f0_0/metricas/20
```
⚠️ detiene el hilo:
```sh
curl -s -X DELETE -w '\nHTTP %{http_code}\n' $BASE/routers/R1/interfaces/f0_0/metricas/20
```

## 4. Alertas

```sh
curl -s -w '\nHTTP %{http_code}\n' $BASE/alertas/
```
```sh
curl -s -w '\nHTTP %{http_code}\n' "$BASE/alertas/?tipo=IFACE_DOWN"
```
```sh
curl -s -w '\nHTTP %{http_code}\n' "$BASE/alertas/?router=R1&limit=5"
```

## 5. Enrutamiento

```sh
curl -s -w '\nHTTP %{http_code}\n' $BASE/enrutamiento/
```
⚠️ activa OSPF **encadenado por CDP** (salta R1->R2->R3; NO requiere enrutamiento
previo y de paso PUEBLA la topología en la BD). Método por defecto:
```sh
curl -s -X POST -H 'Content-Type: application/json' -d '{"protocolo":"ospf"}' -w '\nHTTP %{http_code}\n' $BASE/enrutamiento/
```
⚠️ igual con RIP:
```sh
curl -s -X POST -H 'Content-Type: application/json' -d '{"protocolo":"rip"}' -w '\nHTTP %{http_code}\n' $BASE/enrutamiento/
```
Opcional — método Ansible (solo si TODOS los routers ya son alcanzables):
```sh
curl -s -X POST -H 'Content-Type: application/json' -d '{"protocolo":"ospf","metodo":"ansible"}' -w '\nHTTP %{http_code}\n' $BASE/enrutamiento/
```

> Con el método encadenado (por defecto) **ya no necesitas** explorar antes: este
> POST configura el enrutamiento saltando router por router y llena la topología.
> Después, `POST /topologia/` refresca el descubrimiento con todo ya alcanzable.

## 6. Cambio de datos

⚠️ cambia hostname (Ansible):
```sh
curl -s -X PUT -H 'Content-Type: application/json' -d '{"hostname":"R1"}' -w '\nHTTP %{http_code}\n' $BASE/cambios/R1/hostname
```
⚠️ cambia location (Ansible):
```sh
curl -s -X PUT -H 'Content-Type: application/json' -d '{"location":"Lab-ASR"}' -w '\nHTTP %{http_code}\n' $BASE/cambios/R1/location
```
⚠️ activa/desactiva interfaz (Ansible):
```sh
curl -s -X PUT -H 'Content-Type: application/json' -d '{"accion":"up"}' -w '\nHTTP %{http_code}\n' $BASE/cambios/R1/interfaces/f0_0
```
```sh
curl -s -X PUT -H 'Content-Type: application/json' -d '{"accion":"down"}' -w '\nHTTP %{http_code}\n' $BASE/cambios/R1/interfaces/f0_0
```

## Validaciones (deben dar 400)

```sh
curl -s -X POST -H 'Content-Type: application/json' -d '{"protocolo":"bgp"}' -w '\nHTTP %{http_code}\n' $BASE/enrutamiento/
```
```sh
curl -s -X PUT -H 'Content-Type: application/json' -d '{"accion":"xxx"}' -w '\nHTTP %{http_code}\n' $BASE/cambios/R1/interfaces/f0_0
```
