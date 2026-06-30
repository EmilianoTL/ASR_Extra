# PLAN — Sistema de Monitoreo de Red RESTful (ASR Examen Extraordinario)

> Documento técnico de planeación para `EmilianoTL/ASR_Extra`.
> Referencia (solo lectura): `EmilianoTL/ASR_FinalProject`.
> Rama de trabajo: `claude/asr-extra-network-monitoring-tyc038`.
> Última actualización: 2026-06-29.

---

## 0. Decisiones cerradas

| Tema | Decisión |
|------|----------|
| SNMP | **SNMPv3** (SHA auth + DES56 priv). NO v2c. |
| Credenciales SSH/SNMP | **Desde `.env`** (no formulario en la web). |
| Config de routers | **Ansible** (`cisco.ios`) para toda configuración. |
| Descubrimiento | **Netmiko + CDP (BFS)**. |
| SNMP lib | **pysnmp 7.1 async**. |
| Background | **threading.Thread daemon** (no APScheduler). |
| Pérdida de paquetes | **subprocess ping**. |
| Backend | **Flask + SQLAlchemy (SQLite)**. |
| Visualización | **Plotly** (gráficas de métricas y grafo de topología) + **networkx** (modelo/algoritmos del grafo). |
| Frontend | **Astro 4 + TypeScript (SSR)** + Tailwind + **Plotly.js** (render de figuras Plotly). |
| Idioma UI | **Español**. |
| Arranque | Se entrega `PLAN.md` ANTES de escribir código de la app. |

---

## 1. Qué pide el examen (fuente: PDF)

Página web RESTful para monitorear/administrar una red Cisco en GNS3. La página inicial ofrece 5 opciones:

1. **Configurar enrutamiento** — sin protocolo previo, activar a elección **RIP u OSPF en TODA la red**.
2. **Explorar la red** — sin información previa, usando solo credenciales SSH+SNMP comunes, descubrir la topología, guardarla en BD y mostrarla **gráficamente**.
3. **Enrutadores** — vía SNMPv3: **hardware, SO, contacto, tiempo de actividad**, y guardarlos en BD.
   - **Interfaces**: estado (up/down), IP, máscara, vecino conectado; y **gráficas cada 20 s** (X=tiempo) de:
     - Tráfico **bits/s** (máx y promedio, in/out).
     - **Unicast** paquetes/s (máx y promedio, in/out).
     - **No-unicast** paquetes/s (máx y promedio, in/out).
4. **Relación de alertas** — actuales e históricas, con timestamp y tipo:
     - Interfaz up/down.
     - Acceso por consola a cualquier router.
     - Pérdida de paquetes R1↔R2 > 25%.
5. **Cambio de datos** — hostname, locación, activar/desactivar interfaces.

---

## 2. Cómo se califica (RÚBRICA — 10 puntos)

Proceso de revisión (secuencial; si un paso falla, se detiene y se califica hasta ahí):
1. Verifican que NO haya protocolo de enrutamiento preconfigurado.
2. **Piden alterar la topología** (borran un dispositivo o interfaz) → el descubrimiento debe ser dinámico.
3. Activan configurar enrutamiento.
4. Activan explorar la red.
5. Revisan info de routers e interfaces.
6. Piden un cambio de dato.
7. Fuerzan alertas y verifican que aparezcan.

| # | Condición | Peso aprox. |
|---|-----------|-------------|
| 1 | Página de inicio con todas las opciones | 0.5 |
| 2 | La configuración de enrutamiento se activa en los routers | 1 |
| 3 | Se detecta la topología | 1 |
| 4 | Se despliega la info de los dispositivos | 1 |
| 5 | Info general de las interfaces | 1 |
| 6 | **Gráficas actualizando en los tiempos indicados** | **2** |
| 7 | **Alerta disparada aparece correctamente** | **2** |
| 8 | Cambio de datos corroborable | 0.5 |
| | **TOTAL** | **10** |

