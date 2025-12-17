"""Pure-Python Dijkstra and A* (no networkx helpers)."""

from __future__ import annotations

import heapq
import math
from typing import Any, Dict, List, Tuple


def get_dist(G: Any, u: Any, v: Any) -> float:
    """Edge weight helper using edge length (defaults to 1.0 if missing)."""

    try:
        edge_data = G.get_edge_data(u, v)
        if not edge_data:
            return 1.0
        first = next(iter(edge_data.values()))
        return float(first.get("length", 1.0))
    except Exception:
        return 1.0


def _node_xy(G: Any, node: Any) -> Tuple[float, float]:
    data = G.nodes[node]
    return float(data.get("x", 0.0)), float(data.get("y", 0.0))


def heuristic(G: Any, u: Any, v: Any) -> float:
    """Euclidean heuristic between node coordinates."""

    ux, uy = _node_xy(G, u)
    vx, vy = _node_xy(G, v)
    return math.hypot(ux - vx, uy - vy)


def _reconstruct_path(parents: Dict[Any, Any], end: Any) -> List[Any]:
    path: List[Any] = []
    cur = end
    while cur is not None:
        path.append(cur)
        cur = parents.get(cur)
    path.reverse()
    return path


def dijkstra_search(
    G: Any, start: Any, end: Any, ignore_damage: bool = False
) -> tuple[List[Any], int, float, bool]:
    """Dijkstra shortest path; returns (path, visited_count, total_dist, success).

    ignore_damage lets us preview original routes without considering blocked edges.
    If unreachable, falls back to the visited node closest (euclidean) to target.
    """

    queue: List[Tuple[float, Any]] = [(0.0, start)]
    distances: Dict[Any, float] = {start: 0.0}
    parents: Dict[Any, Any] = {start: None}
    visited = set()
    visited_count = 0
    success = False

    while queue:
        current_dist, current = heapq.heappop(queue)
        if current in visited:
            continue
        visited.add(current)
        visited_count += 1
        if current == end:
            success = True
            break

        for neighbor in G.neighbors(current):
            edge_info = G.get_edge_data(current, neighbor)
            if edge_info:
                first_edge = next(iter(edge_info.values()))
                if first_edge.get("blocked", False) and not ignore_damage:
                    continue
            weight = get_dist(G, current, neighbor)
            new_dist = current_dist + weight
            if new_dist < distances.get(neighbor, math.inf):
                distances[neighbor] = new_dist
                parents[neighbor] = current
                heapq.heappush(queue, (new_dist, neighbor))

    if not visited:
        return [], visited_count, math.inf, False

    target_node = end if success else min(visited, key=lambda n: heuristic(G, n, end))
    total_dist = distances.get(target_node, math.inf)
    path = _reconstruct_path(parents, target_node)
    return path, visited_count, total_dist, success


def astar_search(
    G: Any, start: Any, end: Any, ignore_damage: bool = False
) -> tuple[List[Any], int, float, bool]:
    """A* search with Euclidean heuristic; returns (path, visited_count, total_dist, success).

    ignore_damage lets us preview original routes without considering blocked edges.
    If unreachable, falls back to the visited node closest (euclidean) to target.
    """

    queue: List[Tuple[float, Any]] = [(0.0, start)]
    g_score: Dict[Any, float] = {start: 0.0}
    parents: Dict[Any, Any] = {start: None}
    visited = set()
    visited_count = 0
    success = False

    while queue:
        _, current = heapq.heappop(queue)
        if current in visited:
            continue
        visited.add(current)
        visited_count += 1
        if current == end:
            success = True
            break

        for neighbor in G.neighbors(current):
            edge_info = G.get_edge_data(current, neighbor)
            if edge_info:
                first_edge = next(iter(edge_info.values()))
                if first_edge.get("blocked", False) and not ignore_damage:
                    continue
            tentative_g = g_score.get(current, math.inf) + get_dist(G, current, neighbor)
            if tentative_g < g_score.get(neighbor, math.inf):
                g_score[neighbor] = tentative_g
                parents[neighbor] = current
                f_score = tentative_g + heuristic(G, neighbor, end)
                heapq.heappush(queue, (f_score, neighbor))

    if not visited:
        return [], visited_count, math.inf, False

    target_node = end if success else min(visited, key=lambda n: heuristic(G, n, end))
    total_dist = g_score.get(target_node, math.inf)
    path = _reconstruct_path(parents, target_node)
    return path, visited_count, total_dist, success
