"""Versioned visual style formats for VTS Plotter."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass

from .models import VtsDatasetConfig, VtkPlotConfig


STYLE_VERSION = 2
STYLE_3D_KIND = "MInDes VTS Plotter 3D Style"


def _validate_dataclass_payload(model, raw, label):
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object.")
    for key, value in raw.items():
        if not hasattr(model, key):
            continue
        expected = getattr(model, key)
        if is_dataclass(expected):
            _validate_dataclass_payload(expected, value, f"{label}.{key}")
        elif isinstance(expected, bool):
            if not isinstance(value, bool):
                raise ValueError(f"{label}.{key} has an invalid type.")
        elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{label}.{key} has an invalid type.")
        elif isinstance(expected, str):
            if not isinstance(value, str):
                raise ValueError(f"{label}.{key} has an invalid type.")
        elif isinstance(expected, list) and not isinstance(value, list):
            raise ValueError(f"{label}.{key} has an invalid type.")


def sanitize_dataset_template(dataset: VtsDatasetConfig) -> VtsDatasetConfig:
    result = deepcopy(dataset)
    result.dataset_id = ""
    result.path = ""
    result.label = ""
    result.enabled = True
    result.field_name = ""
    result.auto_color_range = True
    result.color_min = 0.0
    result.color_max = 1.0
    result.filter_enabled = False
    result.filter_field = ""
    result.filter_min = 0.0
    result.filter_max = 1.0
    result.subregion_enabled = False
    return result


def apply_dataset_template(dataset: VtsDatasetConfig, template: VtsDatasetConfig) -> VtsDatasetConfig:
    result = deepcopy(template)
    for name in ("dataset_id", "path", "label", "enabled", "field_name",
                 "auto_color_range", "color_min", "color_max",
                 "filter_enabled", "filter_field", "filter_min", "filter_max",
                 "subregion_enabled"):
        setattr(result, name, getattr(dataset, name))
    return result


def _dataset_template_dict(dataset: VtsDatasetConfig) -> dict:
    raw = asdict(sanitize_dataset_template(dataset))
    for key in ("dataset_id", "path", "label", "enabled", "field_name",
                "auto_color_range", "color_min", "color_max",
                "filter_enabled", "filter_field", "filter_min", "filter_max",
                "subregion_enabled"):
        raw.pop(key, None)
    return raw


def make_3d_style_payload(config: VtkPlotConfig, datasets=None, templates=None) -> dict:
    clean = deepcopy(config)
    clean.migrate_legacy_axes()
    clean.x_title = "X"
    clean.y_title = "Y"
    clean.z_title = "Z"
    clean.x_axis.title = "X"
    clean.y_axis.title = "Y"
    clean.z_axis.title = "Z"
    clean.auto_bounds = True
    clean.x_min = 0.0
    clean.x_max = 1.0
    clean.y_min = 0.0
    clean.y_max = 1.0
    clean.z_min = 0.0
    clean.z_max = 1.0
    source = list(datasets or []) or list(templates or [])
    vtk_raw = asdict(clean)
    for key in ("x_title", "y_title", "z_title", "text_color", "title_font_size", "label_font_size",
                "auto_bounds", "x_min", "x_max", "y_min", "y_max", "z_min", "z_max"):
        vtk_raw.pop(key, None)
    for key in ("x_axis", "y_axis", "z_axis"):
        vtk_raw.get(key, {}).pop("title", None)
    return {
        "kind": STYLE_3D_KIND,
        "version": STYLE_VERSION,
        "vtk": vtk_raw,
        "dataset_templates": [_dataset_template_dict(value) for value in source],
    }


def parse_3d_style_payload(raw: dict) -> tuple[VtkPlotConfig, list[VtsDatasetConfig]]:
    if not isinstance(raw, dict) or raw.get("kind") != STYLE_3D_KIND or raw.get("version") != STYLE_VERSION:
        raise ValueError("This is not a supported MInDes VTS 3D style file.")
    vtk_raw = raw.get("vtk")
    template_raw = raw.get("dataset_templates", [])
    if not isinstance(vtk_raw, dict) or not isinstance(template_raw, list):
        raise ValueError("The 3D style file is incomplete.")
    _validate_dataclass_payload(VtkPlotConfig(), vtk_raw, "vtk")
    for index, value in enumerate(template_raw):
        _validate_dataclass_payload(VtsDatasetConfig(), value, f"dataset_templates[{index}]")
    config = VtkPlotConfig.from_dict(vtk_raw)
    config.x_title = "X"
    config.y_title = "Y"
    config.z_title = "Z"
    config.auto_bounds = True
    config.x_axis.title = "X"
    config.y_axis.title = "Y"
    config.z_axis.title = "Z"
    config.x_min = 0.0
    config.x_max = 1.0
    config.y_min = 0.0
    config.y_max = 1.0
    config.z_min = 0.0
    config.z_max = 1.0
    templates = [sanitize_dataset_template(VtsDatasetConfig.from_dict(value))
                 for value in template_raw if isinstance(value, dict)]
    return config, templates


def apply_3d_visual_style(current: VtkPlotConfig, style: VtkPlotConfig) -> VtkPlotConfig:
    result = deepcopy(style)
    result.x_title = current.x_title
    result.y_title = current.y_title
    result.z_title = current.z_title
    result.x_axis.title = current.x_axis.title
    result.y_axis.title = current.y_axis.title
    result.z_axis.title = current.z_axis.title
    result.auto_bounds = current.auto_bounds
    result.x_min = current.x_min
    result.x_max = current.x_max
    result.y_min = current.y_min
    result.y_max = current.y_max
    result.z_min = current.z_min
    result.z_max = current.z_max
    return result