> Los pesos exactos provienen de una tabla del PDF que se extrajo parcialmente desordenada; **confirmar con el profesor**. Lo seguro: **gráficas en tiempo real + alertas ≈ 40% de la nota** → máxima prioridad.

---

## 3. Arquitectura de archivos objetivo

```
ASR_Extra/
├── PLAN.md                      # este documento
├── start.sh                     # arranque: colección ansible, .env, Flask + Astro
├── Infrastructure/              # Exportaciones GNS3 + configs + scripts de despliegue
│   ├── README.md                # topología, direccionamiento y config base
│   ├── Topologia/               # export del proyecto GNS3 (.gns3 + recursos)
│   └── configs/
│       ├── R1/R1_startup-config.cfg   # interfaces + SSH + SNMPv3 + CDP (sin enrutamiento)
│       ├── R2/R2_startup-config.cfg
│       ├── R3/R3_startup-config.cfg
│       ├── Sw1/                 # switch (sin IP)
│       └── EndDevices/
│           ├── PC1/PC1_startup.vpc    # VPCS (LAN de R2)
│           ├── PC2/PC2_startup.vpc    # VPCS (LAN de R3)
│           └── SME/             # MV Alpine: red + scripts de arranque
│               ├── interfaces   # eth0 estática (topología) + eth1 DHCP (NAT)
│               ├── resolv.conf  # DNS 1.1.1.1
│               ├── sme-routes.sh# rutas: topología->eth0 (vía R1), resto->eth1
│               ├── setup_sme.sh # provisión: red+paquetes+clona repo+venv+cisco.ios
│               ├── sync_github.sh# git pull de la rama en la SME
│               └── README.md    # diseño de red de la SME + uso
├── SME/                         # Backend Flask
│   ├── app.py                   # app, blueprints, arranca hilos (traps + ping)
│   ├── requirements.txt
│   ├── .env.example
│   ├── database/
│   │   └── models.py            # Router, Interface, MetricaInterfaz, Alerta
│   ├── routes/
│   │   ├── routers.py           # /routers/...
│   │   ├── topologia.py         # /topologia/...
│   │   ├── enrutamiento.py      # /enrutamiento/...
│   │   ├── cambios.py           # /cambios/...
│   │   └── alertas.py           # /alertas/...
│   ├── network_utils/           # capa de infraestructura (acceso a la red)
│   │   ├── PySnmpV3.py          # helper SNMPv3 (UsmUserData, get/walk sync+async)
│   │   ├── PySnmpInfo.py        # MIB System (hardware/SO/contacto/uptime/location)
│   │   ├── PySnmpOctetos.py     # monitoreo 6 contadores por interfaz (hilos)
│   │   ├── PySnmpTraps.py       # receptor de traps SNMPv3 -> Alertas
│   │   ├── ssh_netmiko.py       # conexión SSH/CDP (Netmiko) para descubrimiento
│   │   ├── ansible_service.py   # inventario dinámico + ansible_runner
│   │   └── ping_monitor.py      # pérdida de paquetes R1->R2
│   ├── viz/                     # capa de visualización (Plotly + networkx)
│   │   ├── grafo_topologia.py  # construye grafo networkx -> figura Plotly (JSON)
│   │   └── graficas_metricas.py# series de tiempo Plotly (bits/s, unicast, no-unicast)
│   └── ansible/playbooks/
│       ├── configure_rip.yml
│       ├── configure_ospf.yml
│       ├── change_hostname.yml
│       ├── change_location.yml
│       └── toggle_interface.yml
└── Frontend/                    # Astro + TypeScript
    ├── package.json
    ├── astro.config.mjs         # output: 'server', react + tailwind
    ├── tailwind.config.mjs
    ├── .env                     # PUBLIC_API_URL
    └── src/
        ├── lib/api.ts           # wrapper fetch tipado
        └── pages/
            ├── index.astro       # 5 tarjetas
            ├── topologia.astro   # figura Plotly (grafo) + botón descubrir
            ├── enrutamiento.astro# botones RIP/OSPF
            ├── alertas.astro     # tabla filtrable, auto-refresh 15s
            ├── cambios.astro     # formularios hostname/location/interfaz
            └── routers/
                ├── index.astro   # grid de routers
                └── [hostname].astro  # detalle + Plotly.js (polling 20s)
```

