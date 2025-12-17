"""OpenStreetMap data access and proximity helpers."""

from __future__ import annotations

from typing import Any, Tuple

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
    from math import radians, sin, cos, asin, sqrt

    R = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return R * c


# Backward compatibility for existing callers.
def get_graph(place_name: str) -> Any:
    return load_graph(place_name)
