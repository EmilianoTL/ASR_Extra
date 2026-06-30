#!/bin/sh
# =====================================================================
#  setup_sme.sh  —  Provisión inicial de la SME (Alpine Linux)
# ---------------------------------------------------------------------
#  Hace, en orden:
#    1. Instala los archivos de red (interfaces, resolv.conf, sme-routes.sh).
#    2. Levanta la red (eth0 topología estática + eth1 Internet por DHCP).
#    3. Instala dependencias del sistema (git, python, ansible, ping, ssh).
#    4. Clona el repo de GitHub y prepara el entorno Python del backend.
#    5. Instala la colección cisco.ios para Ansible.
#
#  Ejecutar como root:   sh setup_sme.sh
#  Idempotente: se puede correr varias veces.
# =====================================================================
set -eu

# ---- CONFIG ---------------------------------------------------------
REPO_OWNER="${REPO_OWNER:-EmilianoTL}"
REPO_NAME="${REPO_NAME:-ASR_Extra}"
BRANCH="${BRANCH:-claude/asr-extra-network-monitoring-tyc038}"
CLONE_DIR="${CLONE_DIR:-/opt/asr/ASR_Extra}"
VENV_DIR="${VENV_DIR:-/opt/asr/venv}"
# Token de GitHub para repos privados (NO se versiona). Opcional:
#   export GITHUB_TOKEN=ghp_xxx   antes de correr, o déjalo vacío para repo público.
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
# ---------------------------------------------------------------------

HERE="$(cd "$(dirname "$0")" && pwd)"
log() { echo "[setup] $*"; }
[ "$(id -u)" = "0" ] || { echo "Ejecuta como root"; exit 1; }

# --- 1. Archivos de red ---------------------------------------------
log "Instalando configuración de red..."
install -m 0644 "$HERE/interfaces"  /etc/network/interfaces
install -m 0644 "$HERE/resolv.conf" /etc/resolv.conf
install -m 0755 "$HERE/sme-routes.sh" /usr/local/sbin/sme-routes.sh
# Evita que el cliente DHCP sobrescriba nuestro resolv.conf (1.1.1.1):
chattr +i /etc/resolv.conf 2>/dev/null || log "AVISO: chattr no disponible; el DHCP podría tocar resolv.conf"

# --- 2. Levantar la red ---------------------------------------------
log "Reiniciando red..."
rc-service networking restart || /etc/init.d/networking restart || true
/usr/local/sbin/sme-routes.sh up || true

# --- 3. Dependencias del sistema ------------------------------------
log "Instalando paquetes (apk)..."
apk update
apk add --no-cache \
    git python3 py3-pip py3-virtualenv \
    ansible openssh-client \
    iproute2 iputils \
    gcc musl-dev python3-dev libffi-dev openssl-dev   # build deps para algunas wheels

# --- 4. Clonar repo + entorno Python --------------------------------
log "Clonando repositorio..."
mkdir -p "$(dirname "$CLONE_DIR")"
if [ -n "$GITHUB_TOKEN" ]; then
    REMOTE="https://x-access-token:${GITHUB_TOKEN}@github.com/${REPO_OWNER}/${REPO_NAME}.git"
else
    REMOTE="https://github.com/${REPO_OWNER}/${REPO_NAME}.git"
fi
if [ -d "$CLONE_DIR/.git" ]; then
    log "Repo ya existe; haciendo pull..."
    git -C "$CLONE_DIR" fetch origin "$BRANCH"
    git -C "$CLONE_DIR" checkout "$BRANCH"
    git -C "$CLONE_DIR" pull origin "$BRANCH"
else
    git clone --branch "$BRANCH" "$REMOTE" "$CLONE_DIR"
fi

log "Preparando entorno Python..."
python3 -m venv "$VENV_DIR" 2>/dev/null || virtualenv "$VENV_DIR"
# shellcheck disable=SC1091
. "$VENV_DIR/bin/activate"
pip install --upgrade pip
if [ -f "$CLONE_DIR/SME/requirements.txt" ]; then
    pip install -r "$CLONE_DIR/SME/requirements.txt"
else
    log "AVISO: aún no existe SME/requirements.txt (se crea en la Fase 1)"
fi

# --- 5. Colección Ansible cisco.ios ---------------------------------
log "Instalando colección cisco.ios..."
ansible-galaxy collection install cisco.ios || true

log "Listo. Repo en $CLONE_DIR, venv en $VENV_DIR."
log "Verifica la red con: /usr/local/sbin/sme-routes.sh show"