---

## 4. Modelo de datos (SQLAlchemy)

```python
class Router:        id, hostname(uniq), ip_admin(uniq), location, hardware,
                     sistema_operativo, contacto, uptime, last_seen, interfaces[]
class Interface:     id, nombre_api('f0_0'), ip_address, mascara, estado('up'/'down'),
                     router_id(FK), conectado_a_router_id(FK nullable)
class MetricaInterfaz: id, router_hostname, interfaz_api, timestamp,
                     bits_in, bits_out, unicast_in, unicast_out,
                     non_unicast_in, non_unicast_out
class Alerta:        id, timestamp, tipo(IFACE_UP|IFACE_DOWN|CONSOLE_ACCESS|PACKET_LOSS),
                     router_hostname, interfaz_api(nullable), descripcion
```

Diferencias vs referencia: se elimina `Usuario`/`router_usuarios`; `MetricaOctetos` (1 contador) se reemplaza por `MetricaInterfaz` (6 contadores); `EventoTrap` se generaliza a `Alerta`.

---

## 5. Endpoints REST

### `/routers/`
| Método | Ruta | Acción |
|---|---|---|
| GET | `/routers/` | Lista routers |
| GET | `/routers/<hostname>/` | Info (refresca SNMP en cada GET) |
| GET | `/routers/<hostname>/interfaces` | Interfaces |
| GET | `/routers/<hostname>/interfaces/<iface>/metricas/<tiempo>` | Stats (máx, promedio) + muestras |
| POST | `…/metricas/<tiempo>` | Inicia hilo de monitoreo |
| DELETE | `…/metricas/<tiempo>` | Detiene monitoreo |

### `/topologia/`
| GET | `/topologia/` | routers + vecinos + enlaces |
| POST | `/topologia/` | Lanza descubrimiento BFS por CDP |

### `/enrutamiento/`
| GET | `/enrutamiento/` | Protocolo activo actual |
| POST | `/enrutamiento/` | `{"protocolo":"rip"|"ospf"}` → Ansible en todos |

### `/cambios/`
| PUT | `/cambios/<hostname>/hostname` | `{"hostname":"nuevo"}` |
| PUT | `/cambios/<hostname>/location` | `{"location":"nueva"}` |
| PUT | `/cambios/<hostname>/interfaces/<iface>` | `{"accion":"up"|"down"}` |

### `/alertas/`
| GET | `/alertas/` | Historial (`?tipo=&router=&limit=`) |

---

## 6. SNMPv3 — detalle

Credenciales desde `.env`: `SNMP_USER`, `SNMP_AUTH_PASS` (SHA), `SNMP_PRIV_PASS` (DES56).

> Nota: los routers c7200 del lab solo aceptan **DES56** como protocolo de privacidad
> SNMPv3 (no AES128). Por eso `privProtocol` es DES (`usmDESPrivProtocol`).

```python
UsmUserData(SNMP_USER, authKey=SNMP_AUTH_PASS, privKey=SNMP_PRIV_PASS,
            authProtocol=usmHMACSHAAuthProtocol, privProtocol=usmDESPrivProtocol)
```

`PySnmpV3.py` expone `snmp_get/snmp_walk` (sync) y `snmp_get_async/snmp_walk_async`.

OIDs:
- **System**: sysDescr `1.3.6.1.2.1.1.1.0`, sysContact `.1.4.0`, sysName `.1.5.0`, sysLocation `.1.6.0`, sysUpTime `.1.3.0`.
- **ifTable**: ifDescr `…2.2.1.2`, ifInOctets `.10`, ifOutOctets `.16`, ifInUcastPkts `.11`, ifOutUcastPkts `.17`, ifInNUcastPkts `.12`, ifOutNUcastPkts `.18`. Manejo de wrap-around Counter32.
- **Traps**: LinkDown `1.3.6.1.6.3.1.1.5.3`, LinkUp `.5.4`, TTY login `1.3.6.1.4.1.9.9.41.2.0.1`.

