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
  148.204.56.0/24 -> directamente conectada    0.0.0.0/0   -> gateway DHCP (NAT)
  8.8.8.0/24      -> via 148.204.56.1 (R1)      8.8.8.8/32  -> gateway DHCP (NAT)  <-- excepción DNS
  148.204.59.0/24 -> via 148.204.56.1 (R1)
  148.204.60.0/24 -> via 148.204.56.1 (R1)
```

### ⚠️ Conflicto DNS 8.8.8.8 vs red 8.8.8.0/24 (importante)
El DNS de Google **8.8.8.8 cae dentro de `8.8.8.0/24`**, que va por eth0 (topología).
Sin tratamiento, las consultas a 8.8.8.8 saldrían hacia el lab y NO a Internet. Por
eso `sme-routes.sh` añade una ruta **`8.8.8.8/32` por eth1** (más específica → gana),
de modo que el DNS sí resuelve por la NAT.

> Si prefieres evitar el conflicto por completo, usa otro DNS público (p. ej.
> `1.1.1.1`) en `resolv.conf` y la excepción /32 deja de ser necesaria. Se dejó
> 8.8.8.8 porque así lo pediste.

## Archivos
| Archivo | Destino en la SME | Qué hace |
|---------|-------------------|----------|
| `interfaces` | `/etc/network/interfaces` | Define eth0 (estática) y eth1 (DHCP) |
| `resolv.conf` | `/etc/resolv.conf` | Fija `nameserver 8.8.8.8` |
| `sme-routes.sh` | `/usr/local/sbin/sme-routes.sh` | Aplica rutas de topología + excepción DNS |
| `setup_sme.sh` | (se ejecuta) | Provisión: red + paquetes + clona repo + venv + cisco.ios |
| `sync_github.sh` | (se ejecuta) | `git pull` de la rama y reinstala deps si cambian |

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
