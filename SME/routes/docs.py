"""Documentación automática de la API (sin dependencias externas).

Genera una página HTML en `/docs` introspeccionando el mapa de rutas de Flask
(`url_map`) y la primera línea del docstring de cada vista. También expone
`/docs/rutas` como JSON para consumo programático.
"""
from flask import Blueprint, current_app, Response, jsonify

docs_bp = Blueprint('docs', __name__)

_METODOS = {'GET', 'POST', 'PUT', 'DELETE', 'PATCH'}


def _recolectar_rutas():
    rutas = []
    for regla in current_app.url_map.iter_rules():
        if regla.endpoint in ('static', 'docs.docs_html', 'docs.docs_json'):
            continue
        metodos = sorted(m for m in regla.methods if m in _METODOS)
        vista = current_app.view_functions.get(regla.endpoint)
        doc = ''
        if vista and vista.__doc__:
            doc = vista.__doc__.strip().splitlines()[0]
        # Grupo = primer segmento de la ruta (o 'general')
        partes = str(regla).strip('/').split('/')
        grupo = partes[0] if partes and partes[0] else 'general'
        rutas.append({'grupo': grupo, 'metodos': metodos,
                      'ruta': str(regla), 'descripcion': doc})
    rutas.sort(key=lambda r: (r['grupo'], r['ruta']))
    return rutas


@docs_bp.route('/docs/rutas', methods=['GET'])
def docs_json():
    return jsonify(_recolectar_rutas()), 200


@docs_bp.route('/docs', methods=['GET'])
def docs_html():
    rutas = _recolectar_rutas()
    filas = []
    grupo_actual = None
    for r in rutas:
        if r['grupo'] != grupo_actual:
            grupo_actual = r['grupo']
            filas.append(f'<tr class="grupo"><td colspan="3">/{grupo_actual}</td></tr>')
        chips = ' '.join(
            f'<span class="m {m.lower()}">{m}</span>' for m in r['metodos']
        )
        filas.append(
            f'<tr><td>{chips}</td><td class="ruta">{r["ruta"]}</td>'
            f'<td>{r["descripcion"]}</td></tr>'
        )
    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>API — Monitoreo de Red ASR</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 900px;
         color: #1a1a2e; padding: 0 1rem; }}
  h1 {{ font-size: 1.4rem; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .92rem; }}
  td {{ padding: .5rem .6rem; border-bottom: 1px solid #eee; vertical-align: top; }}
  tr.grupo td {{ background: #f4f6fb; font-weight: 700; font-family: monospace; }}
  .ruta {{ font-family: monospace; }}
  .m {{ display: inline-block; padding: .1rem .45rem; border-radius: 4px;
        font-size: .72rem; font-weight: 700; color: #fff; }}
  .get {{ background: #2471a3; }} .post {{ background: #27ae60; }}
  .put {{ background: #e67e22; }} .delete {{ background: #c0392b; }}
  .patch {{ background: #8e44ad; }}
</style></head>
<body>
  <h1>API — Sistema de Monitoreo de Red ASR</h1>
  <p>Documentación autogenerada de los endpoints. JSON en
     <a href="/docs/rutas"><code>/docs/rutas</code></a>.</p>
  <table><tbody>
    {''.join(filas)}
  </tbody></table>
</body></html>"""
    return Response(html, mimetype='text/html')
