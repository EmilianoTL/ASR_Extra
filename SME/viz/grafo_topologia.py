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


def construir_figura(routers) -> dict:
    """Figura Plotly (dict) del grafo de topología."""
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
    return fig.to_plotly_json()