Receptor (`PySnmpTraps.py`): `config.addV3User()` + `ntfrcv.NotificationReceiver` en hilo daemon. LinkUp→IFACE_UP, LinkDown→IFACE_DOWN, TTY→CONSOLE_ACCESS → guarda `Alerta`. Singleton `asegurar_receptor_corriendo(app)`.

---

## 7. Ansible — detalle

`ansible_service.py`: genera inventario INI **temporal desde la BD** (IPs en runtime), ejecuta, borra. `ejecutar_playbook(playbook, extra_vars, routers)` → `ansible_runner.run()` → `{ok, mensaje, rc, stats}`. Requiere colección `cisco.ios` (instalada por `start.sh`).

Playbooks (`cisco.ios.ios_config`, `save_when: always`):
- `configure_rip.yml`: `router rip / version 2 / network 0.0.0.0 / no auto-summary`.
- `configure_ospf.yml`: `router ospf 1 / network 0.0.0.0 255.255.255.255 area 0`.
- `change_hostname.yml`: var `nuevo_hostname`.
- `change_location.yml`: var `nueva_location` → `snmp-server location`.
- `toggle_interface.yml`: vars `nombre_interfaz`, `accion` → `no shutdown`/`shutdown`.

Conversión `f0_0` ↔ `FastEthernet0/0` con `_api_a_ios()` en `cambios.py`.

---

## 8. Monitoreo en background (threading)

- **Métricas** (`PySnmpOctetos.py`): un hilo daemon por interfaz (`threading.Event`), lee 6 contadores cada `<tiempo>`s, calcula deltas (bits/s = Δoctetos×8/Δt; pkts/s = Δpkts/Δt). API: `iniciar_monitoreo_hilo()`, `detener_monitoreo_interfaz()`, `monitoreo_activo()`.
- **Ping** (`ping_monitor.py`): hilo daemon, cada `PACKET_LOSS_INTERVAL`s hace `subprocess ping` R1→ip_admin(R2) con `PACKET_LOSS_COUNT` paquetes; si pérdida > `PACKET_LOSS_THRESHOLD`% → `Alerta(PACKET_LOSS)`.
- **Traps**: receptor daemon (§6).
- En `app.py` al arrancar: `asegurar_receptor_corriendo(app)` + `iniciar_monitor(app)`.

---

## 9. Frontend (Astro + TS) y visualización (Plotly + networkx)

**Estrategia de visualización:** las figuras se construyen en el **backend** con
**Plotly** (a partir de datos de la BD) y se exponen como **JSON de figura Plotly**;
el frontend solo las renderiza con **Plotly.js** (`Plotly.react`). Esto mantiene la
lógica de graficado en Python (modular y testeable) y deja al frontend "tonto".

- **`viz/grafo_topologia.py`**: construye un grafo **networkx** (nodos = routers,
  aristas = enlaces descubiertos por CDP), calcula el layout (`spring_layout`) y
  detecta componentes/conectividad; exporta una **figura Plotly** (scatter de nodos
  + líneas de aristas) servida por `GET /topologia/`.
- **`viz/graficas_metricas.py`**: a partir de `MetricaInterfaz`, arma **3 figuras
  Plotly** de series de tiempo (eje X = tiempo): tráfico bits/s, unicast pkt/s,
  no-unicast pkt/s — cada una con trazas in/out y anotación de máx y promedio.
- Frontend:
  - `astro.config.mjs`: `output:'server'`, integraciones react + tailwind.
  - `src/lib/api.ts`: `apiFetch<T>()` + objeto `api`; base URL desde `import.meta.env.PUBLIC_API_URL`.
  - `Plotly.js` (CDN) renderiza las figuras de métricas (polling 20 s) y el grafo de topología.
  - Páginas: index (5 tarjetas), topologia, enrutamiento, routers (+detalle), alertas (auto-refresh 15 s), cambios.

