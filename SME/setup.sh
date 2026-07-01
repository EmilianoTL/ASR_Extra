#!/bin/sh
# =====================================================================
#  SME/setup.sh  —  Provisión de la máquina SME (Alpine Linux)
# ---------------------------------------------------------------------
#  Hace, en este orden:
#    1. Configura la RED:
#         eth0 -> IP local estática hacia la TOPOLOGÍA (sin DNS, sin gateway)
#         eth1 -> DHCP hacia la NAT (Internet), con DNS 1.1.1.1
#       Regla: la topología sale por eth0; Internet/paquetes/github por eth1.
#    2. Instala DEPENDENCIAS del sistema (ssh, python, nano, ansible, ...).
#    3. Crea el entorno Python e instala requirements.txt.
#    4. Instala la colección Ansible cisco.ios.
#
#  Ejecutar como root desde la carpeta SME:   sh setup.sh
#  Es idempotente: se puede correr varias veces.
# =====================================================================
set -eu

# ---- CONFIG (ajusta a tu topología real) ----------------------------
IF_TOPO="${IF_TOPO:-eth0}"          # interfaz hacia los routers (LAN de R1)
IF_NAT="${IF_NAT:-eth1}"            # interfaz hacia Internet (NAT/DHCP)

ETH0_IP="${ETH0_IP:-148.204.56.10}" # IP local de la SME en la LAN de R1
ETH0_MASK="${ETH0_MASK:-255.255.255.0}"
GW_TOPO="${GW_TOPO:-148.204.56.1}"  # R1: único salto hacia toda la topología

# Redes de la topología alcanzables vía R1 (148.204.56.0/24 es directa).
TOPO_NETS="${TOPO_NETS:-8.8.8.0/24 148.204.59.0/24 148.204.60.0/24}"

DNS_NAT="${DNS_NAT:-1.1.1.1}"       # DNS que usa eth1 (Internet)
# ---------------------------------------------------------------------

HERE="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${VENV_DIR:-$HERE/.venv}"
log() { echo ""; echo ">>> $*"; }

[ "$(id -u)" = "0" ] || { echo "Ejecuta como root: sh setup.sh"; exit 1; }

# =====================================================================
# 1. RED
# =====================================================================
log "[1/4] Configurando red (eth0 topología, eth1 NAT)"

# Rutas de topología (post-up/pre-down de eth0), generadas desde TOPO_NETS.
_rutas=""
for net in $TOPO_NETS; do
    _rutas="${_rutas}    post-up   ip route add ${net} via ${GW_TOPO} dev ${IF_TOPO} || true\n"
done
for net in $TOPO_NETS; do
    _rutas="${_rutas}    pre-down  ip route del ${net} via ${GW_TOPO} dev ${IF_TOPO} 2>/dev/null || true\n"
done

{
    echo "# Generado por SME/setup.sh"
    echo "# eth0: TOPOLOGÍA (estática, sin gateway ni DNS). eth1: NAT/Internet (DHCP)."
    echo "auto lo"
    echo "iface lo inet loopback"
    echo ""
    echo "auto ${IF_TOPO}"
    echo "iface ${IF_TOPO} inet static"
    echo "    address ${ETH0_IP}"
    echo "    netmask ${ETH0_MASK}"
    printf "%b" "$_rutas"
    echo "auto ${IF_NAT}"
    echo "iface ${IF_NAT} inet dhcp"
} > /etc/network/interfaces

# DNS: solo eth1 (Internet). eth0 no aporta DNS.
# Quita el bit inmutable por si una corrida previa lo dejó (hace el script reejecutable).
chattr -i /etc/resolv.conf 2>/dev/null || true
echo "nameserver ${DNS_NAT}" > /etc/resolv.conf
# Evita que el cliente DHCP de eth1 sobrescriba el DNS que queremos usar.
chattr +i /etc/resolv.conf 2>/dev/null || \
    log "AVISO: chattr no disponible; el DHCP podría cambiar /etc/resolv.conf"

# Levanta la red y deja el servicio en el arranque.
rc-update add networking boot 2>/dev/null || true
rc-service networking restart || /etc/init.d/networking restart || true

