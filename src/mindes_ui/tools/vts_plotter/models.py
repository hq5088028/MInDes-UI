"""Serializable state and VTS loading helpers for VTS Plotter."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4


STATE_VERSION = 1


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
                axis.title_style.color = self.text_color
                axis.label_style.color = self.text_color
            if force or (axis.title_style.size == 16 and axis.label_style.size == 12):
                axis.title_style.size = self.title_font_size
                axis.label_style.size = self.label_font_size

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> VtkPlotConfig:
        cfg = cls()
        if isinstance(raw, dict):
            _merge_config_dataclass(cfg, raw)
            if not any(isinstance(raw.get(key), dict) for key in ("x_axis", "y_axis", "z_axis")):
                cfg.migrate_legacy_axes(force=True)
        return cfg


@dataclass
class VtsDatasetConfig:
    dataset_id: str = field(default_factory=lambda: uuid4().hex)
    path: str = ""
    label: str = ""
    enabled: bool = True
    field_name: str = ""
    colormap: str = "Cool-Warm"
    mode3d: str = "Surface"
    color_mode: str = "Colormap"
    color: str = "#1f77b4"
    auto_color_range: bool = True
    color_min: float = 0.0
    color_max: float = 1.0
    opacity: float = 1.0
    point_size: float = 3.0
    mesh_color: str = "#202020"
    mesh_width: float = 1.0
    clip_axis: str = "Z"
    clip_position: float = 0.0
    slice_axis: str = "Z"
    slice_position: float = 0.0
    contour_levels: str = ""
    glyph_color_mode: str = "Single Color"
    glyph_size_mode: str = "Magnitude"
    glyph_scale_factor: float = 1.0
    filter_enabled: bool = False
    filter_field: str = ""
    filter_min: float = 0.0
    filter_max: float = 1.0
    subregion_enabled: bool = False
    subregion_imin: int = 0
    subregion_imax: int = -1
    subregion_jmin: int = 0
    subregion_jmax: int = -1
    subregion_kmin: int = 0
    subregion_kmax: int = -1
    with_boundary: bool = True
    volume_sample_distance: float = 1.0

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> VtsDatasetConfig:
        cfg = cls()
        for key, value in raw.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        if not cfg.dataset_id:
            cfg.dataset_id = uuid4().hex
        return cfg


@dataclass
class VtsPlotterState:
    version: int = STATE_VERSION
    datasets: list[VtsDatasetConfig] = field(default_factory=list)
    vtk: VtkPlotConfig = field(default_factory=VtkPlotConfig)
    active_dataset_id: str = ""
    render_order: list[str] = field(default_factory=list)
    splitter_sizes: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "datasets": [asdict(item) for item in self.datasets],
            "vtk": asdict(self.vtk),
            "active_dataset_id": self.active_dataset_id,
            "render_order": list(self.render_order),
            "splitter_sizes": list(self.splitter_sizes),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> VtsPlotterState:
        if not isinstance(raw, dict) or raw.get("version", STATE_VERSION) != STATE_VERSION:
            return cls()
        datasets = [VtsDatasetConfig.from_dict(item) for item in raw.get("datasets", []) if isinstance(item, dict)]
        dataset_ids = [item.dataset_id for item in datasets]

        def normalized_order(key):
            order = [value for value in raw.get(key, []) if value in dataset_ids]
            return order + [value for value in dataset_ids if value not in order]

        return cls(
            datasets=datasets,
            vtk=VtkPlotConfig.from_dict(raw.get("vtk")),
            active_dataset_id=str(raw.get("active_dataset_id", "")),
            render_order=normalized_order("render_order"),
            splitter_sizes=[int(value) for value in raw.get("splitter_sizes", []) if isinstance(value, (int, float))],
        )


def _merge_config_dataclass(target, raw):
    for key, value in raw.items():
        if not hasattr(target, key):
            continue
        current = getattr(target, key)
        if is_dataclass(current) and isinstance(value, dict):
            _merge_config_dataclass(current, value)
        else:
            setattr(target, key, value)


def dataset_display_name(config: VtsDatasetConfig) -> str:
    return config.label or Path(config.path).stem or "VTS"
