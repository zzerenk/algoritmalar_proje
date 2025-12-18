"""Interactive analysis dashboard with Plotly in a WebEngine view."""

from __future__ import annotations

import math
import time
from typing import Any, Dict

import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from core.algorithms import astar_search, dijkstra_search

# Apply a global dark template for all figures.
pio.templates.default = "plotly_dark"


class AnalysisWindow(QWidget):
    """Renders algorithm comparison charts as a Plotly dashboard."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.browser = QWebEngineView()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.browser)

    def start_comparison_test(self, graph: Any, start_node: Any, end_node: Any) -> None:
        if graph is None or start_node is None or end_node is None:
            return

        # Dijkstra metrics
        t0 = time.perf_counter()
        path_d, visit_d, len_d, _ = dijkstra_search(graph, start_node, end_node)
        time_d = time.perf_counter() - t0

        # A* metrics
        t1 = time.perf_counter()
        path_a, visit_a, len_a, _ = astar_search(graph, start_node, end_node)
        time_a = time.perf_counter() - t1

        dijkstra_metrics = self._build_metrics("Dijkstra", visit_d, time_d, len_d, path_d)
        astar_metrics = self._build_metrics("A*", visit_a, time_a, len_a, path_a)

        self.update_charts(dijkstra_metrics, astar_metrics)

    def _build_metrics(
        self, name: str, visited: int, time_s: float, path_len: float, path: Any
    ) -> Dict[str, Any]:
        # Derive lightweight metrics; memory estimate is heuristic.
        memory_mb = max(0.001, visited * 0.002)
        efficiency = self._compute_efficiency(time_s, visited, path_len)
        return {
            "name": name,
            "visited": visited,
            "time_s": time_s,
            "memory_mb": memory_mb,
            "efficiency": efficiency,
            "path_len": path_len,
            "node_hops": len(path) if path is not None else 0,
        }

    def _compute_efficiency(self, time_s: float, visited: int, path_len: float) -> float:
        # Simple composite score favoring shorter time, fewer visits, and shorter path.
        safe_time = max(time_s, 1e-6)
        safe_visits = max(visited, 1)
        safe_path = max(path_len, 1e-3)
        score = 1000.0 / (safe_time * math.log(safe_visits + 1) * safe_path)
        return max(min(score, 100.0), 0.0)

    def update_charts(self, dijkstra_metrics: Dict[str, Any], astar_metrics: Dict[str, Any]) -> None:
        fig = make_subplots(
            rows=2,
            cols=2,
            specs=[
                [{"type": "xy"}, {"type": "xy"}],
                [{"type": "xy"}, {"type": "indicator"}],
            ],
            subplot_titles=(
                "Search Effort",
                "Memory Usage",
                "Time Performance",
                "Efficiency Score",
            ),
        )

        neon_blue = "#00eaff"
        neon_pink = "#ff2dac"

        # Search effort (visited nodes)
        fig.add_trace(
            go.Bar(
                x=[dijkstra_metrics["name"], astar_metrics["name"]],
                y=[dijkstra_metrics["visited"], astar_metrics["visited"]],
                marker_color=[neon_pink, neon_blue],
                name="Search Effort",
                customdata=[
                    [dijkstra_metrics["name"], dijkstra_metrics["visited"], "Orta"],
                    [astar_metrics["name"], astar_metrics["visited"], "Yüksek"],
                ],
                hovertemplate="Algoritma: %{customdata[0]}<br>Değer: %{customdata[1]} Node<br>Verimlilik: %{customdata[2]}",
            ),
            row=1,
            col=1,
        )

        # Memory usage (heuristic MB)
        fig.add_trace(
            go.Bar(
                x=[dijkstra_metrics["name"], astar_metrics["name"]],
                y=[dijkstra_metrics["memory_mb"], astar_metrics["memory_mb"]],
                marker_color=[neon_blue, neon_pink],
                name="Memory (MB)",
                customdata=[
                    [dijkstra_metrics["name"], dijkstra_metrics["memory_mb"], "Tahmini"],
                    [astar_metrics["name"], astar_metrics["memory_mb"], "Tahmini"],
                ],
                hovertemplate="Algoritma: %{customdata[0]}<br>Değer: %{y:.3f} MB<br>Verimlilik: %{customdata[2]}",
            ),
            row=1,
            col=2,
        )

        # Time performance (horizontal bar)
        fig.add_trace(
            go.Bar(
                y=[dijkstra_metrics["name"], astar_metrics["name"]],
                x=[dijkstra_metrics["time_s"], astar_metrics["time_s"]],
                marker_color=[neon_pink, neon_blue],
                name="Time (s)",
                orientation="h",
                customdata=[
                    [dijkstra_metrics["name"], dijkstra_metrics["time_s"], "Orta"],
                    [astar_metrics["name"], astar_metrics["time_s"], "Yüksek"],
                ],
                hovertemplate="Algoritma: %{customdata[0]}<br>Değer: %{x:.3f} sn<br>Verimlilik: %{customdata[2]}",
            ),
            row=2,
            col=1,
        )

        # Efficiency gauge
        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=astar_metrics["efficiency"],
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": neon_blue},
                    "steps": [
                        {"range": [0, 40], "color": "#4b4b4b"},
                        {"range": [40, 70], "color": "#7f1a55"},
                        {"range": [70, 100], "color": "#144b5a"},
                    ],
                },
                title={"text": "Efficiency"},
                number={"suffix": " %"},
                name="Efficiency",
            ),
            row=2,
            col=2,
        )

        fig.update_layout(
            showlegend=False,
            height=700,
            margin=dict(l=40, r=40, t=80, b=40),
            paper_bgcolor="rgba(0,0,0,1)",
            plot_bgcolor="rgba(0,0,0,1)",
        )

        html_content = fig.to_html(include_plotlyjs="cdn")
        self.browser.setHtml(html_content)