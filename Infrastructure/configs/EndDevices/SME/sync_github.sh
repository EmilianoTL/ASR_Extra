#!/bin/sh
# =====================================================================
#  sync_github.sh  —  Trae los últimos cambios del repo en la SME
# ---------------------------------------------------------------------
#  Hace un pull de la rama de trabajo y reinstala dependencias si el
#  requirements.txt cambió. Pensado para correr en la SME tras un push.
#
#  Uso:   sh sync_github.sh
#  Token privado opcional: export GITHUB_TOKEN=ghp_xxx
# =====================================================================
set -eu

CLONE_DIR="${CLONE_DIR:-/opt/asr/ASR_Extra}"
VENV_DIR="${VENV_DIR:-/opt/asr/venv}"
BRANCH="${BRANCH:-claude/asr-extra-network-monitoring-tyc038}"

log() { echo "[sync] $*"; }
[ -d "$CLONE_DIR/.git" ] || { echo "No existe el repo en $CLONE_DIR. Corre setup_sme.sh primero."; exit 1; }

# Guardamos el hash del requirements antes del pull
REQ="$CLONE_DIR/SME/requirements.txt"
before=""; [ -f "$REQ" ] && before="$(md5sum "$REQ" | awk '{print $1}')"

log "Actualizando $BRANCH..."
git -C "$CLONE_DIR" fetch origin "$BRANCH"
git -C "$CLONE_DIR" checkout "$BRANCH"
git -C "$CLONE_DIR" pull origin "$BRANCH"

# Si cambió requirements.txt, reinstala dependencias
after=""; [ -f "$REQ" ] && after="$(md5sum "$REQ" | awk '{print $1}')"
if [ "$before" != "$after" ] && [ -f "$REQ" ]; then
    log "requirements.txt cambió; reinstalando dependencias..."
    # shellcheck disable=SC1091
    . "$VENV_DIR/bin/activate"
    pip install -r "$REQ"
fi

log "Sincronización completa. Commit actual:"
git -C "$CLONE_DIR" --no-pager log --oneline -1
