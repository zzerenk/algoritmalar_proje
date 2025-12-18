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
    """Fetch raw (unprojected) graph data for a place using OSMnx with speeds and travel times."""

    if ox is None:
        raise ImportError("osmnx is required for load_graph")

    graph = ox.graph_from_place(place_name, network_type="all", simplify=False)
    # Enrich edges with speed and travel time for completeness.
    try:
        graph = ox.add_edge_speeds(graph)
        graph = ox.add_edge_travel_times(graph)
    except Exception:
        # If enrichment fails, continue with base graph.
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
    """Return nearest graph node to provided coordinates with a distance threshold.

    If the nearest road node is farther than ``max_distance_m``, returns None or
    raises ValueError to signal invalid selection.
    Falls back to a pure-Python haversine scan if optional deps are missing.
    """

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
    if distance_m > max_distance_m:
        raise ValueError("Konum yola çok uzak")
    return node_id


def get_nearest_edge_point(graph: Any, lat: float, lon: float):
    """Return nearest road point on an edge and the closer endpoint node id.

    Returns (projected_lat, projected_lon, target_node_id) or raises on failure.
    """

    if ox is None:
        raise ImportError("osmnx is required for get_nearest_edge_point")

    try:
        # nearest_edges expects (X=lon, Y=lat)
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

    # Pick closer endpoint of the edge.
    du = _haversine(proj_lat, proj_lon, graph.nodes[u]["y"], graph.nodes[u]["x"])
    dv = _haversine(proj_lat, proj_lon, graph.nodes[v]["y"], graph.nodes[v]["x"])
    target_node = u if du <= dv else v

    return proj_lat, proj_lon, target_node


def block_area(graph: Any, lat: float, lon: float, radius_m: float = 50.0):
    """Mark edges within radius as blocked; return list of blocked (u, v, key)."""

    blocked_edges = set()
    try:
        from shapely.geometry import Point
        from shapely.ops import nearest_points

        click_pt = Point(lon, lat)
    except Exception:
        click_pt = None
        nearest_points = None  # type: ignore

    def mark_block(u, v):
        try:
            edge_dict = graph.get_edge_data(u, v)
        except Exception:
            edge_dict = None
        if not edge_dict:
            return
        for k, edata in edge_dict.items():
            if edata is None:
                continue
            if "orig_length" not in edata and "length" in edata:
                edata["orig_length"] = edata.get("length")
            edata["blocked"] = True
            edata["weight"] = float("inf")
            blocked_edges.add((u, v, k))

    edges = list(graph.edges(keys=True, data=True))
    for u, v, key, data in edges:
        dist = float("inf")
        geom = data.get("geometry") if isinstance(data, dict) else None
        if click_pt is not None and geom is not None and nearest_points is not None:
            try:
                nearest_on = nearest_points(click_pt, geom)[1]
                dist = _haversine(lat, lon, nearest_on.y, nearest_on.x)
            except Exception:
                dist = float("inf")
        if dist == float("inf"):
            try:
                n1 = graph.nodes[u]
                n2 = graph.nodes[v]
                mid_lat = (n1.get("y") + n2.get("y")) / 2
                mid_lon = (n1.get("x") + n2.get("x")) / 2
                dist = _haversine(lat, lon, mid_lat, mid_lon)
            except Exception:
                dist = float("inf")
        if dist <= radius_m:
            # Block both directions and all parallel edges between the pair.
            mark_block(u, v)
            mark_block(v, u)

    return list(blocked_edges)


def apply_damage_area(graph: Any, center_lat: float, center_lon: float, radius_m: float = 50.0):
    """Block all edges intersecting a damage circle centered at (lat, lon)."""

    if graph is None:
        return []

    blocked_edges = set()
    try:
        from shapely.geometry import Point
        from shapely.ops import nearest_points

        center_pt = Point(center_lon, center_lat)
    except Exception:
        center_pt = None
        nearest_points = None  # type: ignore

    def mark_block(u, v):
        try:
            edge_dict = graph.get_edge_data(u, v)
        except Exception:
            edge_dict = None
        if not edge_dict:
            return
        for k, edata in edge_dict.items():
            if edata is None:
                continue
            if "orig_length" not in edata and "length" in edata:
                edata["orig_length"] = edata.get("length")
            edata["blocked"] = True
            edata["weight"] = float("inf")
            blocked_edges.add((u, v, k))

    for u, v, key, data in list(graph.edges(keys=True, data=True)):
        dist = float("inf")
        geom = data.get("geometry") if isinstance(data, dict) else None
        if center_pt is not None and geom is not None and nearest_points is not None:
            try:
                nearest_on = nearest_points(center_pt, geom)[1]
                dist = _haversine(center_lat, center_lon, nearest_on.y, nearest_on.x)
            except Exception:
                dist = float("inf")
        if dist == float("inf"):
            try:
                n1 = graph.nodes[u]
                n2 = graph.nodes[v]
                mid_lat = (n1.get("y") + n2.get("y")) / 2
                mid_lon = (n1.get("x") + n2.get("x")) / 2
                dist = _haversine(center_lat, center_lon, mid_lat, mid_lon)
            except Exception:
                dist = float("inf")
        if dist <= radius_m:
            mark_block(u, v)
            mark_block(v, u)

    return list(blocked_edges)


def reset_graph_damage(graph: Any) -> None:
    """Hard reset damage flags and weights across the entire graph."""

    if graph is None:
        return

    for _, _, _, data in graph.edges(keys=True, data=True):
        if data is None:
            continue
        data.pop("blocked", None)
        if "orig_length" in data:
            base_len = data.get("orig_length")
        else:
            base_len = data.get("length")
        if base_len is not None:
            data["length"] = base_len
            data["weight"] = base_len
        else:
            data.pop("weight", None)


def reset_graph_weights(graph: Any) -> None:
    """Clear blocked flags and restore original lengths when available."""

    if graph is None:
        return
    for u, v, key, data in graph.edges(keys=True, data=True):
        if data.get("blocked"):
            data.pop("blocked", None)
        if "orig_length" in data:
            data["length"] = data.get("orig_length")


def reset_graph_state(graph: Any) -> None:
    """Fully reset edge state: clear block flags and restore weights/lengths."""

    if graph is None:
        return

    for _, _, _, data in graph.edges(keys=True, data=True):
        # Clear blocked flag
        if data.get("blocked"):
            data.pop("blocked", None)

        # Restore base length
        base_len = None
        if "orig_length" in data:
            base_len = data.get("orig_length")
        elif "length" in data:
            base_len = data.get("length")

        if base_len is not None:
            data["length"] = base_len
            data["weight"] = base_len
        else:
            # If no length info, drop weight to avoid stale infinities
            data.pop("weight", None)


def simulate_scattered_damage(graph: Any, count: int = 10):
    """Scatter small debris pockets (15-20m radius) directly on road geometry.

    Picks random edges, finds their midpoint (geometry-aware), and blocks around it.
    Returns a list of tuples: (lat, lon, radius_m, blocked_edges)
    """

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
                # Use shapely midpoint along the linestring
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
