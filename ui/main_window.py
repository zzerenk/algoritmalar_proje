"""Main window wiring map, controls, and routing."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import DEFAULT_LOCATION, WINDOW_SIZE, WINDOW_TITLE
from core.algorithms import astar_search, dijkstra_search
from core.coordinate_sys import CoordinateTransformer, GeoPoint
from core.data_manager import get_nearest_node, load_buildings, load_graph
from ui.map_canvas import InteractiveMap
from ui.analysis_window import AnalysisWindow


class OperationWindow(QMainWindow):
    """Primary application window with operation and analysis pages."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(*WINDOW_SIZE)

        self.stacked = QStackedWidget()
        self.setCentralWidget(self.stacked)

        self.graph = None
        self.transformer = None
        self.buildings = None
        self.current_algorithm = "dijkstra"  # or "astar"
        self._pick_mode = None  # "start" or "end"
        self.start_node = None
        self.end_node = None

        self.operations_page = self._build_operations_page()
        self.analysis_page = self._build_analysis_page()

        self.stacked.addWidget(self.operations_page)
        self.stacked.addWidget(self.analysis_page)

        self._build_menu()
        self._ensure_graph_loaded()

    def _build_menu(self) -> None:
        view_menu = self.menuBar().addMenu("Görünüm")

        op_action = view_menu.addAction("Operasyon")
        op_action.triggered.connect(lambda: self.stacked.setCurrentIndex(0))

        analysis_action = view_menu.addAction("Analiz")
        analysis_action.triggered.connect(lambda: self._open_analysis(True))

    def _build_operations_page(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.map_view = InteractiveMap()
        self.map_view.setMinimumWidth(int(WINDOW_SIZE[0] * 0.7))
        self.map_view.coordinateClicked.connect(self._on_map_click)
        self.map_view.map_clicked.connect(self.handle_map_click)

        controls = self._build_controls()

        layout.addWidget(self.map_view, 3)
        layout.addWidget(controls, 1)

        return container

    def _build_controls(self) -> QWidget:
        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(6)

        self.start_input = QLineEdit()
        self.start_input.setPlaceholderText("Başlangıç (lat, lon)")

        self.start_select_btn = QPushButton("Başlangıç Seç")
        self.start_select_btn.clicked.connect(self._enable_start_pick)

        self.end_input = QLineEdit()
        self.end_input.setPlaceholderText("Bitiş (lat, lon)")

        self.end_select_btn = QPushButton("Bitiş Seç")
        self.end_select_btn.clicked.connect(self._enable_end_pick)

        self.analysis_button = QPushButton("ANALİZ ET")
        self.analysis_button.clicked.connect(lambda: self._open_analysis(True))

        self.compute_button = QPushButton("ROTA HESAPLA")
        self.compute_button.setMinimumHeight(48)
        self.compute_button.clicked.connect(self.run_algorithm)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)

        vbox.addWidget(self.start_input)
        vbox.addWidget(self.start_select_btn)
        vbox.addWidget(self.end_input)
        vbox.addWidget(self.end_select_btn)
        vbox.addWidget(self.analysis_button)
        vbox.addWidget(self.compute_button)
        vbox.addWidget(self.log_view, 1)

        return panel

    def _build_analysis_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.analysis_view = AnalysisWindow()
        layout.addWidget(self.analysis_view)
        return page

    def _parse_point(self, text: str) -> Optional[GeoPoint]:
        try:
            lat_str, lon_str = [part.strip() for part in text.split(",", maxsplit=1)]
            return GeoPoint(lat=float(lat_str), lon=float(lon_str))
        except Exception:
            return None

    def _enable_start_pick(self) -> None:
        self._pick_mode = "start"
        self.map_view.set_click_enabled(True)
        self._log("Haritada başlangıç noktası seçin.")

    def _enable_end_pick(self) -> None:
        self._pick_mode = "end"
        self.map_view.set_click_enabled(True)
        self._log("Haritada bitiş noktası seçin.")

    def _ensure_graph_loaded(self) -> None:
        if self.graph is not None and self.transformer is not None:
            return

        self._log(f"Grafik indiriliyor: {DEFAULT_LOCATION}")
        try:
            graph = load_graph(DEFAULT_LOCATION)
            self.graph = graph
            try:
                bld = load_buildings(DEFAULT_LOCATION)
                if getattr(bld, "crs", None) and bld.crs and not bld.crs.is_geographic:
                    bld = bld.to_crs("EPSG:4326")
                self.buildings = bld
                self._log(f"Bina verisi yüklendi: {len(bld)} kayıt; CRS={bld.crs}")
            except Exception as exc:
                self._log(f"Bina verisi yüklenemedi: {exc}")
            self.transformer = CoordinateTransformer(
                graph,
                screen_width=int(WINDOW_SIZE[0] * 0.7),
                screen_height=WINDOW_SIZE[1],
            )
            self.map_view.render_map(self.graph, self.buildings, self.transformer)
            self._log("Harita yüklendi ve etkileşim hazır.")
        except Exception as exc:
            self._log(f"Harita yüklenemedi: {exc}")

    def run_algorithm(self) -> None:
        start = self._parse_point(self.start_input.text())
        end = self._parse_point(self.end_input.text())

        if not start or not end:
            self._log("Lütfen 'lat, lon' formatında başlangıç ve bitiş girin.")
            return

        try:
            self._ensure_graph_loaded()
            if not self.graph:
                return

            start_node = get_nearest_node(self.graph, start.lat, start.lon)
            end_node = get_nearest_node(self.graph, end.lat, end.lon)
            self.start_node = start_node
            self.end_node = end_node
            if self.current_algorithm == "astar":
                path, visited, total_dist = astar_search(self.graph, start_node, end_node)
                color = "#27ae60"
                algo_name = "A*"
            else:
                path, visited, total_dist = dijkstra_search(self.graph, start_node, end_node)
                color = "#e74c3c"
                algo_name = "Dijkstra"

            if not path:
                self._log(f"{algo_name}: Yol bulunamadı.")
                return

            self.map_view.draw_path(self.graph, path, color, self.transformer)
            self._log(
                f"{algo_name}: düğüm={len(path)} ziyaret={visited} mesafe={total_dist:.1f} m"
            )
        except Exception as exc:  # pragma: no cover - user environment dependent
            self._log(f"Rota hesaplanamadı: {exc}")

    def _on_map_click(self, x: float, y: float) -> None:
        if not self.transformer:
            self._log("Harita henüz yüklenmedi.")
            return

        lat, lon = self.transformer.screen_to_geo(x, y)
        self._log(f"Harita tıklama: lat={lat:.6f}, lon={lon:.6f}")

    def handle_map_click(self, x: float, y: float) -> None:
        if not self.transformer or not self.graph:
            self._log("Harita henüz yüklenmedi.")
            return

        if not self._pick_mode:
            return

        lat, lon = self.transformer.screen_to_geo(x, y)
        try:
            node_id = get_nearest_node(self.graph, lat, lon)
        except Exception as exc:
            self._log(f"En yakın düğüm bulunamadı: {exc}")
            return

        if self._pick_mode == "start":
            self.start_input.setText(f"{lat:.6f}, {lon:.6f}")
            self.start_node = node_id
        else:
            self.end_input.setText(f"{lat:.6f}, {lon:.6f}")
            self.end_node = node_id

        self._log(f"Seçildi ({self._pick_mode}): düğüm={node_id} lat={lat:.6f} lon={lon:.6f}")
        self._pick_mode = None
        self.map_view.set_click_enabled(False)

    def _open_analysis(self, run: bool = False) -> None:
        self.stacked.setCurrentIndex(1)
        if run and self.graph is not None and self.start_node is not None and self.end_node is not None:
            self.analysis_view.start_comparison_test(self.graph, self.start_node, self.end_node)
        elif run:
            self._log("Analiz için başlangıç ve bitiş seçin ya da rota hesaplayın.")

    def _log(self, message: str) -> None:
        self.log_view.append(message)

    # Rendering moved to map_canvas render_map