---

## 10. Variables de entorno (`.env.example`)

```bash
FLASK_APP=app.py
FLASK_DEBUG=True
FLASK_PUERTO=5000
DB_NAME=red_asr.db
# SSH / Ansible
ROUTER_USER=admin
ROUTER_PASS=cisco123
ROUTER_ENABLE=enable123
# SNMPv3
SNMP_USER=snmp_user
SNMP_AUTH_PASS=authpass123
SNMP_PRIV_PASS=privpass123
SNMP_PORT=161
TRAP_PORT=162
# Descubrimiento
RED_ADMIN=148.204.56
SEED_ROUTER_IP=148.204.56.1
# Pérdida de paquetes R1-R2
PACKET_LOSS_THRESHOLD=25
PACKET_LOSS_INTERVAL=30
PACKET_LOSS_COUNT=10
```

### `requirements.txt` (backend)

| Librería | Uso |
|----------|-----|
| `Flask`, `Flask-Cors` | Servidor REST + CORS para el frontend. |
| `Flask-SQLAlchemy` | ORM sobre SQLite (modelos). |
| `python-dotenv` | Carga de `.env`. |
| `netmiko` | SSH + CDP para descubrimiento de topología. |
| `pysnmp==7.1.26` | SNMPv3 (GETs, walks y receptor de traps), async. |
| `ansible`, `ansible-runner` | Configuración de routers vía playbooks `cisco.ios`. |
| **`networkx`** | **Modelo y algoritmos del grafo de topología** (nodos/aristas, layout, conectividad). |
| **`plotly`** | **Construcción server-side de figuras**: grafo de topología y series de tiempo de métricas. |
| `pandas` | Manejo tabular de muestras de métricas (alimenta a Plotly, cálculo de máx/promedio). |

> **Plotly** y **networkx** son piezas centrales (no opcionales): networkx modela el
> grafo descubierto y Plotly genera todas las visualizaciones. El frontend solo
> renderiza con Plotly.js. Se descartan Chart.js y vis-network.

### Frontend (`package.json`)

| Librería | Uso |
|----------|-----|
| `astro` | Framework SSR. |
| `@astrojs/react`, `react`, `react-dom` | Componentes interactivos. |
| `@astrojs/tailwind`, `tailwindcss` | Estilos. |
| `plotly.js-dist-min` (o CDN) | Render en navegador de las figuras Plotly del backend. |
| `typescript` | Tipado de `lib/api.ts` y componentes. |

---

## 11. Topología GNS3 (referencia — sin seed en BD)

**No hay `seed.py`**: la BD arranca **vacía** y se puebla **dinámicamente** al usar
"Explorar la red" (descubrimiento CDP/SNMP). Esto es coherente con el examen, que
**altera la topología** (borra un dispositivo/interfaz) antes de la revisión.

Las exportaciones reales de GNS3 y los `startup-config` viven en `Infrastructure/`
(documentación/respaldo, no se leen en runtime). Topología en **cadena R1–R2–R3**
con enlaces inter-router de **subneteo /30** (punto a punto) de `8.8.8.0/24`:

| Router | LAN (api / ip) | Enlaces /30 (api / ip) | ip_admin (ej.) |
|--------|----------------|------------------------|----------------|
| R1 | f0_0 → 148.204.56.1/24 (SME) | f1_0 → 8.8.8.1 (R1-R2) | 148.204.56.1 |
| R2 | f0_0 → 148.204.59.1/24 (PC1) | f1_0 → 8.8.8.2 (R1-R2), f1_1 → 8.8.8.5 (R2-R3) | 8.8.8.5 |
| R3 | f0_0 → 148.204.60.1/24 (PC2) | f1_1 → 8.8.8.6 (R2-R3) | 8.8.8.6 |

