"""VTS rendering engine for VTS Plotter."""
from __future__ import annotations

import math

import vtk


def load_vts_file(path: str) -> vtk.vtkStructuredGrid | None:
    """Load a .vts file and return a vtkStructuredGrid."""
    try:
        reader = vtk.vtkXMLStructuredGridReader()
        reader.SetFileName(path)
        reader.Update()
        output = reader.GetOutput()
        if output and output.GetNumberOfPoints() > 0:
            return output
        return None
    except Exception:
        return None


def get_vts_fields(grid: vtk.vtkDataSet) -> list[tuple[str, str, str]]:
    """Return list of (display_name, name, type) for point data arrays."""
    pd = grid.GetPointData()
    fields = []
    for i in range(pd.GetNumberOfArrays()):
        arr = pd.GetArray(i)
        name = arr.GetName()
        if not name:
            continue
        comps = arr.GetNumberOfComponents()
        if comps == 1:
            fields.append((f"[S] {name}", name, "scalar"))
        elif comps == 3:
            fields.append((f"[V] {name}", name, "vector"))
    fields.sort(key=lambda x: (x[2] != "scalar", x[1]))
    return fields


def get_vts_field_names(grid: vtk.vtkDataSet) -> list[str]:
    """Return list of display names for all point data arrays."""
    return [display for display, _, _ in get_vts_fields(grid)]


def _ensure_scalar_field(grid: vtk.vtkDataSet, field_name: str, is_vector: bool) -> tuple[str, bool]:
    """Ensure a scalar array is available for the given field; return (scalar_name, is_magnitude)."""
    if not is_vector:
        return field_name, False
    mag_name = f"{field_name}_magnitude"
    if not grid.GetPointData().HasArray(mag_name):
        vectors = grid.GetPointData().GetArray(field_name)
        if vectors and vectors.GetNumberOfComponents() == 3:
            mag = vtk.vtkFloatArray()
            mag.SetName(mag_name)
            n = vectors.GetNumberOfTuples()
            mag.SetNumberOfValues(n)
            for i in range(n):
                vx, vy, vz = vectors.GetTuple3(i)
                m = math.sqrt(vx * vx + vy * vy + vz * vz)
                mag.SetValue(i, m)
            grid.GetPointData().AddArray(mag)
    return mag_name, True


def _get_field_range(grid: vtk.vtkDataSet, scalar_name: str) -> tuple[float, float]:
    """Get the scalar range for the given array."""
    arr = grid.GetPointData().GetArray(scalar_name)
    if arr:
        return arr.GetRange()
    return (0.0, 1.0)


def apply_data_pipeline(grid: vtk.vtkStructuredGrid, config) -> vtk.vtkDataSet:
    """Apply data processing pipeline: with_boundary -> threshold filter -> subregion extraction.
    Returns processed vtkDataSet."""
    current = grid

    # 1. With Boundary
    if not config.with_boundary:
        if isinstance(current, vtk.vtkStructuredGrid):
            ext = list(current.GetExtent())
            nx = ext[1] - ext[0] + 1
            ny = ext[3] - ext[2] + 1
            nz = ext[5] - ext[4] + 1
            if nx >= 3 and ny >= 3 and nz >= 3:
                extr = vtk.vtkExtractGrid()
                extr.SetInputData(current)
                extr.SetVOI(ext[0] + 1, ext[1] - 1, ext[2] + 1, ext[3] - 1, ext[4] + 1, ext[5] - 1)
                extr.Update()
                if extr.GetOutput().GetNumberOfPoints() > 0:
                    current = extr.GetOutput()

    # 2. Threshold filter
    if config.filter_enabled and config.filter_field:
        thr = vtk.vtkThresholdPoints()
        thr.SetInputData(current)
        thr.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, config.filter_field)
        thr.ThresholdBetween(config.filter_min, config.filter_max)
        thr.Update()
        current = thr.GetOutput()

    # 3. Subregion extraction
    if config.subregion_enabled:
        if not isinstance(current, vtk.vtkStructuredGrid):
            pass
        else:
            voi = vtk.vtkExtractGrid()
            voi.SetInputData(current)
            ext = list(current.GetExtent())
            imin = max(ext[0], config.subregion_imin)
            imax = min(ext[1], config.subregion_imax) if config.subregion_imax >= 0 else ext[1]
            jmin = max(ext[2], config.subregion_jmin)
            jmax = min(ext[3], config.subregion_jmax) if config.subregion_jmax >= 0 else ext[3]
            kmin = max(ext[4], config.subregion_kmin)
            kmax = min(ext[5], config.subregion_kmax) if config.subregion_kmax >= 0 else ext[5]
            if imax > imin and jmax > jmin and kmax >= kmin:
                voi.SetVOI(imin, imax, jmin, jmax, kmin, kmax)
                voi.Update()
                if voi.GetOutput().GetNumberOfPoints() > 0:
                    current = voi.GetOutput()

    return current


