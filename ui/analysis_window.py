"""Analysis window showing live metrics from routing runs."""

from __future__ import annotations

import time
from typing import Any

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from core.algorithms import astar_search, dijkstra_search


class AnalysisWindow(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.figure = Figure(figsize=(6, 4), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

    def start_comparison_test(self, graph: Any, start_node: Any, end_node: Any) -> None:
        if graph is None or start_node is None or end_node is None:
            return

        # Dijkstra
        t0 = time.perf_counter()
        path_d, visit_d, len_d = dijkstra_search(graph, start_node, end_node)
        time_d = time.perf_counter() - t0

        # A*
        t1 = time.perf_counter()
        path_a, visit_a, len_a = astar_search(graph, start_node, end_node)
        time_a = time.perf_counter() - t1

        self._plot_metrics(visit_d, visit_a, time_d, time_a)

    def _plot_metrics(self, visit_d: int, visit_a: int, time_d: float, time_a: float) -> None:
        self.figure.clear()
        axes_visits = self.figure.add_subplot(1, 2, 1)
        axes_time = self.figure.add_subplot(1, 2, 2)

        # Visits bar chart
        visits = [visit_d, visit_a]
        labels = ["Dijkstra", "A*"]
        colors = ["#e74c3c", "#27ae60"]
        bars1 = axes_visits.bar(labels, visits, color=colors)
        axes_visits.set_title("Ziyaret Sayısı")
        for bar, val in zip(bars1, visits):
            axes_visits.text(bar.get_x() + bar.get_width() / 2, val, f"{val}",
                             ha="center", va="bottom", fontsize=8)

        # Time bar chart
        times = [time_d, time_a]
        bars2 = axes_time.bar(labels, times, color=colors)
        axes_time.set_title("Süre (sn)")
        for bar, val in zip(bars2, times):
            axes_time.text(bar.get_x() + bar.get_width() / 2, val, f"{val:.3f}s",
                           ha="center", va="bottom", fontsize=8)

        self.canvas.draw_idle()