Subredes /30: `8.8.8.0/30` (R1-R2), `8.8.8.4/30` (R2-R3). R1 y R3 NO están
conectados entre sí. La **SME** cuelga de la LAN de R1 (`148.204.56.10/24`, vía
Switch1); ver `Infrastructure/configs/EndDevices/SME/`. El convertidor de nombres
del backend debe soportar `f1_1` ↔ `FastEthernet1/1`.

> IPs reales se ajustan cuando se defina la topología final. La verdad la define el
> descubrimiento por CDP, no esta tabla. Con /30 P2P la SME alcanza a R2/R3 vía R1
> una vez activado el enrutamiento (el examen lo configura antes de explorar).

## 12. Config necesaria en cada router Cisco c7200

```
snmp-server group GRUPO_V3 v3 priv
snmp-server user snmp_user GRUPO_V3 v3 auth sha authpass123 priv des56 privpass123
snmp-server enable traps
snmp-server host <IP_MV_ALPINE> version 3 priv snmp_user
snmp-server location <ubicacion>
snmp-server contact <contacto>
cdp run
hostname R1
ip domain-name lab.local
crypto key generate rsa general-keys modulus 1024
username admin privilege 15 secret cisco123
enable secret enable123
line vty 0 4
 transport input ssh
 login local
! NOTA: SIN router rip / router ospf (la app los activa)
```

---

## 13. Plan de ejecución por fases

Cada fase termina con commit + push a la rama. Marcar `[x]` al completar.

### Fase 1 — Cimientos
- [ ] `SME/database/models.py` (4 modelos).
- [ ] `SME/app.py` (Flask, CORS, db.create_all sobre BD vacía, registro de blueprints, arranque de hilos).
- [ ] `SME/requirements.txt`, `SME/.env.example`, `.gitignore`.

### Fase 2 — Capa SNMPv3
- [ ] `SME/network_utils/PySnmpV3.py` (UsmUserData; get/walk sync+async).
- [ ] Prueba unitaria/manual del helper.

### Fase 3 — Features backend
- [ ] `PySnmpInfo.py` + `routes/routers.py` (info dispositivos, refresco SNMP).
- [ ] `PySnmpOctetos.py` + endpoints de métricas (6 contadores, hilos).
- [ ] `PySnmpTraps.py` + `routes/alertas.py` (IFACE_UP/DOWN, CONSOLE_ACCESS).
- [ ] `routes/topologia.py` (BFS CDP, adaptado de referencia; usar `secret=ROUTER_ENABLE`).
- [ ] `ansible_service.py` + 5 playbooks + `routes/enrutamiento.py` + `routes/cambios.py`.
- [ ] `ping_monitor.py` (PACKET_LOSS).

### Fase 4 — Frontend Astro
- [ ] Scaffold Astro + Tailwind + `astro.config.mjs` + `tailwind.config.mjs` + `.env`.
- [ ] `src/lib/api.ts`.
- [ ] Páginas: index, topologia (Plotly grafo), enrutamiento, routers (index + [hostname] con Plotly.js), alertas, cambios.

### Fase 5 — Integración y arranque
- [ ] `start.sh` (instala colección, .env, Flask + Astro).
- [ ] Checklist de demo (§14).

---

## 14. Checklist de demo (mapeado a la rúbrica)

- [ ] (0.5) Página inicio muestra las 5 opciones.
- [ ] (1) Configurar enrutamiento RIP/OSPF se aplica en todos los routers.
- [ ] (1) Explorar la red detecta y dibuja la topología (incluso alterada).
- [ ] (1) Info de dispositivos (hardware/SO/contacto/uptime) correcta.
- [ ] (1) Info de interfaces (estado/IP/máscara/vecino) correcta.
- [ ] (2) Gráficas de tráfico/unicast/no-unicast actualizando cada 20 s.
- [ ] (2) Alertas (iface up/down, consola, pérdida >25%) aparecen al dispararse.
- [ ] (0.5) Cambio de hostname/location/interfaz corroborable.