def _make_lut(config) -> vtk.vtkLookupTable:
    """Create a vtkLookupTable from the dataset config."""
    from .vtk_utils import make_lookup_table
    return make_lookup_table(config.colormap, (config.color_min, config.color_max))


def _configure_mapper_scalars(mapper, grid, scalar_name, lut):
    """Configure a mapper to use the scalar array and lookup table."""
    mapper.SetInputData(grid)
    mapper.SetScalarModeToUsePointFieldData()
    mapper.SelectColorArray(scalar_name)
    mapper.SetLookupTable(lut)
    mapper.UseLookupTableScalarRangeOn()
    mapper.ScalarVisibilityOn()


def _render_surface(renderer, grid, config, lut):
    """Render surface mode."""
    mapper = vtk.vtkDataSetMapper()
    _configure_mapper_scalars(mapper, grid, config._scalar_name, lut)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetOpacity(config.opacity)
    renderer.AddActor(actor)
    return actor


def _render_surface_with_grid(renderer, grid, config, lut):
    """Render surface with wireframe overlay."""
    # Surface
    mapper = vtk.vtkDataSetMapper()
    _configure_mapper_scalars(mapper, grid, config._scalar_name, lut)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetOpacity(config.opacity)
    renderer.AddActor(actor)

    # Wireframe overlay
    wire_mapper = vtk.vtkDataSetMapper()
    wire_mapper.SetInputData(grid)
    wire_mapper.ScalarVisibilityOff()
    wire_actor = vtk.vtkActor()
    wire_actor.SetMapper(wire_mapper)
    wire_actor.GetProperty().SetRepresentationToWireframe()
    wire_actor.GetProperty().SetColor(*hex_to_rgb(config.mesh_color))
    wire_actor.GetProperty().SetLineWidth(config.mesh_width)
    wire_actor.GetProperty().SetOpacity(min(1.0, config.opacity * 1.2))
    renderer.AddActor(wire_actor)
    return actor


