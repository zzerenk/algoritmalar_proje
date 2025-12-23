"""OpenStreetMap data access and proximity helpers."""

from __future__ import annotations

from typing import Any, Tuple, List
from math import radians, sin, cos, asin, sqrt
import random

try:
    import osmnx as ox
except ImportError:  # pragma: no cover - optional dependency
    ox = None  # type: ignore


def load_graph(place_name: str) -> Any:
    """Fetch raw (unprojected) graph data; enrich speeds when possible."""

    if ox is None:
        raise ImportError("osmnx is required for load_graph")

    graph = ox.graph_from_place(place_name, network_type="all", simplify=False)
    try:
        # Make the network undirected to ignore one-way restrictions for emergency routing.
        graph = ox.utils_graph.get_undirected(graph)
    except Exception:
        # Fallback silently to keep loading even if conversion fails.
        pass
    try:
        graph = ox.add_edge_speeds(graph)
        graph = ox.add_edge_travel_times(graph)
    except Exception:
        pass
    return graph


def load_buildings(place_name: str):
    """Fetch building geometries for a place (GeoDataFrame).

    Uses OSMnx features_from_place with building tag. Returns empty GeoDataFrame
    on failure or if no data is found to avoid crashing the UI.
    """

    if ox is None:
        raise ImportError("osmnx is required for load_buildings")

    try:
        gdf = ox.features_from_place(place_name, tags={"building": True})
        if gdf is None or gdf.empty:
            return gdf
        return gdf
    except Exception:
        # Return empty GeoDataFrame on any failure
        try:
            import geopandas as gpd  # type: ignore

            return gpd.GeoDataFrame()
        except Exception:
            return None


def get_nearest_node(graph: Any, lat: float, lon: float, max_distance_m: float = 100.0) -> Any:
    """Nearest node with optional distance guard."""

    if ox is None:
        raise ImportError("osmnx is required for get_nearest_node")

    try:
        node_id = ox.distance.nearest_nodes(graph, lon, lat)
    except Exception:
        node_id = _nearest_node_haversine(graph, lat, lon)

    if node_id is None:
        return None

    node_data = graph.nodes[node_id]
    nlat = node_data.get("y")
    nlon = node_data.get("x")
    if nlat is None or nlon is None:
        return None

    distance_m = _haversine(lat, lon, nlat, nlon)
    if max_distance_m is not None and distance_m > max_distance_m:
        raise ValueError("Konum yola çok uzak")
    return node_id


def get_nearest_edge_point(graph: Any, lat: float, lon: float):
    """Return nearest road point on an edge and the closer endpoint node id."""

    if ox is None:
        raise ImportError("osmnx is required for get_nearest_edge_point")

    try:
        u, v, key = ox.nearest_edges(graph, lon, lat)
    except Exception as exc:
        raise ValueError(f"En yakın yol bulunamadı: {exc}") from exc

    edge_data = graph.get_edge_data(u, v, key)
    if edge_data is None:
        raise ValueError("Edge verisi bulunamadı")

    geom = edge_data.get("geometry")
    if geom is None:
        from shapely.geometry import LineString

        try:
            geom = LineString(
                [
                    (graph.nodes[u]["x"], graph.nodes[u]["y"]),
                    (graph.nodes[v]["x"], graph.nodes[v]["y"]),
                ]
            )
        except Exception as exc:
            raise ValueError(f"Edge geometrisi oluşturulamadı: {exc}") from exc

    try:
        from shapely.geometry import Point
        from shapely.ops import nearest_points
    except Exception as exc:
        raise ImportError("shapely is required for get_nearest_edge_point") from exc

    click_point = Point(lon, lat)
    nearest_on_edge = nearest_points(click_point, geom)[1]
    proj_lon, proj_lat = nearest_on_edge.x, nearest_on_edge.y

    du = _haversine(proj_lat, proj_lon, graph.nodes[u]["y"], graph.nodes[u]["x"])
    dv = _haversine(proj_lat, proj_lon, graph.nodes[v]["y"], graph.nodes[v]["x"])
    target_node = u if du <= dv else v

    return proj_lat, proj_lon, target_node


