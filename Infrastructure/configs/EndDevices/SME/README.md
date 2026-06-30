# SME — Máquina virtual (Alpine Linux)

La SME aloja el backend Flask + frontend Astro y monitorea la red. Tiene **dos
interfaces** con propósitos separados:

| Interfaz | Propósito | Config |
|----------|-----------|--------|
| **eth0** | Red de **topología / gestión** (LAN de R1, vía Sw1) | IP **estática** `148.204.56.10/24`, **sin** gateway |
| **eth1** | **Internet** (NAT) para `apk update` y todo lo de la máquina | **DHCP**, da la **ruta por defecto** y el DNS |

### Topología con enlaces /30 (punto a punto)
Los enlaces entre routers usan **subneteo /30** de `8.8.8.0/24` (2 hosts por
enlace), así que **no hay un segmento compartido** entre los tres routers. La SME
cuelga de la **LAN de R1** (`148.204.56.0/24`) y su único salto hacia toda la
topología es **R1 (`148.204.56.1`)**. R1 alcanza a R2/R3 una vez que la app activa
RIP/OSPF (el examen configura el enrutamiento antes de explorar/monitorear).

### Regla de enrutamiento
- **Las redes de la topología salen por eth0** (vía R1); **todo lo demás por eth1**.
- La ruta por defecto (`0.0.0.0/0`) la pone el DHCP de eth1 → Internet.

```
Topología (eth0, vía R1 = 148.204.56.1):   Internet (eth1):
  148.204.56.0/24 -> directamente conectada    0.0.0.0/0  -> gateway DHCP (NAT)
  8.8.8.0/24      -> via 148.204.56.1 (R1)      DNS 1.1.1.1 sigue la ruta por defecto
  148.204.59.0/24 -> via 148.204.56.1 (R1)
  148.204.60.0/24 -> via 148.204.56.1 (R1)
```

### DNS = 1.1.1.1 (sin conflictos)
Se usa **1.1.1.1** (Cloudflare) como DNS. No cae dentro de `8.8.8.0/24` (la red de
topología que va por eth0), así que el tráfico DNS sale por la **ruta por defecto
(eth1/NAT)** sin necesidad de rutas especiales. Esto cubre `apk update`, github y
todo lo de la máquina.

> Evita 8.8.8.8 a propósito: ese DNS sí solaparía con `8.8.8.0/24` y obligaría a una
> ruta /32 de excepción. Con 1.1.1.1 no hace falta.

## Archivos
| Archivo | Destino en la SME | Qué hace |
|---------|-------------------|----------|
| `interfaces` | `/etc/network/interfaces` | Define eth0 (estática) y eth1 (DHCP) |
| `resolv.conf` | `/etc/resolv.conf` | Fija `nameserver 1.1.1.1` |
| `sme-routes.sh` | `/usr/local/sbin/sme-routes.sh` | Aplica rutas de topología (vía R1) |
| `setup_sme.sh` | (se ejecuta) | Provisión: red + paquetes + clona repo + venv + cisco.ios |
| `sync_github.sh` | (se ejecuta) | `git pull` de la rama y reinstala deps si cambian |

## Paso 0 — Puesta en línea provisional (antes de clonar)

Solo para tener Internet por eth1 (NAT) y poder clonar el repo. No persiste tras
reiniciar ni toca eth0/topología:

```sh
# como root
ip link set eth1 up
udhcpc -i eth1                       # IP por DHCP desde la NAT
echo "nameserver 1.1.1.1" > /etc/resolv.conf
ping -c 3 1.1.1.1 && ping -c 3 github.com
apk update && apk add git
git clone -b claude/asr-extra-network-monitoring-tyc038 \
  https://github.com/EmilianoTL/ASR_Extra.git
# repo privado: usa  https://x-access-token:TU_TOKEN@github.com/EmilianoTL/ASR_Extra.git
```

Luego entra a `ASR_Extra/Infrastructure/configs/EndDevices/SME/` y corre la
provisión completa (`setup_sme.sh`), que deja la red persistente.

## Uso

```sh
# 1) Provisión inicial (como root). Para repo privado, exporta el token antes:
#    export GITHUB_TOKEN=ghp_xxxxx
sh setup_sme.sh

# 2) Verificar rutas
/usr/local/sbin/sme-routes.sh show

# 3) Traer cambios más tarde
sh sync_github.sh
```

> **Ajusta las IPs** (core, LANs y gateways) en `sme-routes.sh` e `interfaces` si tu
> topología real difiere del esquema de ejemplo.