def _render_volume(renderer, grid, config, lut):
    """Render volume mode using vtkSmartVolumeMapper."""
    mapper = vtk.vtkSmartVolumeMapper()
    mapper.SetInputData(grid)

    # Volume property
    prop = vtk.vtkVolumeProperty()
    prop.ShadeOn()
    prop.SetInterpolationTypeToLinear()

    # Opacity transfer function
    otf = vtk.vtkPiecewiseFunction()
    scalar_range = _get_field_range(grid, config._scalar_name)
    rmin, rmax = scalar_range
    mid = (rmin + rmax) / 2.0
    otf.AddPoint(rmin, 0.0)
    otf.AddPoint(rmin + (rmax - rmin) * 0.1, config.opacity * 0.1)
    otf.AddPoint(mid, config.opacity * 0.3)
    otf.AddPoint(rmax - (rmax - rmin) * 0.1, config.opacity * 0.8)
    otf.AddPoint(rmax, config.opacity)
    prop.SetScalarOpacity(otf)

    # Color transfer function - use lut
    ctf = vtk.vtkColorTransferFunction()
    for i in range(256):
        t = rmin + (rmax - rmin) * i / 255.0
        rgb = [0.0, 0.0, 0.0]
        lut.GetColor(t, rgb)
        ctf.AddRGBPoint(t, *rgb)
    prop.SetColor(ctf)

    # Gradient opacity for better boundary definition
    gotf = vtk.vtkPiecewiseFunction()
    gotf.AddPoint(0.0, 0.0)
    gotf.AddPoint(scalar_range[1] * 0.5, 0.5)
    gotf.AddPoint(scalar_range[1], 1.0)
    prop.SetGradientOpacity(gotf)

    volume = vtk.vtkVolume()
    volume.SetMapper(mapper)
    volume.SetProperty(prop)
    renderer.AddVolume(volume)
    return volume


