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
from PyQt6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QGraphicsPolygonItem,
    QGraphicsEllipseItem,
    QGraphicsPathItem,
)


class InteractiveMap(QGraphicsView):
    coordinateClicked = pyqtSignal(float, float)
    map_clicked = pyqtSignal(float, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.scene().setBackgroundBrush(QColor("#000000"))
        self._zoom = 0
        self._click_marker = None
        self._click_enabled = False

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

    def draw_path(self, graph, path_list, color, transformer) -> None:
        """Overlay path, removing any previous path, and mark start/end."""

        if not graph or not transformer or not path_list or len(path_list) < 2:
            return

        scene = self.scene()

        # Remove previous path/markers (z >= 3 used for overlays).
        for item in list(scene.items()):
            if item.zValue() >= 3:
                scene.removeItem(item)

        painter_path = QPainterPath()
        first = path_list[0]
        x0, y0 = transformer.geo_to_screen(graph.nodes[first]["y"], graph.nodes[first]["x"])
        painter_path.moveTo(x0, y0)

        for node in path_list[1:]:
            x, y = transformer.geo_to_screen(graph.nodes[node]["y"], graph.nodes[node]["x"])
            painter_path.lineTo(x, y)

        pen = QPen(QColor(color))
        pen.setWidth(4)
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        path_item = QGraphicsPathItem(painter_path)
        path_item.setPen(pen)
        path_item.setZValue(3)
        scene.addItem(path_item)

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

        end_marker = QGraphicsEllipseItem(ex - half, ey - half, size, size)
        end_marker.setPen(marker_pen)
        end_marker.setBrush(marker_brush_end)
        end_marker.setZValue(4)
        scene.addItem(end_marker)

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
        if event.button() == Qt.MouseButton.LeftButton and self._click_enabled:
            scene_pos: QPointF = self.mapToScene(event.position().toPoint())
            self.coordinateClicked.emit(scene_pos.x(), scene_pos.y())
            self.map_clicked.emit(scene_pos.x(), scene_pos.y())

            # Visual feedback pin
            self._draw_click_marker(scene_pos)
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
