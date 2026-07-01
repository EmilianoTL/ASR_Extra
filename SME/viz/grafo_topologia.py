"""Grafo de topología con networkx, exportado como figura Plotly (JSON).

`construir_figura(routers)` arma un grafo no dirigido (nodos = routers, aristas =
adyacencias descubiertas por CDP), calcula un layout con networkx y devuelve la
figura Plotly serializada (dict) para que el frontend la renderice con Plotly.js.

`construir_enlaces(routers)` devuelve la lista de enlaces (para clientes que
prefieran dibujar el grafo por su cuenta).
"""
import networkx as nx
import plotly.graph_objects as go


def _grafo(routers):
    """Construye el grafo networkx a partir de los routers y sus adyacencias."""
    por_id = {r.id: r for r in routers}
    g = nx.Graph()
    for r in routers:
        g.add_node(r.hostname, ip=r.ip_admin)
    for r in routers:
        for iface in r.interfaces:
            vecino = por_id.get(iface.conectado_a_router_id)
            if vecino is not None:
                g.add_edge(r.hostname, vecino.hostname)
    return g


def construir_enlaces(routers) -> list[dict]:
    """Lista de enlaces únicos [{source, target}] desde las adyacencias."""
    g = _grafo(routers)
    return [{'source': a, 'target': b} for a, b in g.edges()]


def construir_resumen(routers) -> list[dict]:
    """Resumen simple: cada router y con quién está conectado."""
    por_id = {r.id: r for r in routers}
    resumen = []
    for r in routers:
        vecinos = []
        for iface in r.interfaces:
            v = por_id.get(iface.conectado_a_router_id)
            if v is not None and v.hostname not in vecinos:
                vecinos.append(v.hostname)
        resumen.append({'router': r.hostname, 'ip_admin': r.ip_admin,
                        'conectado_a': sorted(vecinos)})
    return resumen


def _figura_obj(routers):
    """Construye el objeto go.Figure del grafo (reutilizable)."""
    g = _grafo(routers)
    pos = nx.spring_layout(g, seed=42) if g.number_of_nodes() else {}

    # Aristas.
    ex, ey = [], []
    for a, b in g.edges():
        ex += [pos[a][0], pos[b][0], None]
        ey += [pos[a][1], pos[b][1], None]
    traza_aristas = go.Scatter(
        x=ex, y=ey, mode='lines',
        line=dict(width=2, color='#888'), hoverinfo='none',
    )

    # Nodos.
    nx_, ny, textos = [], [], []
    for nodo in g.nodes():
        nx_.append(pos[nodo][0])
        ny.append(pos[nodo][1])
        textos.append(f"{nodo}<br>{g.nodes[nodo].get('ip', '')}")
    traza_nodos = go.Scatter(
        x=nx_, y=ny, mode='markers+text',
        text=list(g.nodes()), textposition='top center',
        hovertext=textos, hoverinfo='text',
        marker=dict(size=28, color='#2471a3', line=dict(width=2, color='#fff')),
    )

    fig = go.Figure(data=[traza_aristas, traza_nodos])
    fig.update_layout(
        title='Topología de red',
        showlegend=False,
        margin=dict(l=20, r=20, t=40, b=20),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    )
    return fig


def construir_figura(routers) -> dict:
    """Figura Plotly (dict) del grafo, para renderizar con Plotly.js."""
    return _figura_obj(routers).to_plotly_json()


def construir_html(routers, fragmento: bool = False) -> str:
    """HTML de la figura Plotly. `fragmento=True` devuelve solo un <div>."""
    fig = _figura_obj(routers)
    return fig.to_html(full_html=not fragmento, include_plotlyjs='cdn')


def construir_svg(routers, ancho: int = 640, alto: int = 420) -> str:
    """Imagen SVG estática del grafo (sin dependencias de exportación)."""
    g = _grafo(routers)
    if g.number_of_nodes() == 0:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" '
                f'height="{alto}"><text x="20" y="30" font-family="sans-serif">'
                f'Sin routers en la base de datos</text></svg>')

    pos = nx.spring_layout(g, seed=42)
    margen = 55
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    def esc_x(x):
        return margen + (x - min_x) / ((max_x - min_x) or 1) * (ancho - 2 * margen)

    def esc_y(y):
        return margen + (y - min_y) / ((max_y - min_y) or 1) * (alto - 2 * margen)

    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" '
        f'viewBox="0 0 {ancho} {alto}" font-family="sans-serif">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]
    for a, b in g.edges():
        partes.append(
            f'<line x1="{esc_x(pos[a][0]):.1f}" y1="{esc_y(pos[a][1]):.1f}" '
            f'x2="{esc_x(pos[b][0]):.1f}" y2="{esc_y(pos[b][1]):.1f}" '
            f'stroke="#8899aa" stroke-width="2"/>'
        )
    for nodo in g.nodes():
        cx, cy = esc_x(pos[nodo][0]), esc_y(pos[nodo][1])
        ip = g.nodes[nodo].get('ip', '')
        partes.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="24" fill="#2471a3" '
            f'stroke="#ffffff" stroke-width="2"/>'
            f'<text x="{cx:.1f}" y="{cy:.1f}" font-size="13" fill="#ffffff" '
            f'text-anchor="middle" dominant-baseline="middle">{nodo}</text>'
            f'<text x="{cx:.1f}" y="{cy + 38:.1f}" font-size="10" fill="#555" '
            f'text-anchor="middle">{ip}</text>'
        )
    partes.append('</svg>')
    return ''.join(partes)
