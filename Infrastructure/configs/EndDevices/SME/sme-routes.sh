#!/bin/sh
# =====================================================================
#  sme-routes.sh  —  Política de rutas de la SME (Alpine)
# ---------------------------------------------------------------------
#  Objetivo:
#    * Las REDES DE LA TOPOLOGÍA salen por eth0 (hacia los routers, vía R1).
#    * TODO LO DEMÁS (Internet, apk update, github) sale por eth1 (NAT/DHCP).
#
#  DNS = 1.1.1.1 (no cae dentro de 8.8.8.0/24), así que el tráfico DNS sigue
#  la ruta por defecto (eth1) sin necesidad de excepciones.
#
#  Uso:  sme-routes.sh [up|down|show]
#  Instalar en: /usr/local/sbin/sme-routes.sh  (chmod +x)
#  Idempotente: usa 'ip route replace' / 'ip route del ... || true'.
# =====================================================================
set -u

# ---- CONFIG (ajusta a tu topología real) ----------------------------
IF_TOPO="${IF_TOPO:-eth0}"        # interfaz hacia los routers (LAN de R1)

# La SME cuelga de la LAN de R1 (148.204.56.0/24). Con enlaces /30 punto a
# punto entre routers NO hay segmento compartido, así que el único salto de
# la SME hacia toda la topología es R1. (R1 alcanza al resto una vez que la
# app activa RIP/OSPF.)
GW_TOPO="${GW_TOPO:-148.204.56.1}"   # R1, gateway de la SME en eth0

# Redes de la topología que deben ir por eth0 (todas vía R1).
# 148.204.56.0/24 es directamente conectada (no necesita ruta).
# Formato: "CIDR VIA_GATEWAY".
TOPO_ROUTES="
8.8.8.0/24 ${GW_TOPO}
148.204.59.0/24 ${GW_TOPO}
148.204.60.0/24 ${GW_TOPO}
"
# ---------------------------------------------------------------------

log() { echo "[sme-routes] $*"; }

aplicar_topo() {
    echo "$TOPO_ROUTES" | while read -r cidr gw; do
        [ -z "$cidr" ] && continue
        ip route replace "$cidr" via "$gw" dev "$IF_TOPO" && \
            log "topo  $cidr via $gw dev $IF_TOPO"
    done
}

quitar_topo() {
    echo "$TOPO_ROUTES" | while read -r cidr gw; do
        [ -z "$cidr" ] && continue
        ip route del "$cidr" via "$gw" dev "$IF_TOPO" 2>/dev/null || true
    done
}

case "${1:-up}" in
    up)    aplicar_topo ;;
    down)  quitar_topo ;;
    show)  ip route show ;;
    *)     echo "uso: $0 [up|down|show]"; exit 1 ;;
esac