def _render_clip(renderer, grid, config, lut):
    """Render clip mode."""
    bounds = grid.GetBounds()
    position = config.clip_position
    axis = config.clip_axis.lower()

    if axis == "x":
        center = [position, (bounds[2] + bounds[3]) / 2, (bounds[4] + bounds[5]) / 2]
        normal = (1, 0, 0)
    elif axis == "y":
        center = [(bounds[0] + bounds[1]) / 2, position, (bounds[4] + bounds[5]) / 2]
        normal = (0, 1, 0)
    else:
        center = [(bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2, position]
        normal = (0, 0, 1)

    plane = vtk.vtkPlane()
    plane.SetOrigin(*center)
    plane.SetNormal(*normal)

    clipper = vtk.vtkClipDataSet()
    clipper.SetInputData(grid)
    clipper.SetClipFunction(plane)
    clipper.GenerateClipScalarsOff()
    clipper.GenerateClippedOutputOff()
    clipper.Update()

    output = clipper.GetOutput()
    if output.GetNumberOfPoints() == 0:
        return None

    mapper = vtk.vtkDataSetMapper()
    if config.color_mode == "Colormap" and config._scalar_name:
        _configure_mapper_scalars(mapper, output, config._scalar_name, lut)
    else:
        mapper.SetInputData(output)
        mapper.ScalarVisibilityOff()

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    if config.color_mode == "Fixed Color":
        actor.GetProperty().SetColor(*hex_to_rgb(config.color))
    actor.GetProperty().SetOpacity(config.opacity)
    renderer.AddActor(actor)
    return actor


def _render_slice(renderer, grid, config, lut):
    """Render slice mode using vtkCutter."""
    bounds = grid.GetBounds()
    position = config.slice_position
    axis = config.slice_axis.lower()

    if axis == "x":
        normal = (1, 0, 0)
        center_x = position if bounds[0] <= position <= bounds[1] else (bounds[0] + bounds[1]) / 2
        center = [center_x, (bounds[2] + bounds[3]) / 2, (bounds[4] + bounds[5]) / 2]
    elif axis == "y":
        normal = (0, 1, 0)
        center_y = position if bounds[2] <= position <= bounds[3] else (bounds[2] + bounds[3]) / 2
        center = [(bounds[0] + bounds[1]) / 2, center_y, (bounds[4] + bounds[5]) / 2]
    else:
        normal = (0, 0, 1)
        center_z = position if bounds[4] <= position <= bounds[5] else (bounds[4] + bounds[5]) / 2
        center = [(bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2, center_z]

    plane = vtk.vtkPlane()
    plane.SetOrigin(*center)
    plane.SetNormal(*normal)

    cutter = vtk.vtkCutter()
    cutter.SetInputData(grid)
    cutter.SetCutFunction(plane)
    cutter.Update()

    output = cutter.GetOutput()
    if output.GetNumberOfPoints() == 0:
        return None

    mapper = vtk.vtkPolyDataMapper()
    if config.color_mode == "Colormap" and config._scalar_name:
        mapper.SetInputData(output)
        mapper.SetScalarModeToUsePointFieldData()
        mapper.SelectColorArray(config._scalar_name)
        mapper.SetLookupTable(lut)
        mapper.UseLookupTableScalarRangeOn()
        mapper.ScalarVisibilityOn()
    else:
        mapper.SetInputData(output)
        mapper.ScalarVisibilityOff()

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    if config.color_mode == "Fixed Color":
        actor.GetProperty().SetColor(*hex_to_rgb(config.color))
    actor.GetProperty().SetOpacity(config.opacity)
    actor.GetProperty().SetLineWidth(2.0)
    renderer.AddActor(actor)
    return actor


def _render_contour(renderer, grid, config, lut):
    """Render contour / isosurface mode."""
    text = config.contour_levels.strip()
    if not text:
        return None

    try:
        levels = [float(x.strip()) for x in text.split(",") if x.strip()]
    except ValueError:
        return None

    if not levels:
        return None

    contour = vtk.vtkContourFilter()
    contour.SetInputData(grid)
    contour.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, config._scalar_name)
    contour.SetNumberOfContours(0)
    for i, level in enumerate(levels):
        contour.SetValue(i, level)
    contour.Update()

    output = contour.GetOutput()
    if output.GetNumberOfPoints() == 0:
        return None

    mapper = vtk.vtkPolyDataMapper()
    if config.color_mode == "Colormap" and config._scalar_name:
        mapper.SetInputData(output)
        mapper.SetScalarModeToUsePointFieldData()
        mapper.SelectColorArray(config._scalar_name)
        mapper.SetLookupTable(lut)
        mapper.UseLookupTableScalarRangeOn()
        mapper.ScalarVisibilityOn()
    else:
        mapper.SetInputData(output)
        mapper.ScalarVisibilityOff()

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    if config.color_mode == "Fixed Color":
        actor.GetProperty().SetColor(*hex_to_rgb(config.color))
    actor.GetProperty().SetOpacity(config.opacity)
    renderer.AddActor(actor)
    return actor


def _render_vector_arrows(renderer, grid, config, lut):
    """Render vector arrows using vtkGlyph3D."""
    field_name = config._scalar_name
    if not field_name:
        return None

    vectors = grid.GetPointData().GetArray(field_name)
    if not vectors or vectors.GetNumberOfComponents() != 3:
        return None

    # Ensure magnitude array exists
    mag_name = f"{field_name}_magnitude"
    if not grid.GetPointData().HasArray(mag_name):
        n = vectors.GetNumberOfTuples()
        mag = vtk.vtkFloatArray()
        mag.SetName(mag_name)
        mag.SetNumberOfValues(n)
        for i in range(n):
            vx, vy, vz = vectors.GetTuple3(i)
            m = math.sqrt(vx * vx + vy * vy + vz * vz)
            mag.SetValue(i, m)
        grid.GetPointData().AddArray(mag)

    grid.GetPointData().SetActiveVectors(field_name)

    arrow = vtk.vtkArrowSource()
    arrow.SetTipResolution(8)
    arrow.SetShaftResolution(8)
    arrow.SetTipLength(0.3)
    arrow.SetTipRadius(0.1)
    arrow.SetShaftRadius(0.03)

    glyph = vtk.vtkGlyph3D()
    glyph.SetInputData(grid)
    glyph.SetSourceConnection(arrow.GetOutputPort())
    glyph.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, field_name)
    glyph.SetVectorModeToUseVector()
    if config.glyph_size_mode == "Uniform":
        glyph.SetScaleModeToDataScalingOff()
    else:
        glyph.SetScaleModeToScaleByVector()
    glyph.OrientOn()
    glyph.SetScaleFactor(config.glyph_scale_factor)
    glyph.Update()

    output = glyph.GetOutput()
    if output.GetNumberOfPoints() == 0:
        return None

    mapper = vtk.vtkPolyDataMapper()
    if config.glyph_color_mode == "Colormap":
        mapper.SetInputData(output)
        mapper.SetScalarModeToUsePointFieldData()
        mapper.SelectColorArray(mag_name)
        mapper.SetLookupTable(lut)
        mapper.UseLookupTableScalarRangeOn()
        mapper.ScalarVisibilityOn()
    else:
        mapper.SetInputData(output)
        mapper.ScalarVisibilityOff()

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    if config.glyph_color_mode == "Single Color":
        actor.GetProperty().SetColor(*hex_to_rgb(config.color))
    actor.GetProperty().SetOpacity(config.opacity)
    renderer.AddActor(actor)
    return actor