echo "Rutas actuales:"; ip route show || true

# =====================================================================
# 2. DEPENDENCIAS DEL SISTEMA
# =====================================================================
log "[2/4] Instalando dependencias del sistema (apk)"
apk update || log "AVISO: 'apk update' falló (¿sin Internet?); intento continuar"

# Instala cada paquete solo si falta; si uno falla, sigue con el siguiente.
# Lleva conteo de omitidos / instalados / fallidos y muestra un resumen.
_apk_ya=0
_apk_ok=0
_apk_fail=0
_apk_fallidos=""

instalar_apk() {
    for pkg in "$@"; do
        if apk info -e "$pkg" >/dev/null 2>&1; then
            echo "  [ya]  $pkg (ya instalado, sigo con el siguiente)"
            _apk_ya=$((_apk_ya + 1))
        elif apk add --no-cache "$pkg" >/dev/null 2>&1; then
            echo "  [ok]  $pkg (instalado)"
            _apk_ok=$((_apk_ok + 1))
        else
            echo "  [!!]  $pkg (no se pudo instalar, continuo)"
            _apk_fail=$((_apk_fail + 1))
            _apk_fallidos="${_apk_fallidos} ${pkg}"
        fi
    done
}

instalar_apk \
    openssh-client \
    python3 py3-pip py3-virtualenv \
    nano \
    ansible \
    git \
    iproute2 iputils \
    ca-certificates \
    gcc musl-dev python3-dev libffi-dev openssl-dev linux-headers make

echo ""
echo "  Resumen apk -> ya instalados: ${_apk_ya} | nuevos: ${_apk_ok} | fallidos: ${_apk_fail}"
[ -n "$_apk_fallidos" ] && echo "  Paquetes que fallaron:${_apk_fallidos}"

# =====================================================================
# 3. ENTORNO PYTHON + REQUIREMENTS
# =====================================================================
log "[3/4] Entorno Python e instalación de requirements"
if [ -d "$VENV_DIR" ] && [ -x "$VENV_DIR/bin/python" ]; then
    echo "  [ya]  entorno virtual en $VENV_DIR"
else
    python3 -m venv "$VENV_DIR" 2>/dev/null || virtualenv "$VENV_DIR"
    echo "  [ok]  entorno virtual creado en $VENV_DIR"
fi
# shellcheck disable=SC1091
. "$VENV_DIR/bin/activate"
pip install --upgrade pip >/dev/null 2>&1 || true

# Intenta todo el requirements de una; si falla, instala línea por línea
# (así un paquete problemático no impide instalar los demás).
if pip install -r "$HERE/requirements.txt"; then
    echo "  [ok]  requirements.txt instalado"
else
    log "AVISO: falló la instalación en bloque; reintento paquete por paquete"
    while IFS= read -r linea; do
        # ignora comentarios y líneas vacías
        paquete="$(printf '%s' "$linea" | sed 's/#.*//' | tr -d '[:space:]')"
        [ -z "$paquete" ] && continue
        if pip install "$paquete" >/dev/null 2>&1; then
            echo "  [ok]  $paquete"
        else
            echo "  [!!]  no se pudo instalar $paquete — continuo"
        fi
    done < "$HERE/requirements.txt"
fi

# =====================================================================
# 4. COLECCIÓN ANSIBLE
# =====================================================================
log "[4/4] Instalando colección Ansible cisco.ios"
if ansible-galaxy collection list cisco.ios >/dev/null 2>&1; then
    echo "  [ya]  colección cisco.ios"
else
    ansible-galaxy collection install cisco.ios \
        && echo "  [ok]  colección cisco.ios" \
        || echo "  [!!]  no se pudo instalar cisco.ios — continuo"
fi

log "Listo."
echo "  - Red: eth0=${ETH0_IP} (topología), eth1=DHCP (NAT, DNS ${DNS_NAT})"
echo "  - Entorno Python: ${VENV_DIR}"
echo "  - Para arrancar el backend:"
echo "      . ${VENV_DIR}/bin/activate && python ${HERE}/app.py"
