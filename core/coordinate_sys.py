"""Coordinate transformation between geographic and screen space."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple


@dataclass
class GeoPoint:
    lat: float
    lon: float


class CoordinateTransformer:
    """Convert lat/lon <-> screen pixels using a single uniform scale."""

    def __init__(
        self,
        graph: Any,
        screen_width: int = 800,
        screen_height: int = 600,
        padding: int = 50,
    ) -> None:
        self.width = screen_width
        self.height = screen_height
        self.padding = padding

        lons = [data["x"] for _, data in graph.nodes(data=True)]
        lats = [data["y"] for _, data in graph.nodes(data=True)]

        self.min_lon = min(lons)
        self.max_lon = max(lons)
        self.min_lat = min(lats)
        self.max_lat = max(lats)

        lon_range = self.max_lon - self.min_lon
        lat_range = self.max_lat - self.min_lat

        usable_width = self.width - 2 * self.padding
        usable_height = self.height - 2 * self.padding

        if lon_range == 0 or lat_range == 0:
            self.scale = 1.0
        else:
            self.scale = min(usable_width / lon_range, usable_height / lat_range)

    def geo_to_screen(self, lat: float, lon: float) -> Tuple[int, int]:
        x = (lon - self.min_lon) * self.scale + self.padding
        y = (self.max_lat - lat) * self.scale + self.padding
        return int(x), int(y)

    def screen_to_geo(self, x: float, y: float) -> Tuple[float, float]:
        lon = (x - self.padding) / self.scale + self.min_lon
        lat = self.max_lat - (y - self.padding) / self.scale
        return lat, lon
