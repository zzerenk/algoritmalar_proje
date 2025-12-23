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
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from config import DEFAULT_LOCATION, WINDOW_SIZE, WINDOW_TITLE
from core.algorithms import astar_search, dijkstra_search
from core.coordinate_sys import CoordinateTransformer, GeoPoint
from core.data_manager import (
    get_nearest_node,
    get_nearest_edge_point,
    load_buildings,
    load_graph,
    block_area,
    reset_graph_weights,
    simulate_scattered_damage,
)
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
        self.start_click_coord = None
        self.end_click_coord = None
        self.start_road_point = None
        self.end_road_point = None

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
        try:
            self.map_view.damage_requested.connect(self.handle_damage_request)
            self.map_view.set_mode(self.map_view.MODE_NAVIGATION)
        except Exception:
            pass

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

        self.damage_button = QPushButton("Hasar Modu")
        self.damage_button.setCheckable(True)
        self.damage_button.setStyleSheet(
            "QPushButton {background:#666; color:white;} QPushButton:checked {background:#e53935; color:white;}"
        )
        self.damage_button.toggled.connect(self._toggle_damage_mode)

        self.reset_damage_button = QPushButton("Hasarları Temizle")
        self.reset_damage_button.clicked.connect(self._reset_damages)

        self.random_disaster_button = QPushButton("Rastgele Deprem Simülasyonu")
        self.random_disaster_button.clicked.connect(self._simulate_random_disaster)

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
        vbox.addWidget(self.damage_button)
        vbox.addWidget(self.reset_damage_button)
        vbox.addWidget(self.random_disaster_button)
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
        try:
            self.map_view.set_mode(self.map_view.MODE_NAVIGATION)
            self.damage_button.setChecked(False)
        except Exception:
            pass
        self._log("Haritada başlangıç noktası seçin.")

    def _enable_end_pick(self) -> None:
        self._pick_mode = "end"
        self.map_view.set_click_enabled(True)
        try:
            self.map_view.set_mode(self.map_view.MODE_NAVIGATION)
            self.damage_button.setChecked(False)
        except Exception:
            pass
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
            if not self._resolve_route_inputs(start, end):
                return

            if self.current_algorithm == "astar":
                path, visited, total_dist, exec_time, max_fringe = astar_search(
                    self.graph, self.start_node, self.end_node
                )
                color = "#27ae60"
                algo_name = "A*"
            else:
                path, visited, total_dist, exec_time, max_fringe = dijkstra_search(
                    self.graph, self.start_node, self.end_node
                )
                color = "#e74c3c"
                algo_name = "Dijkstra"

            if not path:
                self._log(f"{algo_name}: Yol bulunamadı.")
                return

            walk_start = self._walk_distance(
                self.start_click_coord, self.start_road_point, self.start_node
            )
            walk_end = self._walk_distance(
                self.end_click_coord, self.end_road_point, self.end_node
            )
            real_total_dist = total_dist + walk_start + walk_end

            self.map_view.draw_path(
                self.graph,
                path,
                color,
                self.transformer,
                start_click_point=self.start_click_coord,
                start_road_point=self.start_road_point,
                start_node=self.start_node,
                end_click_point=self.end_click_coord,
                end_road_point=self.end_road_point,
                end_node=self.end_node,
            )
            self._log(
                f"{algo_name}: düğüm={len(path)} ziyaret={visited} mesafe={real_total_dist:.1f} m süre={exec_time*1000:.2f} ms fringe={max_fringe}"
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

        try:
            road_point = get_nearest_edge_point(self.graph, lat, lon)
        except Exception:
            road_point = None

        if self._pick_mode == "start":
            self.start_input.setText(f"{lat:.6f}, {lon:.6f}")
            self.start_node = road_point[2] if road_point and len(road_point) > 2 else node_id
            self.start_click_coord = GeoPoint(lat=lat, lon=lon)
            self.start_road_point = (road_point[0], road_point[1]) if road_point else None
        else:
            self.end_input.setText(f"{lat:.6f}, {lon:.6f}")
            self.end_node = road_point[2] if road_point and len(road_point) > 2 else node_id
            self.end_click_coord = GeoPoint(lat=lat, lon=lon)
            self.end_road_point = (road_point[0], road_point[1]) if road_point else None

        self.map_view.update_markers(
            self.transformer,
            start_pos=(self.start_click_coord.lat, self.start_click_coord.lon)
            if self.start_click_coord
            else None,
            end_pos=(self.end_click_coord.lat, self.end_click_coord.lon)
            if self.end_click_coord
            else None,
        )

        self._log(
            f"Seçildi ({self._pick_mode}): düğüm={node_id} lat={lat:.6f} lon={lon:.6f}"
        )
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

    def _resolve_route_inputs(self, start: GeoPoint, end: GeoPoint) -> bool:
        self._ensure_graph_loaded()
        if not self.graph:
            return False

        # Update start
        self.start_click_coord = start
        try:
            self.start_node = get_nearest_node(self.graph, start.lat, start.lon)
        except Exception as exc:
            self._log(f"Başlangıç düğümü bulunamadı: {exc}")
            return False
        try:
            road = get_nearest_edge_point(self.graph, start.lat, start.lon)
            self.start_road_point = (road[0], road[1])
            if len(road) > 2:
                self.start_node = road[2]
        except Exception:
            self.start_road_point = None

        # Update end
        self.end_click_coord = end
        try:
            self.end_node = get_nearest_node(self.graph, end.lat, end.lon)
        except Exception as exc:
            self._log(f"Bitiş düğümü bulunamadı: {exc}")
            return False
        try:
            road = get_nearest_edge_point(self.graph, end.lat, end.lon)
            self.end_road_point = (road[0], road[1])
            if len(road) > 2:
                self.end_node = road[2]
        except Exception:
            self.end_road_point = None

        self.map_view.update_markers(
            self.transformer,
            start_pos=(self.start_click_coord.lat, self.start_click_coord.lon),
            end_pos=(self.end_click_coord.lat, self.end_click_coord.lon),
        )
        return True

    def _walk_distance(
        self,
        click: Optional[GeoPoint],
        road_point: Optional[tuple],
        node_id: Optional[int],
    ) -> float:
        if click is None:
            return 0.0
        try:
            if road_point:
                click_to_road = self._haversine(click.lat, click.lon, road_point[0], road_point[1])
            else:
                click_to_road = 0.0
            if node_id is not None and self.graph is not None:
                n = self.graph.nodes[node_id]
                road_to_node = self._haversine(road_point[0], road_point[1], n["y"], n["x"]) if road_point else 0.0
            else:
                road_to_node = 0.0
            return click_to_road + road_to_node
        except Exception:
            return 0.0

    def _haversine(self, lat1, lon1, lat2, lon2) -> float:
        from math import radians, sin, cos, sqrt, atan2

        R = 6371000
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return R * c

    def _toggle_damage_mode(self, checked: bool) -> None:
        try:
            self.map_view.set_mode(
                self.map_view.MODE_DISASTER if checked else self.map_view.MODE_NAVIGATION
            )
            self.map_view.set_click_enabled(not checked)
            if checked:
                self._log("Hasar modu: haritaya tıklayarak blokaj ekleyin.")
            else:
                self._log("Navigasyon modu aktif.")
        except Exception as exc:
            self._log(f"Hasar modu ayarlanamadı: {exc}")

    def handle_damage_request(self, x: float, y: float) -> None:
        if not self.transformer or not self.graph:
            return
        lat, lon = self.transformer.screen_to_geo(x, y)
        radius = 120  # meters
        try:
            blocked_edges = block_area(self.graph, lat, lon, radius)
            self._log(f"Hasar eklendi: {len(blocked_edges)} kenar bloklandı.")
            self.map_view.draw_damage_marker(x, y)
        except Exception as exc:
            self._log(f"Hasar uygulanamadı: {exc}")

    def _reset_damages(self) -> None:
        if not self.graph:
            return
        try:
            reset_graph_weights(self.graph)
            self.map_view.clear_damages()
            self.map_view.clear_route()
            self._log("Tüm blokajlar temizlendi.")
        except Exception as exc:
            self._log(f"Temizleme hatası: {exc}")

    def _simulate_random_disaster(self) -> None:
        if not self.graph:
            return
        reply = QMessageBox.question(
            self,
            "Deprem Simülasyonu",
            "Rastgele hasar senaryosu uygulansın mı?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            centers = simulate_scattered_damage(self.graph, count=6)
            for lat, lon, *_ in centers:
                try:
                    x, y = self.transformer.geo_to_screen(lat, lon)
                    self.map_view.draw_damage_marker(x, y)
                except Exception:
                    continue
            self._log(f"Rastgele {len(centers)} hasar kümesi uygulandı.")
        except Exception as exc:
            self._log(f"Simülasyon hatası: {exc}")
