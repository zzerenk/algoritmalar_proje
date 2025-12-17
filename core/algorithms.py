"""Pure-Python Dijkstra and A* (no networkx helpers)."""

from __future__ import annotations

import heapq
import math
from typing import Any, Dict, List, Tuple

def get_best_edge_weight(G: Any, u: Any, v: Any, ignore_damage: bool) -> float:
    """
    İki düğüm arasındaki en iyi (en kısa ve açık) kenarın ağırlığını bulur.
    Hem 'blocked' kontrolü yapar hem de 'weight' verisini okur.
    """
    edge_data = G.get_edge_data(u, v)
    if not edge_data:
        return float('inf')

    best_weight = float('inf')
    found_passable = False

    # Tüm paralel kenarları (varsa) kontrol et, en iyisini seç
    for key, data in edge_data.items():
        # 1. Hasar Kontrolü: Eğer hasar varsa ve hasarı görmezden gelmiyorsak, bu kenarı atla
        if not ignore_damage and data.get("blocked", False):
            continue
        
        # 2. Ağırlık Okuma: Önce 'weight' (bizim değiştirdiğimiz), yoksa 'length'
        # Hasarlı yolların weight'i inf olabilir, bunu dikkate almalıyız.
        w = float(data.get("weight", data.get("length", 1.0)))
        
        if w < best_weight:
            best_weight = w
            found_passable = True

    # Eğer tüm yollar kapalıysa veya yol yoksa sonsuz dön
    if not found_passable:
        return float('inf')
        
    return best_weight

def _node_xy(G: Any, node: Any) -> Tuple[float, float]:
    data = G.nodes[node]
    return float(data.get("x", 0.0)), float(data.get("y", 0.0))

def heuristic(G: Any, u: Any, v: Any) -> float:
    """
    Basit Öklid mesafesi.
    NOT: Koordinatlar derece (lat/lon) ise bu değer metreye göre çok küçük kalır.
    A* performansını artırmak için bunu kabaca metreye çeviriyoruz (x 111000).
    Bu mükemmel değil ama algoritmayı hızlandırır.
    """
    ux, uy = _node_xy(G, u)
    vx, vy = _node_xy(G, v)
    dist_deg = math.hypot(ux - vx, uy - vy)
    return dist_deg * 111000  # Dereceyi kabaca metreye çevir

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
            # DÜZELTME: Ağırlık ve Engel kontrolünü tek fonksiyonda yap
            weight = get_best_edge_weight(G, current, neighbor, ignore_damage)
            
            # Eğer yol kapalıysa (sonsuz ağırlık), atla
            if weight == float('inf'):
                continue

            new_dist = current_dist + weight
            
            if new_dist < distances.get(neighbor, float('inf')):
                distances[neighbor] = new_dist
                parents[neighbor] = current
                heapq.heappush(queue, (new_dist, neighbor))

    if not visited:
        return [], visited_count, float('inf'), False

    # Hedefe varamadıysak en yakın noktaya (Fallback)
    target_node = end if success else min(visited, key=lambda n: heuristic(G, n, end))
    total_dist = distances.get(target_node, float('inf'))
    path = _reconstruct_path(parents, target_node)
    
    return path, visited_count, total_dist, success

def astar_search(
    G: Any, start: Any, end: Any, ignore_damage: bool = False
) -> tuple[List[Any], int, float, bool]:
    
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
            # DÜZELTME: Ağırlık ve Engel kontrolünü tek fonksiyonda yap
            weight = get_best_edge_weight(G, current, neighbor, ignore_damage)
            
            if weight == float('inf'):
                continue

            tentative_g = g_score.get(current, float('inf')) + weight
            
            if tentative_g < g_score.get(neighbor, float('inf')):
                g_score[neighbor] = tentative_g
                parents[neighbor] = current
                f_score = tentative_g + heuristic(G, neighbor, end)
                heapq.heappush(queue, (f_score, neighbor))

    if not visited:
        return [], visited_count, float('inf'), False

    target_node = end if success else min(visited, key=lambda n: heuristic(G, n, end))
    total_dist = g_score.get(target_node, float('inf'))
    path = _reconstruct_path(parents, target_node)
    
    return path, visited_count, total_dist, success