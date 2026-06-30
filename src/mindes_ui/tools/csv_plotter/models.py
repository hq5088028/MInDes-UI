"""Serializable state and CSV loading helpers for CSV Plotter."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd


STATE_VERSION = 1


@dataclass
class CsvDatasetConfig:
    dataset_id: str = field(default_factory=lambda: uuid4().hex)
    path: str = ""
    label: str = ""
    enabled: bool = True
    x2d: str = ""
    y2d: str = ""
    x3d: str = ""
    y3d: str = ""
    z3d: str = ""
    mode3d: str = "Surface"
    color_mode: str = "Fixed Color"
    color: str = "#1f77b4"
    colormap: str = "Viridis"
    auto_color_range: bool = True
    color_min: float = 0.0
    color_max: float = 1.0
    opacity: float = 0.85
    point_size: float = 5.0
    mesh_color: str = "#202020"
    mesh_width: float = 1.0

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CsvDatasetConfig":
        cfg = cls()
        for key, value in raw.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        if not cfg.dataset_id:
            cfg.dataset_id = uuid4().hex
        return cfg


@dataclass
class VtkTextStyle:
    font: str = "Arial"
    size: int = 16
    bold: bool = False
    italic: bool = False
    color: str = "#000000"


@dataclass
class VtkAxisConfig:
    title: str = "X"
    axis_visible: bool = True
    title_visible: bool = True
    label_visible: bool = True
    major_tick_visible: bool = True
    minor_tick_visible: bool = False
    grid_visible: bool = False
    format_mode: str = "Auto"
    decimals: int = 3
    line_color: str = "#000000"
    line_width: float = 1.0
    grid_color: str = "#b0b0b0"
    grid_width: float = 0.6
    title_style: VtkTextStyle = field(default_factory=lambda: VtkTextStyle(size=16))
    label_style: VtkTextStyle = field(default_factory=lambda: VtkTextStyle(size=12))


@dataclass
class VtkPlotConfig:
    background: str = "White"
    show_axes: bool = True
    show_colorbar: bool = True
    show_legend: bool = True
    x_title: str = "X"
    y_title: str = "Y"
    z_title: str = "Z"
    text_color: str = "#000000"
    title_font_size: int = 16
    label_font_size: int = 12
    auto_normalize: bool = True
    x_scale: float = 1.0
    y_scale: float = 1.0
    z_scale: float = 1.0
    auto_bounds: bool = True
    x_min: float = 0.0
    x_max: float = 1.0
    y_min: float = 0.0
    y_max: float = 1.0
    z_min: float = 0.0
    z_max: float = 1.0
    screenshot_scale: int = 2
    x_axis: VtkAxisConfig = field(default_factory=lambda: VtkAxisConfig(title="X"))
    y_axis: VtkAxisConfig = field(default_factory=lambda: VtkAxisConfig(title="Y"))
    z_axis: VtkAxisConfig = field(default_factory=lambda: VtkAxisConfig(title="Z"))
    tick_location: str = "Inside"
    fly_mode: str = "Closest Triad"
    grid_line_location: str = "All"
    title_offset_x: float = 20.0
    title_offset_y: float = 20.0
    label_offset: float = 20.0
    corner_offset: float = 0.0

    def migrate_legacy_axes(self, force=False):
        values = ((self.x_axis, self.x_title), (self.y_axis, self.y_title), (self.z_axis, self.z_title))
        for axis, title in values:
            if force or axis.title in ("X", "Y", "Z"):
                axis.title = title
            if force or (axis.title_style.color == "#000000" and axis.label_style.color == "#000000"):
                axis.title_style.color = self.text_color; axis.label_style.color = self.text_color
            if force or (axis.title_style.size == 16 and axis.label_style.size == 12):
                axis.title_style.size = self.title_font_size; axis.label_style.size = self.label_font_size

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "VtkPlotConfig":
        cfg = cls()
        if isinstance(raw, dict):
            _merge_config_dataclass(cfg, raw)
            if not any(isinstance(raw.get(key), dict) for key in ("x_axis", "y_axis", "z_axis")):
                cfg.migrate_legacy_axes(force=True)
        return cfg


def _merge_config_dataclass(target, raw):
    for key, value in raw.items():
        if not hasattr(target, key): continue
        current = getattr(target, key)
        if is_dataclass(current) and isinstance(value, dict): _merge_config_dataclass(current, value)
        else: setattr(target, key, value)


@dataclass
class CsvPlotterState:
    version: int = STATE_VERSION
    datasets: list[CsvDatasetConfig] = field(default_factory=list)
    figure: dict[str, Any] = field(default_factory=dict)
    vtk: VtkPlotConfig = field(default_factory=VtkPlotConfig)
    active_dataset_id: str = ""
    render_order_2d: list[str] = field(default_factory=list)
    render_order_3d: list[str] = field(default_factory=list)
    splitter_sizes: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "datasets": [asdict(item) for item in self.datasets],
            "figure": self.figure,
            "vtk": asdict(self.vtk),
            "active_dataset_id": self.active_dataset_id,
            "render_order_2d": list(self.render_order_2d),
            "render_order_3d": list(self.render_order_3d),
            "splitter_sizes": list(self.splitter_sizes),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "CsvPlotterState":
        if not isinstance(raw, dict) or raw.get("version", STATE_VERSION) != STATE_VERSION:
            return cls()
        datasets = [CsvDatasetConfig.from_dict(item) for item in raw.get("datasets", []) if isinstance(item, dict)]
        dataset_ids = [item.dataset_id for item in datasets]
        def normalized_order(key):
            order = [value for value in raw.get(key, []) if value in dataset_ids]
            return order + [value for value in dataset_ids if value not in order]
        return cls(
            datasets=datasets,
            figure=raw.get("figure", {}) if isinstance(raw.get("figure", {}), dict) else {},
            vtk=VtkPlotConfig.from_dict(raw.get("vtk")),
            active_dataset_id=str(raw.get("active_dataset_id", "")),
            render_order_2d=normalized_order("render_order_2d"),
            render_order_3d=normalized_order("render_order_3d"),
            splitter_sizes=[int(value) for value in raw.get("splitter_sizes", []) if isinstance(value, (int, float))],
        )


def load_csv(path: str) -> pd.DataFrame:
    """Read a comma-separated file without altering its columns or row order."""
    return pd.read_csv(path, encoding="utf-8-sig")


def numeric_series(frame: pd.DataFrame, column: str) -> np.ndarray:
    """Convert a selected column to float; non-numeric and Inf become NaN."""
    if not column or column not in frame.columns:
        return np.full(len(frame), np.nan, dtype=float)
    values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
    values[~np.isfinite(values)] = np.nan
    return values


def dataset_display_name(config: CsvDatasetConfig) -> str:
    return config.label or Path(config.path).stem or "CSV"
