"""Interactive map canvas built on QGraphicsView."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QMouseEvent,
    QWheelEvent,
    QPainter,
    QPen,
    QBrush,
    QPolygonF,
    QPainterPath,
)
import math
from PyQt6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QGraphicsPolygonItem,
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
)


class InteractiveMap(QGraphicsView):
    coordinateClicked = pyqtSignal(float, float)
    map_clicked = pyqtSignal(float, float)
    damage_requested = pyqtSignal(float, float)

    MODE_NAVIGATION = 0
    MODE_DISASTER = 1

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.scene().setBackgroundBrush(QColor("#000000"))
        self._zoom = 0
        self._click_marker = None
        self._click_enabled = False
        self.mode = self.MODE_NAVIGATION
        self.route_items = []
        self.damage_items = []
        self.start_pin = None
        self.end_pin = None

    def render_map(self, graph, buildings, transformer) -> None:
        """Render buildings, roads, and nodes with z-ordering."""

        scene = self.scene()
        scene.clear()
        scene.setBackgroundBrush(QColor("#000000"))

        if not transformer:
            return

        # 1) Buildings (z=0)
        if buildings is not None and getattr(buildings, "empty", True) is False:
            brush = QBrush(QColor(44, 62, 80, 180))  # semi-transparent blue-gray
            border_pen = QPen(QColor("#1abc9c"))
            border_pen.setWidth(1)
            border_pen.setCosmetic(True)
            for geom in buildings.geometry.dropna():
                try:
                    for item in self._polygon_items_from_geom(
                        geom, transformer, brush, border_pen
                    ):
                        item.setZValue(0)
                        scene.addItem(item)
                except Exception:
                    continue

        # 2) Roads (z=1)
        if graph is not None:
            road_pen = QPen(QColor("#ffffff"))
            road_pen.setWidth(2)
            road_pen.setCosmetic(True)
            road_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            for u, v in graph.edges():
                try:
                    udata = graph.nodes[u]
                    vdata = graph.nodes[v]
                    x1, y1 = transformer.geo_to_screen(udata["y"], udata["x"])
                    x2, y2 = transformer.geo_to_screen(vdata["y"], vdata["x"])
                    line = scene.addLine(x1, y1, x2, y2, road_pen)
                    line.setZValue(1)
                except Exception:
                    continue

        # Nodes hidden to keep view clean with cosmetic roads.

        scene.setSceneRect(0, 0, transformer.width, transformer.height)
        self.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

        # Visual boundary/ruler-like frame to indicate drawable area.
        frame_pen = QPen(QColor("#555555"))
        frame_pen.setStyle(Qt.PenStyle.DashLine)
        frame_pen.setCosmetic(True)
        frame_pen.setWidth(1)
        frame = scene.addRect(scene.sceneRect(), frame_pen)
        frame.setZValue(0.5)

    def set_mode(self, mode_code: int) -> None:
        self.mode = mode_code
        if self.mode == self.MODE_DISASTER:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def draw_path(
        self,
        graph,
        path_list,
        color,
        transformer,
        start_click_point=None,
        start_road_point=None,
        start_node=None,
        end_click_point=None,
        end_road_point=None,
        end_node=None,
        end_road_pos=None,
        success: bool = True,
        clear_existing: bool = True,
    ) -> None:
        """Overlay path with walking (dashed) and driving (solid) legs, mark start/end."""

        if not graph or not transformer or not path_list or len(path_list) < 2:
            return

        scene = self.scene()

        if clear_existing:
            self.clear_route()

        # Driving leg: solid main path.
        painter_path = QPainterPath()
        first = path_list[0]
        x0, y0 = transformer.geo_to_screen(graph.nodes[first]["y"], graph.nodes[first]["x"])
        painter_path.moveTo(x0, y0)
        for node in path_list[1:]:
            x, y = transformer.geo_to_screen(graph.nodes[node]["y"], graph.nodes[node]["x"])
            painter_path.lineTo(x, y)

        drive_pen = QPen(QColor(color))
        drive_pen.setWidth(4)
        drive_pen.setCosmetic(True)
        drive_pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        path_item = QGraphicsPathItem(painter_path)
        path_item.setPen(drive_pen)
        path_item.setZValue(3)
        scene.addItem(path_item)
        self.route_items.append(path_item)

        # Walking legs: dashed cyan segments.
        walk_pen = QPen(QColor("#00FFFF"))
        walk_pen.setStyle(Qt.PenStyle.DashLine)
        walk_pen.setWidth(2)
        walk_pen.setCosmetic(True)
        walk_pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        def add_walk_segment(p1, p2):
            if p1 is None or p2 is None:
                return
            x1, y1 = transformer.geo_to_screen(p1[0], p1[1])
            x2, y2 = transformer.geo_to_screen(p2[0], p2[1])
            line = scene.addLine(x1, y1, x2, y2, walk_pen)
            line.setZValue(3)
            self.route_items.append(line)

        # Start side walking: click -> road point -> start node
        add_walk_segment(start_click_point, start_road_point)
        if start_node is not None:
            sn = graph.nodes[start_node]
            add_walk_segment(start_road_point, (sn["y"], sn["x"]))

        # End leg: mirror start on success; dotted red fallback on isolation.
        last_node_id = path_list[-1]
        if success and end_road_pos is not None:
            try:
                en_lat, en_lon = graph.nodes[last_node_id]["y"], graph.nodes[last_node_id]["x"]
                ex_node, ey_node = transformer.geo_to_screen(en_lat, en_lon)
                ex_road, ey_road = transformer.geo_to_screen(end_road_pos[0], end_road_pos[1])
                tail_drive = scene.addLine(ex_node, ey_node, ex_road, ey_road, drive_pen)
                tail_drive.setZValue(3)
                self.route_items.append(tail_drive)
                add_walk_segment(end_road_pos, end_click_point)
            except Exception:
                add_walk_segment(end_road_point, end_click_point)
        elif not success and end_click_point is not None:
            try:
                en_lat, en_lon = graph.nodes[last_node_id]["y"], graph.nodes[last_node_id]["x"]
                ex_node, ey_node = transformer.geo_to_screen(en_lat, en_lon)
                ex_pin, ey_pin = transformer.geo_to_screen(end_click_point[0], end_click_point[1])
                dotted_pen = QPen(QColor("#e53935"))
                dotted_pen.setStyle(Qt.PenStyle.DotLine)
                dotted_pen.setWidth(2)
                dotted_pen.setCosmetic(True)
                dotted_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                line = scene.addLine(ex_node, ey_node, ex_pin, ey_pin, dotted_pen)
                line.setZValue(3.2)
                self.route_items.append(line)
            except Exception:
                pass
        else:
            add_walk_segment(end_road_point, end_click_point)

        # Markers for start/end
        marker_pen = QPen(Qt.PenStyle.NoPen)
        marker_brush_start = QBrush(QColor("#27ae60"))
        marker_brush_end = QBrush(QColor("#e74c3c"))
        size = 8
        half = size / 2

        sx, sy = x0, y0
        ex, ey = transformer.geo_to_screen(
            graph.nodes[path_list[-1]]["y"], graph.nodes[path_list[-1]]["x"]
        )

        start_marker = QGraphicsEllipseItem(sx - half, sy - half, size, size)
        start_marker.setPen(marker_pen)
        start_marker.setBrush(marker_brush_start)
        start_marker.setZValue(4)
        scene.addItem(start_marker)
        self.route_items.append(start_marker)

        end_marker = QGraphicsEllipseItem(ex - half, ey - half, size, size)
        end_marker.setPen(marker_pen)
        end_marker.setBrush(marker_brush_end)
        end_marker.setZValue(4)
        scene.addItem(end_marker)
        self.route_items.append(end_marker)

    def _polygon_items_from_geom(self, geom, transformer, brush, pen):
        try:
            from shapely.geometry import Polygon, MultiPolygon
        except Exception:
            return []

        def build_polygon(coords):
            poly = QPolygonF()
            for lon, lat in coords:
                x, y = transformer.geo_to_screen(lat, lon)
                poly.append(QPointF(x, y))
            pen.setCosmetic(True)
            item = QGraphicsPolygonItem(poly)
            item.setBrush(brush)
            item.setPen(pen)
            return item

        if isinstance(geom, Polygon):
            return [build_polygon(geom.exterior.coords)]
        if isinstance(geom, MultiPolygon):
            items = []
            for poly_geom in geom.geoms:
                items.append(build_polygon(poly_geom.exterior.coords))
            return items
        return []

    def wheelEvent(self, event: QWheelEvent) -> None:
        # Basic zoom handler with modest scaling to avoid jumpy behavior.
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor

        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
            self._zoom += 1
        else:
            zoom_factor = zoom_out_factor
            self._zoom -= 1

        self.scale(zoom_factor, zoom_factor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos: QPointF = self.mapToScene(event.position().toPoint())
            if self.mode == self.MODE_NAVIGATION and self._click_enabled:
                self.coordinateClicked.emit(scene_pos.x(), scene_pos.y())
                self.map_clicked.emit(scene_pos.x(), scene_pos.y())
                self._draw_click_marker(scene_pos)
            elif self.mode == self.MODE_DISASTER:
                self.damage_requested.emit(scene_pos.x(), scene_pos.y())
        super().mousePressEvent(event)

    def set_click_enabled(self, enabled: bool) -> None:
        self._click_enabled = enabled

    def _draw_click_marker(self, pos: QPointF) -> None:
        scene = self.scene()
        if self._click_marker:
            scene.removeItem(self._click_marker)
        size = 10
        half = size / 2
        marker = QGraphicsEllipseItem(pos.x() - half, pos.y() - half, size, size)
        pen = QPen(QColor("#f1c40f"))
        pen.setCosmetic(True)
        marker.setPen(pen)
        marker.setBrush(QBrush(QColor(241, 196, 15, 160)))
        marker.setZValue(5)
        scene.addItem(marker)
        self._click_marker = marker

    def draw_damage_marker(self, x: float, y: float) -> None:
        scene = self.scene()
        size = 16
        half = size / 2
        marker = QGraphicsEllipseItem(x - half, y - half, size, size)
        pen = QPen(QColor("#e53935"))
        pen.setCosmetic(True)
        pen.setWidth(2)
        marker.setPen(pen)
        marker.setBrush(QBrush(QColor(229, 57, 53, 120)))
        marker.setZValue(4.5)
        scene.addItem(marker)
        self.damage_items.append(marker)

    def draw_damage_circle(self, transformer, center_lat: float, center_lon: float, radius_m: float) -> None:
        if transformer is None:
            return
        try:
            cx, cy = transformer.geo_to_screen(center_lat, center_lon)
            # Approximate radius in screen space using local degree offsets.
            delta_lat = radius_m / 111320.0
            denom = max(0.0001, abs(math.cos(math.radians(center_lat))))
            delta_lon = radius_m / (111320.0 * denom)
            rx, ry = transformer.geo_to_screen(center_lat + delta_lat, center_lon)
            radius_px = abs(ry - cy)
            if radius_px <= 0:
                radius_px = 5
        except Exception:
            return

        scene = self.scene()
        diameter = radius_px * 2
        circle = QGraphicsEllipseItem(cx - radius_px, cy - radius_px, diameter, diameter)
        pen = QPen(QColor(229, 57, 53))
        pen.setWidth(2)
        pen.setCosmetic(True)
        circle.setPen(pen)
        circle.setBrush(QBrush(QColor(229, 57, 53, 100)))
        circle.setZValue(4.2)
        scene.addItem(circle)
        self.damage_items.append(circle)

    def create_pin_item(self, x: float, y: float) -> QGraphicsPathItem:
        r = 8
        path = QPainterPath()
        # Head (circle) centered above the tip
        path.addEllipse(-r, -2 * r, 2 * r, 2 * r)
        # Tail (pointing to origin)
        path.moveTo(0, 0)
        path.lineTo(-r * 0.6, -r)
        path.lineTo(r * 0.6, -r)
        path.closeSubpath()

        item = QGraphicsPathItem(path)
        pen = QPen(QColor("#000000"))
        pen.setWidth(1)
        pen.setCosmetic(True)
        item.setPen(pen)
        item.setBrush(QBrush(QColor("#FF0000")))
        item.setPos(x, y)
        item.setZValue(10)
        return item

    def update_markers(self, transformer, start_pos=None, end_pos=None) -> None:
        scene = self.scene()
        if start_pos is not None:
            if self.start_pin:
                scene.removeItem(self.start_pin)
            sx, sy = transformer.geo_to_screen(start_pos[0], start_pos[1])
            self.start_pin = self.create_pin_item(sx, sy)
            scene.addItem(self.start_pin)
        if end_pos is not None:
            if self.end_pin:
                scene.removeItem(self.end_pin)
            ex, ey = transformer.geo_to_screen(end_pos[0], end_pos[1])
            self.end_pin = self.create_pin_item(ex, ey)
            scene.addItem(self.end_pin)

    def clear_route(self) -> None:
        scene = self.scene()
        for item in self.route_items:
            try:
                scene.removeItem(item)
            except Exception:
                continue
        self.route_items = []

    def clear_damages(self) -> None:
        scene = self.scene()
        for item in self.damage_items:
            try:
                scene.removeItem(item)
            except Exception:
                continue
        self.damage_items = []

    def draw_ghost_path(self, graph, path_list, transformer) -> None:
        if not graph or not transformer or not path_list or len(path_list) < 2:
            return
        scene = self.scene()
        # Do not clear route; ghost overlays with existing.
        for u, v in zip(path_list, path_list[1:]):
            try:
                x1, y1 = transformer.geo_to_screen(graph.nodes[u]["y"], graph.nodes[u]["x"])
                x2, y2 = transformer.geo_to_screen(graph.nodes[v]["y"], graph.nodes[v]["x"])
            except Exception:
                continue

            edge_info = graph.get_edge_data(u, v) or graph.get_edge_data(v, u)
            blocked = False
            if edge_info:
                try:
                    blocked = any(data.get("blocked", False) for data in edge_info.values())
                except Exception:
                    blocked = False

            pen = QPen(QColor("#e53935" if blocked else "#555555"))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidth(3)
            pen.setCosmetic(True)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)

            segment = scene.addLine(x1, y1, x2, y2, pen)
            segment.setOpacity(0.8 if blocked else 0.5)
            segment.setZValue(2.5)
            self.route_items.append(segment)

    def draw_dotted_connector(self, transformer, start_geo, end_geo) -> None:
        if transformer is None or start_geo is None or end_geo is None:
            return
        try:
            x1, y1 = transformer.geo_to_screen(start_geo[0], start_geo[1])
            x2, y2 = transformer.geo_to_screen(end_geo[0], end_geo[1])
        except Exception:
            return
        scene = self.scene()
        pen = QPen(QColor("#e53935"))
        pen.setStyle(Qt.PenStyle.DotLine)
        pen.setWidth(2)
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        line = scene.addLine(x1, y1, x2, y2, pen)
        line.setZValue(3.2)
        self.route_items.append(line)
