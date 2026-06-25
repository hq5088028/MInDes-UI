"""VTK geometry helpers with explicit NaN holes for CSV surfaces."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import vtk


@dataclass
class SurfaceBuildResult:
    polydata: vtk.vtkPolyData | None
    reason: str = ""
    valid_points: int = 0


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
    if axis.format_mode == "Fixed": return f"%.{decimals}f"
    if axis.format_mode == "Scientific": return f"%.{decimals}e"
    return "%g"


def _configure_cube_common(actor, config, bounds, raw_min, raw_max, camera=None):
    actor.SetBounds(*map(float, bounds))
    if camera is not None: actor.SetCamera(camera)
    if hasattr(actor, "SetXAxisRange"):
        actor.SetXAxisRange(float(raw_min[0]), float(raw_max[0])); actor.SetYAxisRange(float(raw_min[1]), float(raw_max[1])); actor.SetZAxisRange(float(raw_min[2]), float(raw_max[2]))
    actor.SetTickLocation({"Inside": actor.VTK_TICKS_INSIDE, "Outside": actor.VTK_TICKS_OUTSIDE, "Both": actor.VTK_TICKS_BOTH}.get(config.tick_location, actor.VTK_TICKS_INSIDE))
    actor.SetFlyMode({"Closest Triad": actor.VTK_FLY_CLOSEST_TRIAD, "Furthest Triad": actor.VTK_FLY_FURTHEST_TRIAD,
                      "Outer Edges": actor.VTK_FLY_OUTER_EDGES, "Static Triad": actor.VTK_FLY_STATIC_TRIAD,
                      "Static Edges": actor.VTK_FLY_STATIC_EDGES}.get(config.fly_mode, actor.VTK_FLY_CLOSEST_TRIAD))
    actor.SetGridLineLocation({"All": actor.VTK_GRID_LINES_ALL, "Closest": actor.VTK_GRID_LINES_CLOSEST,
                               "Furthest": actor.VTK_GRID_LINES_FURTHEST}.get(config.grid_line_location, actor.VTK_GRID_LINES_ALL))
    actor.SetTitleOffset((float(config.title_offset_x), float(config.title_offset_y))); actor.SetLabelOffset(float(config.label_offset)); actor.SetCornerOffset(float(config.corner_offset))
    return actor


def configure_cube_axes(actor, config, bounds, raw_min, raw_max, camera=None):
    """Configure one complete cube actor; layered rendering uses build_cube_axes_bundle."""
    _configure_cube_common(actor, config, bounds, raw_min, raw_max, camera); actor.SetUseTextActor3D(True)
    for index, (name, axis) in enumerate(zip("XYZ", (config.x_axis, config.y_axis, config.z_axis))):
        getattr(actor, f"Set{name}Title")(axis.title if axis.title_visible and axis.axis_visible else "")
        getattr(actor, f"Set{name}AxisVisibility")(bool(axis.axis_visible))
        getattr(actor, f"Set{name}AxisLabelVisibility")(bool(axis.axis_visible and axis.label_visible))
        getattr(actor, f"Set{name}AxisTickVisibility")(bool(axis.axis_visible and axis.major_tick_visible))
        getattr(actor, f"Set{name}AxisMinorTickVisibility")(bool(axis.axis_visible and axis.minor_tick_visible))
        getattr(actor, f"SetDraw{name}Gridlines")(bool(axis.axis_visible and axis.grid_visible))
        getattr(actor, f"Set{name}LabelFormat")(_label_format(axis))
        line = getattr(actor, f"Get{name}AxesLinesProperty")(); line.SetColor(*hex_to_rgb(axis.line_color)); line.SetLineWidth(float(axis.line_width)); line.Modified()
        grid = getattr(actor, f"Get{name}AxesGridlinesProperty")(); grid.SetColor(*hex_to_rgb(axis.grid_color)); grid.SetLineWidth(float(axis.grid_width)); grid.Modified()
        _apply_text_style(actor.GetTitleTextProperty(index), axis.title_style); _apply_text_style(actor.GetLabelTextProperty(index), axis.label_style)
    actor.Modified(); return actor


def _hide_axis_geometry(actor, name):
    line = getattr(actor, f"Get{name}AxesLinesProperty")(); line.SetOpacity(0.0); line.Modified()
    grid = getattr(actor, f"Get{name}AxesGridlinesProperty")(); grid.SetOpacity(0.0); grid.Modified()
    getattr(actor, f"Set{name}AxisTickVisibility")(False); getattr(actor, f"Set{name}AxisMinorTickVisibility")(False)
    getattr(actor, f"SetDraw{name}Gridlines")(False)


def _text_layer(config, bounds, raw_min, raw_max, camera, selected, kind):
    actor = vtk.vtkCubeAxesActor(); _configure_cube_common(actor, config, bounds, raw_min, raw_max, camera)
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
    actor.Modified(); return actor


def build_cube_axes_bundle(config, bounds, raw_min, raw_max, camera=None):
    """Build one geometry actor plus independent title/label text actors for X/Y/Z."""
    base = vtk.vtkCubeAxesActor(); configure_cube_axes(base, config, bounds, raw_min, raw_max, camera)
    base.SetUseTextActor3D(True)
    for name in "XYZ":
        getattr(base, f"Set{name}Title")(""); getattr(base, f"Set{name}AxisLabelVisibility")(False)
    base.Modified()
    labels = {name: _text_layer(config, bounds, raw_min, raw_max, camera, name, "label") for name in "XYZ"}
    titles = {name: _text_layer(config, bounds, raw_min, raw_max, camera, name, "title") for name in "XYZ"}
    return CubeAxesBundle(base, labels, titles)


def aggregate_xy(x: np.ndarray, y: np.ndarray, z: np.ndarray):
    """Collapse duplicate finite X/Y coordinates while preserving all-invalid Z holes."""
    buckets: dict[tuple[float, float], list[float]] = {}
    for xv, yv, zv in zip(x, y, z):
        if not (np.isfinite(xv) and np.isfinite(yv)):
            continue
        buckets.setdefault((float(xv), float(yv)), []).append(float(zv))
    xs, ys, zs = [], [], []
    for (xv, yv), values in buckets.items():
        finite = [v for v in values if np.isfinite(v)]
        xs.append(xv); ys.append(yv); zs.append(float(np.mean(finite)) if finite else np.nan)
    return np.asarray(xs), np.asarray(ys), np.asarray(zs)


def build_surface_with_holes(x, y, z, transform=None) -> SurfaceBuildResult:
    """Delaunay-triangulate X/Y and remove every face incident to an invalid Z vertex."""
    x, y, z = aggregate_xy(np.asarray(x, float), np.asarray(y, float), np.asarray(z, float))
    finite_z = np.isfinite(z)
    if len(x) < 3 or finite_z.sum() < 3:
        return SurfaceBuildResult(None, "fewer than three valid points", int(finite_z.sum()))
    xy = np.column_stack([x, y])
    if np.linalg.matrix_rank(xy - xy.mean(axis=0)) < 2:
        return SurfaceBuildResult(None, "X/Y points are collinear", int(finite_z.sum()))

    display = np.column_stack([x, y, np.where(finite_z, z, 0.0)])
    if transform is not None:
        display = transform(display)

    points = vtk.vtkPoints()
    validity = vtk.vtkUnsignedCharArray(); validity.SetName("csv_valid_z")
    raw_z = vtk.vtkDoubleArray(); raw_z.SetName("csv_z")
    for point, zv, valid in zip(display, z, finite_z):
        points.InsertNextPoint(*map(float, point))
        validity.InsertNextValue(1 if valid else 0)
        raw_z.InsertNextValue(float(zv) if valid else 0.0)

    source = vtk.vtkPolyData(); source.SetPoints(points)
    source.GetPointData().AddArray(validity); source.GetPointData().SetScalars(raw_z)
    delaunay = vtk.vtkDelaunay2D(); delaunay.SetInputData(source); delaunay.Update()
    output = delaunay.GetOutput()
    out_validity = output.GetPointData().GetArray("csv_valid_z")
    if out_validity is None:
        return SurfaceBuildResult(None, "triangulation lost validity metadata", int(finite_z.sum()))

    kept = vtk.vtkCellArray(); ids = vtk.vtkIdList()
    cells = output.GetPolys(); cells.InitTraversal()
    while cells.GetNextCell(ids):
        if ids.GetNumberOfIds() != 3:
            continue
        vertex_ids = [ids.GetId(i) for i in range(3)]
        if all(out_validity.GetTuple1(pid) > 0.5 for pid in vertex_ids):
            kept.InsertNextCell(3)
            for pid in vertex_ids:
                kept.InsertCellPoint(pid)

    if kept.GetNumberOfCells() == 0:
        return SurfaceBuildResult(None, "no valid triangle remains after applying holes", int(finite_z.sum()))
    result = vtk.vtkPolyData(); result.SetPoints(output.GetPoints()); result.SetPolys(kept)
    result.GetPointData().ShallowCopy(output.GetPointData())
    return SurfaceBuildResult(result, "", int(finite_z.sum()))


def build_scatter(x, y, z, transform=None) -> vtk.vtkPolyData:
    x, y, z = map(lambda v: np.asarray(v, float), (x, y, z))
    valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    display = np.column_stack([x[valid], y[valid], z[valid]])
    if transform is not None and len(display):
        display = transform(display)
    points = vtk.vtkPoints(); vertices = vtk.vtkCellArray(); raw_z = vtk.vtkDoubleArray(); raw_z.SetName("csv_z")
    for point, zv in zip(display, z[valid]):
        pid = points.InsertNextPoint(*map(float, point)); vertices.InsertNextCell(1); vertices.InsertCellPoint(pid)
        raw_z.InsertNextValue(float(zv))
    poly = vtk.vtkPolyData(); poly.SetPoints(points); poly.SetVerts(vertices); poly.GetPointData().SetScalars(raw_z)
    return poly


def make_lookup_table(name: str, value_range: tuple[float, float]):
    import matplotlib
    cmap_name = {"grayscale": "gray", "cool-warm": "coolwarm"}.get(name.lower(), name.lower())
    cmap = matplotlib.colormaps.get_cmap(cmap_name if cmap_name in matplotlib.colormaps else "viridis")
    lut = vtk.vtkLookupTable(); lut.SetNumberOfTableValues(256); lut.SetRange(*map(float, value_range))
    for index in range(256):
        r, g, b, a = cmap(index / 255.0); lut.SetTableValue(index, r, g, b, a)
    lut.Build(); return lut


def hex_to_rgb(color: str):
    color = color.lstrip("#")
    if len(color) != 6:
        return 0.0, 0.0, 0.0
    return tuple(int(color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
