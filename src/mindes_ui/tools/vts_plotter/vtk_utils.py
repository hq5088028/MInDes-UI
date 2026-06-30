"""VTK geometry helpers for VTS Plotter."""
from __future__ import annotations

from dataclasses import dataclass

import vtk


@dataclass
class CubeAxesBundle:
    base: vtk.vtkCubeAxesActor
    labels: dict[str, vtk.vtkCubeAxesActor]
    titles: dict[str, vtk.vtkCubeAxesActor]

    @property
    def actors(self):
        return [self.base, *(self.labels[name] for name in "XYZ"), *(self.titles[name] for name in "XYZ")]


def _apply_text_style(prop, style):
    family = {"Arial": prop.SetFontFamilyToArial, "Courier": prop.SetFontFamilyToCourier,
              "Times": prop.SetFontFamilyToTimes}.get(style.font, prop.SetFontFamilyToArial)
    family(); prop.SetFontSize(int(style.size)); prop.SetBold(bool(style.bold)); prop.SetItalic(bool(style.italic))
    prop.SetShadow(False); prop.SetColor(*hex_to_rgb(style.color)); prop.Modified()


def _label_format(axis):
    decimals = max(0, min(12, int(axis.decimals)))
    if axis.format_mode == "Fixed":
        return f"%.{decimals}f"
    if axis.format_mode == "Scientific":
        return f"%.{decimals}e"
    return "%g"


def _configure_cube_common(actor, config, bounds, raw_min, raw_max, camera=None):
    actor.SetBounds(*map(float, bounds))
    if camera is not None:
        actor.SetCamera(camera)
    if hasattr(actor, "SetXAxisRange"):
        actor.SetXAxisRange(float(raw_min[0]), float(raw_max[0]))
        actor.SetYAxisRange(float(raw_min[1]), float(raw_max[1]))
        actor.SetZAxisRange(float(raw_min[2]), float(raw_max[2]))
    actor.SetTickLocation({"Inside": actor.VTK_TICKS_INSIDE, "Outside": actor.VTK_TICKS_OUTSIDE,
                          "Both": actor.VTK_TICKS_BOTH}.get(config.tick_location, actor.VTK_TICKS_INSIDE))
    actor.SetFlyMode({"Closest Triad": actor.VTK_FLY_CLOSEST_TRIAD, "Furthest Triad": actor.VTK_FLY_FURTHEST_TRIAD,
                      "Outer Edges": actor.VTK_FLY_OUTER_EDGES, "Static Triad": actor.VTK_FLY_STATIC_TRIAD,
                      "Static Edges": actor.VTK_FLY_STATIC_EDGES}.get(config.fly_mode, actor.VTK_FLY_CLOSEST_TRIAD))
    actor.SetGridLineLocation({"All": actor.VTK_GRID_LINES_ALL, "Closest": actor.VTK_GRID_LINES_CLOSEST,
                               "Furthest": actor.VTK_GRID_LINES_FURTHEST}.get(config.grid_line_location, actor.VTK_GRID_LINES_ALL))
    actor.SetTitleOffset((float(config.title_offset_x), float(config.title_offset_y)))
    actor.SetLabelOffset(float(config.label_offset))
    actor.SetCornerOffset(float(config.corner_offset))
    return actor


def configure_cube_axes(actor, config, bounds, raw_min, raw_max, camera=None):
    _configure_cube_common(actor, config, bounds, raw_min, raw_max, camera)
    actor.SetUseTextActor3D(True)
    for index, (name, axis) in enumerate(zip("XYZ", (config.x_axis, config.y_axis, config.z_axis))):
        getattr(actor, f"Set{name}Title")(axis.title if axis.title_visible and axis.axis_visible else "")
        getattr(actor, f"Set{name}AxisVisibility")(bool(axis.axis_visible))
        getattr(actor, f"Set{name}AxisLabelVisibility")(bool(axis.axis_visible and axis.label_visible))
        getattr(actor, f"Set{name}AxisTickVisibility")(bool(axis.axis_visible and axis.major_tick_visible))
        getattr(actor, f"Set{name}AxisMinorTickVisibility")(bool(axis.axis_visible and axis.minor_tick_visible))
        getattr(actor, f"SetDraw{name}Gridlines")(bool(axis.axis_visible and axis.grid_visible))
        getattr(actor, f"Set{name}LabelFormat")(_label_format(axis))
        line = getattr(actor, f"Get{name}AxesLinesProperty")()
        line.SetColor(*hex_to_rgb(axis.line_color))
        line.SetLineWidth(float(axis.line_width))
        line.Modified()
        grid = getattr(actor, f"Get{name}AxesGridlinesProperty")()
        grid.SetColor(*hex_to_rgb(axis.grid_color))
        grid.SetLineWidth(float(axis.grid_width))
        grid.Modified()
        _apply_text_style(actor.GetTitleTextProperty(index), axis.title_style)
        _apply_text_style(actor.GetLabelTextProperty(index), axis.label_style)
    actor.Modified()
    return actor