_RENDERERS = {
    "Surface": _render_surface,
    "Surface with Grid": _render_surface_with_grid,
    "Volume": _render_volume,
    "Clip": _render_clip,
    "Slice": _render_slice,
    "Contour": _render_contour,
    "Vector Arrows": _render_vector_arrows,
}


def render_scene(renderer, grid: vtk.vtkDataSet, config, vtk_config) -> list[vtk.vtkProp]:
    """Render one dataset into the scene. Returns list of actors added."""
    from .vtk_utils import make_lookup_table

    # Determine scalar field
    field_display = config.field_name
    if not field_display:
        return []

    is_vector = field_display.startswith("[V] ")
    field_name = field_display[4:] if (field_display.startswith("[S] ") or field_display.startswith("[V] ")) else field_display

    # Ensure scalar array
    if config._scalar_name is None or not grid.GetPointData().HasArray(config._scalar_name):
        scalar_name, _ = _ensure_scalar_field(grid, field_name, is_vector)
        config._scalar_name = scalar_name

    # Update color range
    if config.auto_color_range and config._scalar_name:
        rmin, rmax = _get_field_range(grid, config._scalar_name)
        config.color_min = rmin
        config.color_max = rmax

    # Create lookup table
    lut = make_lookup_table(config.colormap, (config.color_min, config.color_max))

    # Apply data pipeline
    processed = apply_data_pipeline(grid, config)
    if processed.GetNumberOfPoints() == 0:
        return []

    # Render
    render_fn = _RENDERERS.get(config.mode3d, _render_surface)
    result = render_fn(renderer, processed, config, lut)
    return [result] if result else []


def render_all_datasets(renderer, datasets: list, frames: dict, vtk_config, configs: dict):
    """Render all enabled datasets into the scene."""
    renderer.RemoveAllViewProps()

    actors = []
    for dataset in datasets:
        if not dataset.enabled:
            continue
        grid = frames.get(dataset.dataset_id)
        if grid is None:
            continue
        try:
            added = render_scene(renderer, grid, dataset, vtk_config)
            actors.extend(added)
        except Exception:
            continue

    # Add axes
    _add_axes_if_needed(renderer, vtk_config)

    # Add colorbar for active dataset
    _add_colorbar_if_needed(renderer, vtk_config, actors, datasets, configs)

    # Add legend
    _add_legend_if_needed(renderer, vtk_config, actors, datasets)

    renderer.ResetCamera()
    renderer.ResetCameraClippingRange()


def _background_rgb(name: str):
    return {"White": (1, 1, 1), "Light Gray": (.85, .85, .85),
            "Gray": (.5, .5, .5), "Dark Gray": (.2, .2, .2),
            "Black": (0, 0, 0)}.get(name, (1, 1, 1))