---

## 15. Riesgos y notas

1. **PDF contradice SNMP v2c vs v3.** Decisión: **SNMPv3**. Confirmar con el profesor; el helper se diseña aislado por si hubiera que añadir v2c.
2. **El examen altera la topología** → el descubrimiento por CDP debe ser robusto y dinámico; la BD arranca vacía (sin seed) y se puebla al explorar.
3. **Sin enrutamiento previo** en los configs de GNS3 (lo activa la app).
4. **Gráficas + alertas = ~40% de la nota** → prioridad máxima.
5. **Frontend es 100% nuevo** (la referencia lo tiene vacío).
6. **Migración SNMP v2c→v3** respecto a la referencia es trabajo real.
7. **IPs de topología provisionales** hasta definir la red final.
8. **MCP GitHub sin escritura**: se usa git directo (con token configurado) para push.

---

## 16. Arquitectura modular (separación de responsabilidades)

El backend se organiza en **capas** para que cada pieza sea independiente, testeable y
reemplazable sin tocar el resto:

```
 Frontend (Astro)  ──HTTP──▶  routes/ (controladores REST, "delgados")
                                   │  validan entrada, devuelven JSON
                                   ▼
                              services / network_utils / viz   (lógica)
                                   │  SNMP, SSH, Ansible, ping, grafos, gráficas
                                   ▼
                              database/ (models + sesión SQLAlchemy)
```

Principios:
- **`routes/` no contiene lógica de red**: solo orquesta llamadas a `network_utils/` y
  `viz/` y serializa la respuesta. Cada opción del examen = un blueprint propio.
- **`network_utils/` es infraestructura pura** (SNMP/SSH/Ansible/ping), sin saber de Flask
  más allá de recibir el `app` para el contexto de BD cuando un hilo necesita escribir.
- **`viz/` aísla Plotly + networkx**: recibe datos de la BD y devuelve figuras JSON; se
  puede probar sin levantar el servidor.
- **`PySnmpV3.py` centraliza credenciales y wrappers**: ningún otro módulo instancia
  `UsmUserData`; si cambia el modo SNMP, se cambia en un solo lugar.
- **Configuración por `.env`**: nada de credenciales/IPs hardcodeadas en el código.
- **Frontend desacoplado**: habla con el backend solo por `lib/api.ts`; cambiar la URL del
  API o un endpoint se hace en un único archivo.

## 17. Prácticas de Git (branches y commits)

**Ramas**
- `main`: estable, **nunca** se hace push directo.
- `claude/asr-extra-network-monitoring-tyc038`: **rama de integración** de este trabajo
  (la designada). Todos los pushes remotos van aquí.
- Para cada fase se usa una **rama local de feature** que luego se integra a la rama de
  integración, manteniendo el historial limpio:
  `feat/cimientos`, `feat/snmpv3`, `feat/routers-info`, `feat/metricas`,
  `feat/alertas-traps`, `feat/topologia`, `feat/ansible-config`, `feat/ping-monitor`,
  `feat/viz-plotly`, `feat/frontend`.
  > Nota: por política de la sesión solo se **pushea la rama de integración**; las ramas
  > de feature son locales salvo que se autorice publicarlas.

**Commits — [Conventional Commits](https://www.conventionalcommits.org/)**
- Formato: `tipo(scope): descripción breve en imperativo`.
- Tipos: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`.
- Ejemplos:
  - `feat(models): agrega Router, Interface, MetricaInterfaz y Alerta`
  - `feat(snmp): implementa helper SNMPv3 con UsmUserData (SHA+DES56)`
  - `feat(viz): grafo de topología con networkx y figura Plotly`
  - `fix(metricas): maneja wrap-around de Counter32 en ifInOctets`
- **Un cambio lógico por commit** (atómico), mensaje que explique el *porqué* cuando no
  sea obvio. Nada de commits gigantes "WIP".
- Cada fase del §13 termina con sus commits y un push a la rama de integración.
