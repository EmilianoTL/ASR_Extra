# SME — Máquina virtual (Alpine Linux)

La SME aloja el backend Flask + frontend Astro y monitorea la red. Tiene **dos
interfaces** con propósitos separados:

| Interfaz | Propósito | Config |
|----------|-----------|--------|
| **eth0** | Red de **topología / gestión** (hacia los routers, vía Sw1) | IP **estática** `8.8.8.100/24`, **sin** gateway |
| **eth1** | **Internet** (NAT) para `apk update` y todo lo de la máquina | **DHCP**, da la **ruta por defecto** y el DNS |

### Regla de enrutamiento
- **Las redes de la topología salen por eth0**; **todo lo demás por eth1**.
- La ruta por defecto (`0.0.0.0/0`) la pone el DHCP de eth1 → Internet.
- Rutas específicas hacia las LAN detrás de cada router van por eth0 (vía la IP de
  cada router en el core). Las aplica `sme-routes.sh`.

```
Topología (eth0):                         Internet (eth1):
  8.8.8.0/24      -> directamente conectada   0.0.0.0/0   -> gateway DHCP (NAT)
  148.204.56.0/24 -> via 8.8.8.1 (R1)         8.8.8.8/32  -> gateway DHCP (NAT)  <-- excepción DNS
  148.204.59.0/24 -> via 8.8.8.5 (R2)
  148.204.60.0/24 -> via 8.8.8.9 (R3)
```

### ⚠️ Conflicto DNS 8.8.8.8 vs red 8.8.8.0/24 (importante)
El DNS de Google **8.8.8.8 cae dentro de `8.8.8.0/24`**, que es la red del core
(eth0). Sin tratamiento, las consultas a 8.8.8.8 saldrían hacia el lab y NO a
Internet. Por eso `sme-routes.sh` añade una ruta **`8.8.8.8/32` por eth1** (más
específica → gana), de modo que el DNS sí resuelve por la NAT.

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