def _add_axes_if_needed(renderer, vtk_config):
    """Add cube axes to the scene if configured."""
    from .vtk_utils import build_cube_axes_bundle

    if not vtk_config.show_axes:
        return

    bounds = renderer.ComputeVisiblePropBounds()
    if not bounds or all(abs(v) < 1e-10 for v in bounds):
        return

    raw_min = (bounds[0], bounds[2], bounds[4])
    raw_max = (bounds[1], bounds[3], bounds[5])
    display_max = (bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4])
    display_bounds = (0, display_max[0], 0, display_max[1], 0, display_max[2])

    bundle = build_cube_axes_bundle(vtk_config, display_bounds, raw_min, raw_max, renderer.GetActiveCamera())
    for actor in bundle.actors:
        renderer.AddActor(actor)


def _add_colorbar_if_needed(renderer, vtk_config, actors, datasets, configs):
    """Add scalar bar for the active/first colored dataset."""
    if not vtk_config.show_colorbar or not actors:
        return

    active_id = None
    for ds in datasets:
        if ds.enabled:
            active_id = ds.dataset_id
            break

    if active_id is None:
        return

    ds = next((d for d in datasets if d.dataset_id == active_id), None)
    if ds is None or not ds._scalar_name:
        return

    from .vtk_utils import make_lookup_table
    lut = make_lookup_table(ds.colormap, (ds.color_min, ds.color_max))

    bar = vtk.vtkScalarBarActor()
    bar.SetLookupTable(lut)
    bar.SetTitle(ds.field_name or ds.label)
    bar.SetNumberOfLabels(5)
    bar.SetLabelFormat("%.3g")
    bar.SetPosition(.86, .15)
    bar.SetWidth(.1)
    bar.SetHeight(.7)

    color = hex_to_rgb(vtk_config.x_axis.label_style.color)
    bar.GetTitleTextProperty().SetColor(*color)
    bar.GetLabelTextProperty().SetColor(*color)
    renderer.AddActor2D(bar)


def _add_legend_if_needed(renderer, vtk_config, actors, datasets):
    """Add a legend for each dataset."""
    if not vtk_config.show_legend or not actors:
        return

    enabled = [d for d in datasets if d.enabled]
    if not enabled:
        return

    legend = vtk.vtkLegendBoxActor()
    legend.SetNumberOfEntries(len(enabled))
    legend.SetPosition(.02, .02)
    legend.SetWidth(.22)
    legend.SetHeight(min(.35, .06 * len(enabled) + .05))

    sphere = vtk.vtkSphereSource()
    sphere.Update()

    for index, ds in enumerate(enabled):
        legend.SetEntry(index, sphere.GetOutput(), ds.label or ds.field_name or Path(ds.path).stem, hex_to_rgb(ds.color))

    legend.GetEntryTextProperty().SetColor(*hex_to_rgb("#000000"))
    renderer.AddActor2D(legend)


def hex_to_rgb(color: str):
    color = color.lstrip("#")
    if len(color) != 6:
        return 0.0, 0.0, 0.0
    return tuple(int(color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def reset_view(renderer, vtk_widget, axis=None):
    """Reset camera to view from a specific axis, or reset to default."""
    if axis is None:
        renderer.ResetCamera()
        renderer.ResetCameraClippingRange()
        vtk_widget.GetRenderWindow().Render()
        return

    bounds = renderer.ComputeVisiblePropBounds()
    center = [(bounds[i * 2] + bounds[i * 2 + 1]) / 2 for i in range(3)]
    distance = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4], 1) * 2.5
    camera = renderer.GetActiveCamera()
    camera.SetFocalPoint(*center)

    axis = axis.upper()
    if axis == "X":
        camera.SetPosition(center[0] + distance, center[1], center[2])
        camera.SetViewUp(0, 0, 1)
    elif axis == "Y":
        camera.SetPosition(center[0], center[1] + distance, center[2])
        camera.SetViewUp(0, 0, 1)
    else:
        camera.SetPosition(center[0], center[1], center[2] + distance)
        camera.SetViewUp(0, 1, 0)

    renderer.ResetCameraClippingRange()
    vtk_widget.GetRenderWindow().Render()


from pathlib import Path
