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
    get_nearest_edge_point,
    load_buildings,
    load_graph,
    block_area,
    apply_damage_area,
    reset_graph_weights,
    reset_graph_state,
    reset_graph_damage,
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
        self.damage_active = False

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
        self.map_view.damage_requested.connect(self.handle_damage_request)
        self.map_view.set_mode(self.map_view.MODE_NAVIGATION)

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
        self.map_view.set_mode(self.map_view.MODE_NAVIGATION)
        self.damage_button.setChecked(False)
        self._log("Haritada başlangıç noktası seçin.")

    def _enable_end_pick(self) -> None:
        self._pick_mode = "end"
        self.map_view.set_click_enabled(True)
        self.map_view.set_mode(self.map_view.MODE_NAVIGATION)
        self.damage_button.setChecked(False)
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

            # Clear stale damage/weights unless a disaster scenario is active.
            if not self.damage_active:
                reset_graph_state(self.graph)

            if self.current_algorithm == "astar":
                path, visited, total_dist, success = astar_search(
                    self.graph, self.start_node, self.end_node
                )
                color = "#27ae60"
                algo_name = "A*"
            else:
                path, visited, total_dist, success = dijkstra_search(
                    self.graph, self.start_node, self.end_node
                )
                color = "#e74c3c"
                algo_name = "Dijkstra"

            if not path:
                QMessageBox.warning(self, "Uyarı", "Bu iki nokta arasında karayolu bağlantısı yok!")
                self._log(f"{algo_name}: Yol bulunamadı.")
                return

            walk_start = self._walk_distance(
                self.start_click_coord, self.start_road_point, self.start_node
            )
            walk_end = self._walk_distance(
                self.end_click_coord, self.end_road_point, self.end_node
            )
            real_total_dist = total_dist + walk_start + walk_end

            end_road_pos = None
            if success:
                end_road_pos = self.end_road_point
            else:
                QMessageBox.warning(
                    self,
                    "Uyarı",
                    "Target is isolated! Route calculated to the nearest safe point.",
                )

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
                end_road_pos=end_road_pos,
                success=success,
            )
            self._log(
                f"{algo_name}: düğüm={len(path)} ziyaret={visited} mesafe={real_total_dist:.1f} m"
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
            proj_lat, proj_lon, node_id = get_nearest_edge_point(self.graph, lat, lon)
        except ValueError:
            QMessageBox.warning(self, "Uyarı", "Lütfen bir yola yakın tıklayın!")
            return
        except Exception as exc:
            self._log(f"En yakın yol bulunamadı: {exc}")
            QMessageBox.warning(self, "Uyarı", "Lütfen bir yola yakın tıklayın!")
            return
        if node_id is None:
            QMessageBox.warning(self, "Uyarı", "Lütfen bir yola yakın tıklayın!")
            return

        if self._pick_mode == "start":
            self.start_input.setText(f"{lat:.6f}, {lon:.6f}")
            self.start_node = node_id
            self.start_click_coord = (lat, lon)
            self.start_road_point = (proj_lat, proj_lon)
        else:
            self.end_input.setText(f"{lat:.6f}, {lon:.6f}")
            self.end_node = node_id
            self.end_click_coord = (lat, lon)
            self.end_road_point = (proj_lat, proj_lon)

        self._log(f"Seçildi ({self._pick_mode}): düğüm={node_id} lat={lat:.6f} lon={lon:.6f}")
        self._pick_mode = None
        self.map_view.set_click_enabled(False)
        self.map_view.set_mode(self.map_view.MODE_NAVIGATION)
        self.map_view.update_markers(
            self.transformer,
            start_pos=self.start_click_coord,
            end_pos=self.end_click_coord,
        )

    def _open_analysis(self, run: bool = False) -> None:
        self.stacked.setCurrentIndex(1)
        if run and self.graph is not None and self.start_node is not None and self.end_node is not None:
            self.analysis_view.start_comparison_test(self.graph, self.start_node, self.end_node)
        elif run:
            self._log("Analiz için başlangıç ve bitiş seçin ya da rota hesaplayın.")

    def _toggle_damage_mode(self, checked: bool) -> None:
        if checked:
            self.map_view.set_mode(self.map_view.MODE_DISASTER)
            self.map_view.set_click_enabled(False)
        else:
            self.map_view.set_mode(self.map_view.MODE_NAVIGATION)
            self.map_view.set_click_enabled(True)

    def handle_damage_request(self, x: float, y: float) -> None:
        if not self.transformer or not self.graph:
            self._log("Harita henüz yüklenmedi.")
            return

        lat, lon = self.transformer.screen_to_geo(x, y)
        try:
            radius = 50.0
            blocked_edges = apply_damage_area(self.graph, lat, lon, radius)
            self.map_view.draw_damage_circle(self.transformer, lat, lon, radius)
            if blocked_edges:
                self.damage_active = True
            self._log(f"Hasar uygulandı: {len(blocked_edges)} kenar kapatıldı.")
        except Exception as exc:
            self._log(f"Hasar uygulanamadı: {exc}")
            QMessageBox.warning(self, "Uyarı", "Hasar işlemi başarısız oldu.")

    def _reset_damages(self) -> None:
        if self.graph is None:
            return
        self.map_view.clear_damages()
        reset_graph_weights(self.graph)
        self.damage_active = False
        try:
            self.run_algorithm()
        except Exception:
            pass

    def _resolve_route_inputs(self, start: GeoPoint, end: GeoPoint, update_markers: bool = True) -> bool:
        self._ensure_graph_loaded()
        if not self.graph or not self.transformer:
            return False

        self.start_click_coord = (start.lat, start.lon)
        self.end_click_coord = (end.lat, end.lon)

        try:
            s_proj_lat, s_proj_lon, start_node = get_nearest_edge_point(
                self.graph, start.lat, start.lon
            )
            e_proj_lat, e_proj_lon, end_node = get_nearest_edge_point(
                self.graph, end.lat, end.lon
            )
        except ValueError:
            QMessageBox.warning(self, "Uyarı", "Lütfen bir yola yakın tıklayın!")
            return False
        except Exception as exc:
            self._log(f"En yakın yol bulunamadı: {exc}")
            QMessageBox.warning(self, "Uyarı", "Lütfen bir yola yakın tıklayın!")
            return False

        if start_node is None or end_node is None:
            QMessageBox.warning(self, "Uyarı", "Lütfen bir yola yakın tıklayın!")
            return False

        self.start_node = start_node
        self.end_node = end_node
        self.start_road_point = (s_proj_lat, s_proj_lon)
        self.end_road_point = (e_proj_lat, e_proj_lon)

        if update_markers:
            self.map_view.update_markers(
                self.transformer,
                start_pos=self.start_click_coord,
                end_pos=self.end_click_coord,
            )
        return True

    def _simulate_random_disaster(self) -> None:
        start = self._parse_point(self.start_input.text())
        end = self._parse_point(self.end_input.text())

        if not start or not end:
            self._log("Rastgele senaryo için başlangıç/bitiş girin.")
            return

        if not self._resolve_route_inputs(start, end):
            return

        if not self.graph or not self.transformer:
            return

        # Clean previous visuals and reset graph damage flags.
        self.map_view.clear_damages()
        self.map_view.clear_route()
        reset_graph_damage(self.graph)
        self.damage_active = True  # Simulation will keep damage state active

        # Apply scattered micro damages first so ghost path can show red overlaps.
        damages = simulate_scattered_damage(self.graph, count=10)
        total_blocked = 0
        for lat, lon, radius, _ in damages:
            blocked_edges = apply_damage_area(self.graph, lat, lon, radius)
            total_blocked += len(blocked_edges)
            try:
                self.map_view.draw_damage_circle(self.transformer, lat, lon, radius)
            except Exception:
                pass

        # Baseline (ghost) path ignoring damage but colored where blocked.
        if self.current_algorithm == "astar":
            ghost_path, _, _, _ = astar_search(
                self.graph, self.start_node, self.end_node, ignore_damage=True
            )
        else:
            ghost_path, _, _, _ = dijkstra_search(
                self.graph, self.start_node, self.end_node, ignore_damage=True
            )
        if ghost_path:
            self.map_view.draw_ghost_path(self.graph, ghost_path, self.transformer)
        else:
            QMessageBox.warning(self, "Uyarı", "Hasar öncesi yol bulunamadı.")
            return

        # Now compute damaged path (actual route).
        if self.current_algorithm == "astar":
            path, visited, total_dist, success = astar_search(
                self.graph, self.start_node, self.end_node
            )
            color = "#27ae60"
            algo_name = "A*"
        else:
            path, visited, total_dist, success = dijkstra_search(
                self.graph, self.start_node, self.end_node
            )
            color = "#e74c3c"
            algo_name = "Dijkstra"

        if not path:
            QMessageBox.warning(self, "Uyarı", "Hasar sonrası ulaşılabilir yol bulunamadı!")
            self._log(f"{algo_name}: Hasar sonrası rota yok; kapalı kenar={total_blocked}.")
            return

        walk_start = self._walk_distance(
            self.start_click_coord, self.start_road_point, self.start_node
        )
        walk_end = self._walk_distance(self.end_click_coord, self.end_road_point, self.end_node)
        real_total_dist = total_dist + walk_start + walk_end

        end_road_pos = None
        if success:
            end_road_pos = self.end_road_point
        else:
            QMessageBox.warning(
                self,
                "Uyarı",
                "Target is isolated! Route calculated to the nearest safe point.",
            )

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
            end_road_pos=end_road_pos,
            success=success,
            clear_existing=False,
        )
        self._log(
            f"{algo_name}: Hasar sonrası düğüm={len(path)} ziyaret={visited} mesafe={real_total_dist:.1f} m; kapalı kenar={total_blocked}"
        )

    def _log(self, message: str) -> None:
        self.log_view.append(message)

    def _walk_distance(self, click_coord, road_point, node_id) -> float:
        if click_coord is None or road_point is None or node_id is None:
            return 0.0
        try:
            nlat = self.graph.nodes[node_id].get("y")
            nlon = self.graph.nodes[node_id].get("x")
            seg1 = self._haversine(click_coord[0], click_coord[1], road_point[0], road_point[1])
            seg2 = self._haversine(road_point[0], road_point[1], nlat, nlon)
            return seg1 + seg2
        except Exception:
            return 0.0

    def _haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        from math import radians, sin, cos, asin, sqrt

        R = 6371000.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        return R * c

    # Rendering moved to map_canvas render_map
