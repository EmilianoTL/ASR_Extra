#!/bin/sh
# =====================================================================
#  probar_endpoints.sh  —  Recorre los endpoints del backend con curl
# ---------------------------------------------------------------------
#  Uso:
#     sh pruebas/probar_endpoints.sh                 # solo lecturas (seguro)
#     HOST=R1 IFACE=f0_0 sh pruebas/probar_endpoints.sh
#     ESCRIBIR=1 sh pruebas/probar_endpoints.sh      # incluye POST/PUT que
#                                                    # ACTÚAN sobre los routers
#
#  Variables:
#     BASE     URL del backend (def. http://127.0.0.1:5000)
#     HOST     hostname de router a probar (def. R1)
#     IFACE    interfaz a probar (def. f0_0)
#     TIEMPO   intervalo de métricas en seg (def. 20)
#     ESCRIBIR =1 habilita las operaciones que reconfiguran routers (Ansible)
# =====================================================================
BASE="${BASE:-http://127.0.0.1:5000}"
HOST="${HOST:-R1}"
IFACE="${IFACE:-f0_0}"
TIEMPO="${TIEMPO:-20}"
ESCRIBIR="${ESCRIBIR:-0}"

# Formatea el cuerpo JSON (recibido como argumento) o lo imprime crudo si no es JSON.
_fmt() { printf '%s\n' "$1" | python3 -m json.tool 2>/dev/null || printf '%s\n' "$1"; }

req() {
    metodo="$1"; ruta="$2"; shift 2
    echo ""
    echo "===================================================================="
    echo ">> $metodo $ruta"
    echo "--------------------------------------------------------------------"
    # Respuesta = cuerpo + última línea con el código HTTP.
    resp="$(curl -s -w '\n%{http_code}' -X "$metodo" "$@" "${BASE}${ruta}")"
    code="$(printf '%s\n' "$resp" | tail -n1)"
    body="$(printf '%s\n' "$resp" | sed '$d')"
    echo "[HTTP $code]"
    _fmt "$body"
}

echo "Backend: $BASE | HOST=$HOST IFACE=$IFACE TIEMPO=$TIEMPO ESCRIBIR=$ESCRIBIR"

# ---------------------------------------------------------------------
echo ""; echo "########## 1. Estado del servicio ##########"
req GET /
req GET /health

echo ""; echo "########## 2. Routers (lecturas) ##########"
req GET /routers/
req GET "/routers/${HOST}/"
req GET "/routers/${HOST}/interfaces"

echo ""; echo "########## 3. Métricas ##########"
req GET "/routers/${HOST}/interfaces/${IFACE}/metricas/${TIEMPO}"
if [ "$ESCRIBIR" = "1" ]; then
    req POST "/routers/${HOST}/interfaces/${IFACE}/metricas/${TIEMPO}"
    echo "   (esperando ~$((TIEMPO + 5))s para que el hilo tome muestras...)"
    sleep "$((TIEMPO + 5))"
    req GET "/routers/${HOST}/interfaces/${IFACE}/metricas/${TIEMPO}"
    req DELETE "/routers/${HOST}/interfaces/${IFACE}/metricas/${TIEMPO}"
else
    echo "   (POST/DELETE de monitoreo omitidos; usa ESCRIBIR=1 para lanzarlos)"
fi

echo ""; echo "########## 4. Alertas ##########"
req GET /alertas/
req GET "/alertas/?tipo=IFACE_DOWN"
req GET "/alertas/?router=${HOST}&limit=5"

echo ""; echo "########## 5. Enrutamiento ##########"
req GET /enrutamiento/
if [ "$ESCRIBIR" = "1" ]; then
    req POST /enrutamiento/ -H 'Content-Type: application/json' -d '{"protocolo":"ospf"}'
else
    echo "   (POST /enrutamiento/ omitido; RECONFIGURA todos los routers. ESCRIBIR=1)"
fi

echo ""; echo "########## 6. Cambio de datos ##########"
if [ "$ESCRIBIR" = "1" ]; then
    req PUT "/cambios/${HOST}/location" -H 'Content-Type: application/json' -d '{"location":"Prueba-ASR"}'
    req PUT "/cambios/${HOST}/interfaces/${IFACE}" -H 'Content-Type: application/json' -d '{"accion":"up"}'
else
    echo "   (PUT /cambios/... omitidos; RECONFIGURAN el router. ESCRIBIR=1)"
    echo "   Validación segura (payload inválido -> 400 esperado):"
    req PUT "/cambios/${HOST}/interfaces/${IFACE}" -H 'Content-Type: application/json' -d '{"accion":"xxx"}'
fi

echo ""; echo "Listo."
