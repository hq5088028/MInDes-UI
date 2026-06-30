"""Configuration model for publication-quality statistic figures."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any


CONFIG_VERSION = 1


@dataclass
class TextStyle:
    text: str = ""
    font: str = "Arial"
    size: float = 11.0
    bold: bool = False
    italic: bool = False
    color: str = "#000000"
    visible: bool = True


@dataclass
class TickStyle:
    major_visible: bool = True
    minor_visible: bool = False
    direction: str = "in"
    major_length: float = 5.0
    minor_length: float = 3.0
    width: float = 1.0
    color: str = "#000000"
    show_bottom: bool = True
    show_top: bool = False
    show_left: bool = True
    show_right: bool = False
    format_mode: str = "Auto"
    decimals: int = 2
    manual_mode: str = "Auto"
    positions: str = ""
    start: float = 0.0
    stop: float = 1.0
    step: float = 0.1
    font: TextStyle = field(default_factory=lambda: TextStyle(size=9.0))


@dataclass
class GridStyle:
    visible: bool = False
    color: str = "#b0b0b0"
    linestyle: str = "--"
    linewidth: float = 0.6
    alpha: float = 0.6


@dataclass
class AxisStyle:
    label: TextStyle = field(default_factory=lambda: TextStyle(size=11.0))
    scale: str = "Linear"
    auto_range: bool = True
    minimum: float = 0.0
    maximum: float = 1.0
    inverted: bool = False
    tick: TickStyle = field(default_factory=TickStyle)
    grid: GridStyle = field(default_factory=GridStyle)
    spine_visible: bool = True
    spine_width: float = 1.0
    spine_color: str = "#000000"


@dataclass
class ErrorStyle:
    mode: str = "None"
    source: str = "Constant"
    column: str = ""
    constant: float = 0.0
    every: int = 1
    capsize: float = 3.0
    capthick: float = 1.0
    linewidth: float = 1.0
    color: str = "#000000"
    fill_color: str = "#808080"
    fill_alpha: float = 0.2


@dataclass
class CurveStyle:
    column: str = ""
    side: str = "left"
    visible: bool = True
    legend_text: str = ""
    color: str = "#000000"
    linewidth: float = 1.5
    linestyle: str = "-"
    marker: str = "None"
    markersize: float = 5.0
    marker_face_color: str = "#ffffff"
    marker_edge_color: str = "#000000"
    marker_edge_width: float = 0.8
    markevery: int = 1
    axis: AxisStyle = field(default_factory=AxisStyle)
    error: ErrorStyle = field(default_factory=ErrorStyle)


@dataclass
class LegendStyle:
    visible: bool = True
    location: str = "best"
    custom_anchor: bool = False
    anchor_x: float = 0.0
    anchor_y: float = 0.0
    columns: int = 1
    frame_visible: bool = True
    edge_color: str = "#000000"
    face_color: str = "#ffffff"
    frame_alpha: float = 0.85
    font: TextStyle = field(default_factory=lambda: TextStyle(size=9.0))


@dataclass
class FigureConfig:
    version: int = CONFIG_VERSION
    width_cm: float = 16.0
    height_cm: float = 10.0
    unit: str = "cm"
    background: str = "White"
    margin_left_cm: float = 1.8
    margin_right_cm: float = 1.8
    margin_top_cm: float = 1.0
    margin_bottom_cm: float = 1.4
    title: TextStyle = field(default_factory=lambda: TextStyle(size=12.0, bold=True))
    x_axis: AxisStyle = field(default_factory=AxisStyle)
    shared_y_axis: AxisStyle = field(default_factory=AxisStyle)
    show_top_spine: bool = True
    show_bottom_spine: bool = True
    show_left_spine: bool = True
    show_right_spine: bool = True
    use_latex: bool = False
    legend: LegendStyle = field(default_factory=LegendStyle)
    export_dpi: int = 600
    curves: list[CurveStyle] = field(default_factory=list)

    def copy(self) -> "FigureConfig":
        return deepcopy(self)

    def to_dict(self, *, include_curves: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if not include_curves:
            data["curves"] = []
            data["title"]["text"] = ""
            data["x_axis"]["label"]["text"] = ""
            data["shared_y_axis"]["label"]["text"] = ""
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "FigureConfig":
        cfg = cls()
        if not isinstance(raw, dict) or raw.get("version", CONFIG_VERSION) != CONFIG_VERSION:
            return cfg
        _merge_dataclass(cfg, raw)
        curves = []
        for value in raw.get("curves", []):
            curve = CurveStyle()
            if isinstance(value, dict):
                _merge_dataclass(curve, value)
            curves.append(curve)
        cfg.curves = curves
        return cfg


def _merge_dataclass(target: Any, values: dict[str, Any]) -> None:
    for key, value in values.items():
        if key == "curves" or not hasattr(target, key):
            continue
        current = getattr(target, key)
        if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
            _merge_dataclass(current, value)
        else:
            setattr(target, key, value)


def new_curve(column: str, side: str, index: int) -> CurveStyle:
    colors = ["#000000", "#d62728", "#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e"]
    lines = ["-", "--", "-.", ":", "-", "--"]
    markers = ["None", "o", "s", "^", "v", "D"]
    color = colors[index % len(colors)]
    curve = CurveStyle(
        column=column,
        side=side,
        legend_text=column,
        color=color,
        linestyle=lines[index % len(lines)],
        marker=markers[index % len(markers)],
        marker_edge_color=color,
    )
    curve.axis.label.text = column
    curve.axis.label.color = color
    curve.axis.tick.color = color
    curve.axis.tick.font.color = color
    curve.axis.tick.show_left = side == "left"
    curve.axis.tick.show_right = side == "right"
    curve.axis.spine_color = color
    curve.axis.grid.color = color
    curve.error.color = color
    curve.error.fill_color = color
    return curve


def convert_length(value: float, from_unit: str, to_unit: str) -> float:
    factors = {"cm": 1.0, "in": 2.54, "mm": 0.1}
    return float(value) * factors[from_unit] / factors[to_unit]
