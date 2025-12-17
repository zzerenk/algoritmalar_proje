"""Interactive analysis dashboard using Plotly + QWebEngineView."""

from __future__ import annotations

import time
from typing import Any, Dict, Tuple

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from core.algorithms import astar_search, dijkstra_search


class AnalysisWindow(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.browser = QWebEngineView(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.browser)

    def start_comparison_test(self, graph: Any, start_node: Any, end_node: Any) -> None:
        if graph is None or start_node is None or end_node is None:
            return

        # Measure Dijkstra
        t0 = time.perf_counter()
        d_out = dijkstra_search(graph, start_node, end_node)
        d_elapsed = time.perf_counter() - t0

        # Measure A*
        t1 = time.perf_counter()
        a_out = astar_search(graph, start_node, end_node)
        a_elapsed = time.perf_counter() - t1

        d_metrics = self._normalize_metrics(d_out, d_elapsed)
        a_metrics = self._normalize_metrics(a_out, a_elapsed)

        self.update_dashboard(d_metrics, a_metrics)

    @staticmethod
    def _normalize_metrics(metrics: Tuple[Any, ...], measured_time: float) -> Dict[str, Any]:
        """Accepts either (path, visited, length) or extended tuples; fills defaults."""

        path = metrics[0] if len(metrics) > 0 else []
        visited = metrics[1] if len(metrics) > 1 else 0
        total_len = metrics[2] if len(metrics) > 2 else 0.0
        exec_time = metrics[3] if len(metrics) > 3 else measured_time
        max_fringe = metrics[4] if len(metrics) > 4 else 0

        visited = max(int(visited or 0), 0)
        total_len = float(total_len or 0.0)
        exec_time = float(exec_time or 0.0)
        max_fringe = max(int(max_fringe or 0), 0)

        return {
            "path": path,
            "visited": visited,
            "total_len": total_len,
            "exec_time": exec_time,
            "max_fringe": max_fringe,
        }

    def update_dashboard(self, d_metrics: Dict[str, Any], a_metrics: Dict[str, Any]) -> None:
        # Extract values with fallbacks
        d_visit = d_metrics.get("visited", 0)
        a_visit = a_metrics.get("visited", 0)
        d_fringe = d_metrics.get("max_fringe", 0)
        a_fringe = a_metrics.get("max_fringe", 0)
        d_time_ms = (d_metrics.get("exec_time", 0.0) or 0.0) * 1000.0
        a_time_ms = (a_metrics.get("exec_time", 0.0) or 0.0) * 1000.0
        d_len = d_metrics.get("total_len", 0.0) or 0.0
        a_len = a_metrics.get("total_len", 0.0) or 0.0

        d_eff = d_len / d_visit if d_visit > 0 else 0.0
        a_eff = a_len / a_visit if a_visit > 0 else 0.0

        labels = ["Dijkstra", "A*"]
        colors = ["#ff6b3a", "#32e0a1"]  # warm orange / neon green
        mem_colors = ["#b388ff", "#7c4dff"]

        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                "Arama Eforu (Visited)",
                "Bellek Kullanımı (Max Fringe)",
                "İşlem Süresi (ms)",
                "Verimlilik Skoru (m/visit)",
            ),
            specs=[[{"type": "xy"}, {"type": "xy"}], [{"type": "domain"}, {"type": "xy"}]],
        )
        fig.update_layout(template="plotly_dark", height=700, margin=dict(t=70, l=40, r=40, b=40))

        # Graph 1: Search Effort
        fig.add_trace(
            go.Bar(
                x=labels,
                y=[d_visit, a_visit],
                marker_color=colors,
                hovertemplate="Algoritma: %{x}<br>Gezilen Düğüm: %{y}<extra></extra>",
                name="Ziyaret",
            ),
            row=1,
            col=1,
        )

        # Graph 2: Memory / Fringe
        fig.add_trace(
            go.Bar(
                x=labels,
                y=[d_fringe, a_fringe],
                marker_color=mem_colors,
                hovertemplate="Algoritma: %{x}<br>Max Kuyruk: %{y}<extra></extra>",
                name="Fringe",
            ),
            row=1,
            col=2,
        )

        # Graph 3: Efficiency gauge (domain cell)
        fig.add_trace(
            go.Indicator(
                mode="gauge+number+delta",
                value=d_eff,
                delta={"reference": a_eff, "relative": False, "valueformat": ".2f"},
                title={"text": "Dijkstra Verimlilik (m/visit)"},
                gauge={
                    "axis": {"range": [0, max(d_eff, a_eff, 1.0)]},
                    "bar": {"color": colors[0]},
                    "bgcolor": "rgba(255,255,255,0.05)",
                    "steps": [
                        {"range": [0, max(d_eff, a_eff, 1.0) * 0.5], "color": "rgba(255,107,58,0.3)"},
                        {"range": [max(d_eff, a_eff, 1.0) * 0.5, max(d_eff, a_eff, 1.0)], "color": "rgba(50,224,161,0.25)"},
                    ],
                },
                number={"valueformat": ".2f"},
            ),
            row=2,
            col=1,
        )

        # Graph 4: Time (horizontal)
        fig.add_trace(
            go.Bar(
                y=labels,
                x=[d_time_ms, a_time_ms],
                orientation="h",
                marker_color=colors,
                hovertemplate="Algoritma: %{y}<br>Süre: %{x:.3f} ms<extra></extra>",
                name="Süre",
            ),
            row=2,
            col=2,
        )

        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=True)

        html = fig.to_html(include_plotlyjs="cdn")
        self.browser.setHtml(html)