"""Pure-Python Dijkstra and A* (no networkx helpers) with optional metrics."""

from __future__ import annotations

import heapq
import math
import time
from typing import Any, Dict, List, Tuple


def get_dist(G: Any, u: Any, v: Any) -> float:
    """Edge weight helper (defaults to 1.0 if missing)."""

    try:
        data = G[u][v][0]
        if data.get("blocked"):
            return float("inf")
        return float(data.get("length", 1.0))
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


def dijkstra_search(G: Any, start: Any, end: Any) -> tuple[List[Any], int, float, float, int]:
    """Dijkstra shortest path with heapq; returns (path, visited_count, total_dist, exec_time, max_fringe)."""

    t0 = time.perf_counter()
    queue: List[Tuple[float, Any]] = [(0.0, start)]
    distances: Dict[Any, float] = {node: math.inf for node in G.nodes}
    distances[start] = 0.0
    parents: Dict[Any, Any] = {node: None for node in G.nodes}
    visited_count = 0
    max_fringe = len(queue)

    while queue:
        current_dist, current = heapq.heappop(queue)
        if current_dist > distances.get(current, math.inf):
            continue
        visited_count += 1
        if visited_count % 1000 == 0:
            print(f"Algoritma çalışıyor... İncelenen düğüm sayısı: {visited_count}")
        if current == end:
            break

        for neighbor in G.neighbors(current):
            new_dist = current_dist + get_dist(G, current, neighbor)
            if new_dist < distances.get(neighbor, math.inf):
                distances[neighbor] = new_dist
                parents[neighbor] = current
                heapq.heappush(queue, (new_dist, neighbor))
        if len(queue) > max_fringe:
            max_fringe = len(queue)

    exec_time = time.perf_counter() - t0

    if distances[end] == math.inf:
        return [], visited_count, math.inf, exec_time, max_fringe

    path = _reconstruct_path(parents, end)
    return path, visited_count, distances[end], exec_time, max_fringe


def astar_search(G: Any, start: Any, end: Any) -> tuple[List[Any], int, float, float, int]:
    """A* search with Euclidean heuristic; returns (path, visited_count, total_dist, exec_time, max_fringe)."""

    t0 = time.perf_counter()
    queue: List[Tuple[float, Any]] = [(0.0, start)]
    g_score: Dict[Any, float] = {node: math.inf for node in G.nodes}
    g_score[start] = 0.0
    parents: Dict[Any, Any] = {node: None for node in G.nodes}
    visited_count = 0
    max_fringe = len(queue)

    while queue:
        _, current = heapq.heappop(queue)
        visited_count += 1
        if visited_count % 1000 == 0:
            print(f"Algoritma çalışıyor... İncelenen düğüm sayısı: {visited_count}")
        if current == end:
            break

        for neighbor in G.neighbors(current):
            tentative_g = g_score.get(current, math.inf) + get_dist(G, current, neighbor)
            if tentative_g < g_score.get(neighbor, math.inf):
                g_score[neighbor] = tentative_g
                parents[neighbor] = current
                f_score = tentative_g + heuristic(G, neighbor, end)
                heapq.heappush(queue, (f_score, neighbor))
        if len(queue) > max_fringe:
            max_fringe = len(queue)

    exec_time = time.perf_counter() - t0

    if g_score[end] == math.inf:
        return [], visited_count, math.inf, exec_time, max_fringe

    path = _reconstruct_path(parents, end)
    return path, visited_count, g_score[end], exec_time, max_fringe