def _hide_axis_geometry(actor, name):
    line = getattr(actor, f"Get{name}AxesLinesProperty")()
    line.SetOpacity(0.0); line.Modified()
    grid = getattr(actor, f"Get{name}AxesGridlinesProperty")()
    grid.SetOpacity(0.0); grid.Modified()
    getattr(actor, f"Set{name}AxisTickVisibility")(False)
    getattr(actor, f"Set{name}AxisMinorTickVisibility")(False)
    getattr(actor, f"SetDraw{name}Gridlines")(False)


def _text_layer(config, bounds, raw_min, raw_max, camera, selected, kind):
    actor = vtk.vtkCubeAxesActor()
    _configure_cube_common(actor, config, bounds, raw_min, raw_max, camera)
    actor.SetUseTextActor3D(True)
    selected_axis = (config.x_axis, config.y_axis, config.z_axis)["XYZ".index(selected)]
    style = selected_axis.title_style if kind == "title" else selected_axis.label_style
    actor.SetScreenSize(float(style.size))
    for index, (name, axis) in enumerate(zip("XYZ", (config.x_axis, config.y_axis, config.z_axis))):
        selected_visible = name == selected and axis.axis_visible and (axis.title_visible if kind == "title" else axis.label_visible)
        getattr(actor, f"Set{name}AxisVisibility")(bool(selected_visible))
        getattr(actor, f"Set{name}Title")(axis.title if selected_visible and kind == "title" else "")
        getattr(actor, f"Set{name}AxisLabelVisibility")(bool(selected_visible and kind == "label"))
        getattr(actor, f"Set{name}LabelFormat")(_label_format(axis))
        _hide_axis_geometry(actor, name)
        _apply_text_style(actor.GetTitleTextProperty(index), axis.title_style)
        _apply_text_style(actor.GetLabelTextProperty(index), axis.label_style)
    actor.Modified()
    return actor


def build_cube_axes_bundle(config, bounds, raw_min, raw_max, camera=None):
    base = vtk.vtkCubeAxesActor()
    configure_cube_axes(base, config, bounds, raw_min, raw_max, camera)
    base.SetUseTextActor3D(True)
    for name in "XYZ":
        getattr(base, f"Set{name}Title")("")
        getattr(base, f"Set{name}AxisLabelVisibility")(False)
    base.Modified()
    labels = {name: _text_layer(config, bounds, raw_min, raw_max, camera, name, "label") for name in "XYZ"}
    titles = {name: _text_layer(config, bounds, raw_min, raw_max, camera, name, "title") for name in "XYZ"}
    return CubeAxesBundle(base, labels, titles)


def make_lookup_table(name: str, value_range: tuple[float, float]):
    import matplotlib
    cmap_name = {"cool-warm": "coolwarm", "cool_warm": "coolwarm"}.get(name.lower().replace(" ", "_"), name.lower().replace(" ", "_"))
    try:
        cmap = matplotlib.colormaps.get_cmap(cmap_name)
    except ValueError:
        cmap = matplotlib.colormaps.get_cmap("viridis")
    lut = vtk.vtkLookupTable()
    lut.SetNumberOfTableValues(256)
    lut.SetRange(*map(float, value_range))
    for index in range(256):
        r, g, b, a = cmap(index / 255.0)
        lut.SetTableValue(index, r, g, b, a)
    lut.Build()
    return lut


def hex_to_rgb(color: str):
    color = color.lstrip("#")
    if len(color) != 6:
        return 0.0, 0.0, 0.0
    return tuple(int(color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