def block_area(graph: Any, lat: float, lon: float, radius_m: float = 50.0):
    """Mark edges within radius as blocked; return list of blocked (u, v, key)."""

    blocked_edges = []
    try:
        from shapely.geometry import Point
        from shapely.ops import nearest_points

        click_pt = Point(lon, lat)
    except Exception:
        click_pt = None
        nearest_points = None  # type: ignore

    edges = list(graph.edges(keys=True, data=True))
    for u, v, key, data in edges:
        dist = float("inf")
        if click_pt is not None:
            geom = data.get("geometry")
            if geom is not None and nearest_points is not None:
                try:
                    nearest_on = nearest_points(click_pt, geom)[1]
                    dist = _haversine(lat, lon, nearest_on.y, nearest_on.x)
                except Exception:
                    dist = float("inf")
        if dist == float("inf"):
            try:
                n1 = graph.nodes[u]
                n2 = graph.nodes[v]
                d1 = _haversine(lat, lon, n1.get("y"), n1.get("x"))
                d2 = _haversine(lat, lon, n2.get("y"), n2.get("x"))
                dist = min(d1, d2)
            except Exception:
                dist = float("inf")
        if dist <= radius_m:
            edge_data = graph.get_edge_data(u, v, key)
            if edge_data is None:
                continue
            if "orig_length" not in edge_data and "length" in edge_data:
                edge_data["orig_length"] = edge_data.get("length")
            edge_data["blocked"] = True
            blocked_edges.append((u, v, key))
    return blocked_edges


def reset_graph_weights(graph: Any) -> None:
    """Clear blocked flags and restore original lengths when available."""

    if graph is None:
        return
    for u, v, key, data in graph.edges(keys=True, data=True):
        if data.get("blocked"):
            data.pop("blocked", None)
        if "orig_length" in data:
            data["length"] = data.get("orig_length")


def simulate_scattered_damage(graph: Any, count: int = 10):
    """Scatter small debris pockets (15-20m radius) directly on road geometry."""

    if graph is None or len(graph.edges) == 0:
        return []

    all_edges = list(graph.edges(data=True))
    if not all_edges:
        return []

    pick_count = min(count, len(all_edges))
    chosen = random.sample(all_edges, pick_count)

    results: List[tuple] = []
    for u, v, data in chosen:
        lat = None
        lon = None
        geom = data.get("geometry") if isinstance(data, dict) else None
        if geom is not None:
            try:
                mid_pt = geom.interpolate(0.5, normalized=True)
                lon = mid_pt.x
                lat = mid_pt.y
            except Exception:
                lat = None
                lon = None
        if lat is None or lon is None:
            try:
                lat = (graph.nodes[u]["y"] + graph.nodes[v]["y"]) / 2
                lon = (graph.nodes[u]["x"] + graph.nodes[v]["x"]) / 2
            except Exception:
                continue
        radius = random.uniform(15.0, 20.0)
        blocked = block_area(graph, lat, lon, radius)
        results.append((lat, lon, radius, blocked))
    return results


def _nearest_node_haversine(graph: Any, lat: float, lon: float) -> Any:
    """Naive nearest neighbor using haversine distance over all nodes."""

    best_node = None
    best_dist = float("inf")
    for node_id, data in graph.nodes(data=True):
        nlat = data.get("y")
        nlon = data.get("x")
        if nlat is None or nlon is None:
            continue
        d = _haversine(lat, lon, nlat, nlon)
        if d < best_dist:
            best_dist = d
            best_node = node_id
    return best_node


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return R * c


# Backward compatibility for existing callers.
def get_graph(place_name: str) -> Any:
    return load_graph(place_name)
