"""Versioned, data-free visual style formats for CSV Plotter."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass

from plot_config import AxisStyle, CurveStyle, FigureConfig
from .models import CsvDatasetConfig, VtkPlotConfig


STYLE_VERSION = 1
STYLE_3D_VERSION = 2
STYLE_2D_KIND = "MInDes CSV Plotter 2D Style"
STYLE_3D_KIND = "MInDes CSV Plotter 3D Style"


def _validate_dataclass_payload(model, raw, label):
    if not isinstance(raw, dict): raise ValueError(f"{label} must be an object.")
    for key, value in raw.items():
        if not hasattr(model, key): continue
        expected = getattr(model, key)
        if is_dataclass(expected):
            _validate_dataclass_payload(expected, value, f"{label}.{key}")
        elif isinstance(expected, bool):
            if not isinstance(value, bool): raise ValueError(f"{label}.{key} has an invalid type.")
        elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
            if not isinstance(value, (int, float)) or isinstance(value, bool): raise ValueError(f"{label}.{key} has an invalid type.")
        elif isinstance(expected, str):
            if not isinstance(value, str): raise ValueError(f"{label}.{key} has an invalid type.")
        elif isinstance(expected, list) and not isinstance(value, list):
            raise ValueError(f"{label}.{key} has an invalid type.")


def _reset_axis_data(axis: AxisStyle) -> None:
    axis.label.text = ""
    axis.auto_range = True; axis.minimum = 0.0; axis.maximum = 1.0
    tick = axis.tick
    tick.manual_mode = "Auto"; tick.positions = ""; tick.start = 0.0; tick.stop = 1.0; tick.step = 0.1


def _restore_axis_data(target: AxisStyle, source: AxisStyle) -> None:
    target.label.text = source.label.text
    target.auto_range = source.auto_range; target.minimum = source.minimum; target.maximum = source.maximum
    target.tick.manual_mode = source.tick.manual_mode; target.tick.positions = source.tick.positions
    target.tick.start = source.tick.start; target.tick.stop = source.tick.stop; target.tick.step = source.tick.step


def _strip_axis_data_dict(raw: dict) -> None:
    raw.get("label", {}).pop("text", None)
    for key in ("auto_range", "minimum", "maximum"): raw.pop(key, None)
    tick = raw.get("tick", {})
    for key in ("manual_mode", "positions", "start", "stop", "step"): tick.pop(key, None)


def _curve_template_dict(curve: CurveStyle) -> dict:
    raw = asdict(sanitize_curve_template(curve))
    for key in ("column", "legend_text", "side"): raw.pop(key, None)
    _strip_axis_data_dict(raw.get("axis", {}))
    error = raw.get("error", {})
    for key in ("mode", "source", "column", "constant"): error.pop(key, None)
    return raw


def _dataset_template_dict(dataset: CsvDatasetConfig) -> dict:
    raw = asdict(sanitize_dataset_template(dataset))
    for key in ("dataset_id", "path", "label", "enabled", "x2d", "y2d", "x3d", "y3d", "z3d",
                "auto_color_range", "color_min", "color_max"):
        raw.pop(key, None)
    return raw


def sanitize_curve_template(curve: CurveStyle) -> CurveStyle:
    result = deepcopy(curve)
    result.column = ""; result.legend_text = ""; result.side = "left"
    _reset_axis_data(result.axis)
    result.error.mode = "None"; result.error.source = "Constant"
    result.error.column = ""; result.error.constant = 0.0
    return result


def apply_curve_template(curve: CurveStyle, template: CurveStyle) -> CurveStyle:
    result = deepcopy(template)
    result.column = curve.column; result.legend_text = curve.legend_text; result.side = curve.side
    _restore_axis_data(result.axis, curve.axis)
    result.error.mode = curve.error.mode; result.error.source = curve.error.source
    result.error.column = curve.error.column; result.error.constant = curve.error.constant
    return result


def make_2d_style_payload(config: FigureConfig, templates=None) -> dict:
    clean = config.copy(); clean.curves = []
    clean.title.text = ""; _reset_axis_data(clean.x_axis); _reset_axis_data(clean.shared_y_axis)
    source = list(config.curves) or list(templates or [])
    figure_raw = clean.to_dict(include_curves=False)
    figure_raw.get("title", {}).pop("text", None)
    _strip_axis_data_dict(figure_raw.get("x_axis", {})); _strip_axis_data_dict(figure_raw.get("shared_y_axis", {}))
    return {
        "kind": STYLE_2D_KIND, "version": STYLE_VERSION,
        "figure": figure_raw,
        "curve_templates": [_curve_template_dict(curve) for curve in source],
    }


def parse_2d_style_payload(raw: dict) -> tuple[FigureConfig, list[CurveStyle]]:
    if not isinstance(raw, dict) or raw.get("kind") != STYLE_2D_KIND or raw.get("version") != STYLE_VERSION:
        raise ValueError("This is not a supported MInDes 2D style file.")
    figure_raw = raw.get("figure")
    template_raw = raw.get("curve_templates", [])
    if not isinstance(figure_raw, dict) or not isinstance(template_raw, list):
        raise ValueError("The 2D style file is incomplete.")
    _validate_dataclass_payload(FigureConfig(), figure_raw, "figure")
    for index, value in enumerate(template_raw): _validate_dataclass_payload(CurveStyle(), value, f"curve_templates[{index}]")
    combined = deepcopy(figure_raw); combined["curves"] = template_raw
    parsed = FigureConfig.from_dict(combined); templates = [sanitize_curve_template(value) for value in parsed.curves]
    parsed.curves = []; parsed.title.text = ""; _reset_axis_data(parsed.x_axis); _reset_axis_data(parsed.shared_y_axis)
    return parsed, templates


def apply_2d_visual_style(current: FigureConfig, style: FigureConfig, templates: list[CurveStyle]) -> FigureConfig:
    result = style.copy()
    result.title.text = current.title.text
    _restore_axis_data(result.x_axis, current.x_axis); _restore_axis_data(result.shared_y_axis, current.shared_y_axis)
    result.curves = []
    for index, curve in enumerate(current.curves):
        result.curves.append(apply_curve_template(curve, templates[index]) if index < len(templates) else deepcopy(curve))
    return result


def sanitize_dataset_template(dataset: CsvDatasetConfig) -> CsvDatasetConfig:
    result = deepcopy(dataset)
    result.dataset_id = ""; result.path = ""; result.label = ""; result.enabled = True
    result.x2d = ""; result.y2d = ""; result.x3d = ""; result.y3d = ""; result.z3d = ""
    result.auto_color_range = True; result.color_min = 0.0; result.color_max = 1.0
    return result


def apply_dataset_template(dataset: CsvDatasetConfig, template: CsvDatasetConfig) -> CsvDatasetConfig:
    result = deepcopy(template)
    for name in ("dataset_id", "path", "label", "enabled", "x2d", "y2d", "x3d", "y3d", "z3d",
                 "auto_color_range", "color_min", "color_max"):
        setattr(result, name, getattr(dataset, name))
    return result


def make_3d_style_payload(config: VtkPlotConfig, datasets=None, templates=None) -> dict:
    clean = deepcopy(config)
    clean.migrate_legacy_axes()
    clean.x_title = "X"; clean.y_title = "Y"; clean.z_title = "Z"
    clean.x_axis.title = "X"; clean.y_axis.title = "Y"; clean.z_axis.title = "Z"
    clean.auto_bounds = True; clean.x_min = 0.0; clean.x_max = 1.0
    clean.y_min = 0.0; clean.y_max = 1.0; clean.z_min = 0.0; clean.z_max = 1.0
    source = list(datasets or []) or list(templates or [])
    vtk_raw = asdict(clean)
    for key in ("x_title", "y_title", "z_title", "text_color", "title_font_size", "label_font_size",
                "auto_bounds", "x_min", "x_max", "y_min", "y_max", "z_min", "z_max"):
        vtk_raw.pop(key, None)
    for key in ("x_axis", "y_axis", "z_axis"): vtk_raw.get(key, {}).pop("title", None)
    return {
        "kind": STYLE_3D_KIND, "version": STYLE_3D_VERSION,
        "vtk": vtk_raw,
        "dataset_templates": [_dataset_template_dict(value) for value in source],
    }


def parse_3d_style_payload(raw: dict) -> tuple[VtkPlotConfig, list[CsvDatasetConfig]]:
    if not isinstance(raw, dict) or raw.get("kind") != STYLE_3D_KIND or raw.get("version") not in (STYLE_VERSION, STYLE_3D_VERSION):
        raise ValueError("This is not a supported MInDes 3D style file.")
    vtk_raw = raw.get("vtk"); template_raw = raw.get("dataset_templates", [])
    if not isinstance(vtk_raw, dict) or not isinstance(template_raw, list):
        raise ValueError("The 3D style file is incomplete.")
    _validate_dataclass_payload(VtkPlotConfig(), vtk_raw, "vtk")
    for index, value in enumerate(template_raw): _validate_dataclass_payload(CsvDatasetConfig(), value, f"dataset_templates[{index}]")
    config = VtkPlotConfig.from_dict(vtk_raw)
    config.x_title = "X"; config.y_title = "Y"; config.z_title = "Z"; config.auto_bounds = True
    config.x_axis.title = "X"; config.y_axis.title = "Y"; config.z_axis.title = "Z"
    config.x_min = 0.0; config.x_max = 1.0; config.y_min = 0.0; config.y_max = 1.0; config.z_min = 0.0; config.z_max = 1.0
    templates = [sanitize_dataset_template(CsvDatasetConfig.from_dict(value)) for value in template_raw if isinstance(value, dict)]
    return config, templates


def apply_3d_visual_style(current: VtkPlotConfig, style: VtkPlotConfig) -> VtkPlotConfig:
    result = deepcopy(style)
    result.x_title = current.x_title; result.y_title = current.y_title; result.z_title = current.z_title
    result.x_axis.title = current.x_axis.title; result.y_axis.title = current.y_axis.title; result.z_axis.title = current.z_axis.title
    result.auto_bounds = current.auto_bounds; result.x_min = current.x_min; result.x_max = current.x_max
    result.y_min = current.y_min; result.y_max = current.y_max; result.z_min = current.z_min; result.z_max = current.z_max
    return result
