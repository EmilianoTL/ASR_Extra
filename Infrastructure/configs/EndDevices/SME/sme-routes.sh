#!/bin/sh
# =====================================================================
#  sme-routes.sh  —  Política de rutas de la SME (Alpine)
# ---------------------------------------------------------------------
#  Objetivo:
#    * Las REDES DE LA TOPOLOGÍA salen por eth0 (hacia los routers).
#    * TODO LO DEMÁS (Internet, apk update) sale por eth1 (NAT/DHCP).
#    * El DNS 8.8.8.8 cae dentro de 8.8.8.0/24 (que va por eth0); por eso
#      se fuerza una ruta /32 más específica de 8.8.8.8 por eth1, para que
#      la resolución DNS/Internet sí salga por la NAT y no hacia el lab.
#
#  Uso:  sme-routes.sh [up|down|dns|show]
#  Instalar en: /usr/local/sbin/sme-routes.sh  (chmod +x)
#  Idempotente: usa 'ip route replace' / 'ip route del ... || true'.
# =====================================================================
set -u

# ---- CONFIG (ajusta a tu topología real) ----------------------------
IF_TOPO="${IF_TOPO:-eth0}"        # interfaz hacia los routers (LAN de R1)
IF_NAT="${IF_NAT:-eth1}"          # interfaz hacia Internet (NAT/DHCP)

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

# IP del DNS público que debe salir por Internet (no por el lab).
DNS_PUBLIC="${DNS_PUBLIC:-8.8.8.8}"
# ---------------------------------------------------------------------

log() { echo "[sme-routes] $*"; }

aplicar_topo() {
    # eth0 ya tiene 8.8.8.0/24 directamente conectada al asignar la IP.
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

aplicar_dns() {
    # Descubre el gateway por defecto que dio el DHCP en la interfaz NAT.
    gw=$(ip -4 route show default dev "$IF_NAT" 2>/dev/null | awk '{print $3; exit}')
    if [ -n "${gw:-}" ]; then
        ip route replace "${DNS_PUBLIC}/32" via "$gw" dev "$IF_NAT" && \
            log "dns   ${DNS_PUBLIC}/32 via $gw dev $IF_NAT (Internet)"
    else
        log "AVISO: aún no hay gateway por DHCP en $IF_NAT; reintenta tras el DHCP"
    fi
}

case "${1:-up}" in
    up)    aplicar_topo; aplicar_dns ;;
    down)  quitar_topo ;;
    dns)   aplicar_dns ;;
    show)  ip route show ;;
    *)     echo "uso: $0 [up|down|dns|show]"; exit 1 ;;
esac
