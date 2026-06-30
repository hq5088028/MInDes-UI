"""Shared type declarations for VTS viewer mixin classes.

This Protocol declares every cross-mixin attribute so that Pylance
can resolve ``self.xxx`` across mixin boundaries at static-analysis time.

At runtime this module is never imported — the ``TYPE_CHECKING`` guard in
each mixin substitutes ``object`` as the base class.
"""

from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING, Any, Callable, Protocol

if TYPE_CHECKING:
    import vtk
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QGroupBox,
        QVBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QScrollArea,
        QSlider,
        QTabWidget,
        QTableView,
        QWidget,
    )
    from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor


class VTSViewerProtocol(Protocol):
    """Every attribute that any VTS mixin accesses via ``self``.

    Because these mixins are only ever combined into
    ``VTSViewerWidget(QWidget, VTKViewMixin, ControlPanelMixin, …)``,
    all of these will exist at runtime.
    """

    # ── VTKViewMixin ──
    vtk_widget: QVTKRenderWindowInteractor
    renderer: vtk.vtkRenderer
    iren: vtk.vtkRenderWindowInteractor
    tab_widget: QTabWidget
    plot_tab: QWidget
    plot_figure: Figure
    plot_canvas: FigureCanvasQTAgg
    line_table_view: QTableView
    DEFAULT_COLOR_CYCLE: list[tuple[float, float, float]]
    _line_styles: dict[str, dict[str, Any]]
    active_line_data: Any  # pd.DataFrame at runtime, dict for type flexibility
    _last_valid_y_range: tuple[float, float]
    line_widget: vtk.vtkLineWidget | None
    plot_line_p1: list[float] | None
    plot_line_p2: list[float] | None

    # ── ControlPanelMixin ──
    load_btn: QPushButton
    bg_color_combo: QComboBox
    playback_group: QGroupBox
    draw_btns: QPushButton
    play_button: QPushButton
    stop_button: QPushButton
    auto_update_checkbox: QCheckBox
    auto_update_interval_combo: QComboBox
    playback_status_label: QLabel
    file_combo: QComboBox
    refresh_btn: QPushButton
    field_combo: QComboBox
    colormap_combo: QComboBox
    auto_range_checkbox: QCheckBox
    min_spin: QDoubleSpinBox
    max_spin: QDoubleSpinBox
    colorbar_label: QLabel
    vis_mode_combo: QComboBox
    clip_group: QGroupBox
    clip_axis_combo: QComboBox
    clip_slider: QDoubleSpinBox
    contour_group: QGroupBox
    contour_levels_edit: QLineEdit
    glyph_group: QGroupBox
    glyph_color_mode_combo: QComboBox
    arrow_color_btn: QPushButton
    glyph_size_mode_combo: QComboBox
    glyph_scale_edit: QLineEdit
    opacity_slider: QSlider
    opacity_value_label: QLabel
    show_with_boundary_checkbox: QCheckBox
    plot_line_checkbox: QCheckBox
    line_endpoint_group: QGroupBox
    line_style_group: QGroupBox
    y_axis_range_group: QGroupBox
    p1x: QLineEdit
    p1y: QLineEdit
    p1z: QLineEdit
    p2x: QLineEdit
    p2y: QLineEdit
    p2z: QLineEdit
    auto_y_range_checkbox: QCheckBox
    y_min_spin: QDoubleSpinBox
    y_max_spin: QDoubleSpinBox
    line_style_layout: QVBoxLayout
    line_visible_checkbox: QCheckBox
    display_group: QGroupBox
    show_axes_checkbox: QCheckBox
    show_bounds_checkbox: QCheckBox
    show_colorbar_checkbox: QCheckBox
    control_scroll_area: QScrollArea
    color_arrows_by_mag_checkbox: QCheckBox
    scroll: Any  # QScrollArea — conflicts with QWidget.scroll(int,int) method
    set_line_btn: QPushButton
    export_excel_btn: QPushButton

    # ── VTSDataLoaderMixin ──
    vts_folder: str | None
    vts_prefix: str | None
    vts_file_list: list[str]
    current_file_index: int
    auto_update_timer: QTimer | None
    auto_update_enabled: bool
    sequential_timer: QTimer | None
    is_sequential_playing: bool
    frame_buffer: queue.Queue[tuple[int, vtk.vtkStructuredGrid]]
    playback_worker: threading.Thread | None
    stop_playback_event: threading.Event
    _loaded_or_queued_indices: set[int]
    _loaded_indices_lock: threading.Lock
    field_selection: str | None
    colormap_selection: str
    auto_range_enabled: bool
    user_min_val: float
    user_max_val: float
    vis_mode: str
    clip_axis: str
    clip_position: float
    contour_levels_text: str
    default_opacity: float
    opacity_value: float
    show_axes: bool
    show_bounds: bool
    show_colorbar: bool
    show_with_boundary: bool
    glyph_enabled: bool
    arrow_color_rgb: tuple[float, float, float]
    color_arrows_by_mag: bool
    plot_line_enabled: bool
    current_vis_mode: str
    camera_position: tuple[float, float, float] | None
    camera_focal_point: tuple[float, float, float] | None
    camera_view_up: tuple[float, float, float] | None
    camera_distance: float | None
    should_reset_camera_on_load: bool

    # ── VisualizationMixin ──
    current_data: vtk.vtkStructuredGrid | None
    surface_mapper: vtk.vtkDataSetMapper
    surface_actor: vtk.vtkActor
    wire_mapper: vtk.vtkDataSetMapper
    wire_actor: vtk.vtkActor
    clipper: vtk.vtkClipDataSet
    clip_mapper: vtk.vtkDataSetMapper
    clip_actor: vtk.vtkActor
    contour_filter: vtk.vtkContourFilter
    contour_mapper: vtk.vtkPolyDataMapper
    contour_actor: vtk.vtkActor
    glyph_arrow_source: vtk.vtkArrowSource
    glyph_filter: vtk.vtkGlyph3D
    glyph_mapper: vtk.vtkPolyDataMapper
    glyph_actor: vtk.vtkActor
    plane: vtk.vtkPlane
    lut: vtk.vtkLookupTable
    _boundary_extract_filter: vtk.vtkExtractGrid | None
    _current_colormap: str | None
    _current_lut_range: tuple[float, float] | None
    _is_surface_render_new: bool
    _is_surface_wire_render_new: bool
    _is_clip_render_new: bool
    _is_contour_render_new: bool
    _cube_axes_actor: vtk.vtkCubeAxesActor | None
    orientation_marker: vtk.vtkOrientationMarkerWidget | None
    _scalar_bar_actor: vtk.vtkScalarBarActor | None
    arrow_color: tuple[float, float, float]
    control_panel_width: int

    # ── Cross-mixin callbacks ──
    progress_callback: Callable[[str], None] | None
    _report_progress: Callable[..., None]
    update_background_color: Callable[..., None]
    on_file_combo_changed: Callable[..., None]
    start_sequential_playback: Callable[..., None]
    stop_sequential_playback: Callable[..., None]
    toggle_auto_update: Callable[..., None]
    on_glyph_scale_edit_finished: Callable[..., None]
    toggle_range_edit: Callable[..., None]
    on_opacity_slider_changed: Callable[..., None]
    on_field_selection_changed: Callable[..., None]
    update_colormap_preview: Callable[..., None]
    on_vis_mode_changed: Callable[..., None]
    on_clip_axis_changed: Callable[..., None]
    pick_arrow_color: Callable[..., None]
    on_glyph_color_mode_changed: Callable[..., None]
    toggle_plot_over_line: Callable[..., None]
    _load_vts_interactive: Callable[..., None]
    _load_vts_from_folder_or_series: Callable[..., None]
    load_single_vts_file: Callable[..., bool]
    load_vts: Callable[..., None]
    load_vts_from_folder: Callable[..., None]
    populate_field_combos: Callable[..., None]
    _reset_series_state: Callable[..., None]
    _update_current_state_snapshot: Callable[..., None]
    refresh_plot_over_line_for_current_data: Callable[..., None]
    update_playback_status: Callable[..., None]
    refresh_file_list: Callable[..., None]
    _update_file_combo: Callable[..., None]
    _extract_series_prefix: Callable[..., None]
    _update_playback_ui_enabled: Callable[..., None]
    update_range_inputs: Callable[..., None]
    _create_lookup_table: Callable[..., None]
    _disable_all_interactive_controls: Callable[..., None]
    update_visualization: Callable[..., None]
    compute_magnitude_array: Callable[..., Any]  # returns vtkFloatArray | None
    array_magnitude_name: Callable[..., str]
    _hide_all_actors_except: Callable[..., None]
    _render_surface_actor: Callable[..., None]
    _render_clip_actor: Callable[..., None]
    _render_contour_actor: Callable[..., None]
    _render_glyph_actor: Callable[..., None]
    _update_text_colors: Callable[..., None]
    _update_line_input_fields: Callable[..., None]
    _rebuild_line_style_controls: Callable[..., None]
    _on_line_visible_changed: Callable[..., None]
    _pick_field_color: Callable[..., None]
    _on_linestyle_changed: Callable[..., None]
    update_plot_and_table: Callable[..., None]
    on_line_changed: Callable[..., None]
    start_plot_over_line: Callable[..., None]
    end_plot_over_line: Callable[..., None]
    _play_next_frame: Callable[..., None]
    _preload_frames_worker: Callable[..., None]
    _create_vtk_and_tabs: Callable[..., None]
    _create_control_panel: Callable[..., Any]  # returns QScrollArea
    _setup_coolwarm_lut: Callable[..., None]
    _setup_rainbow_lut: Callable[..., None]
    _setup_grayscale_lut: Callable[..., None]
    _setup_viridis_lut: Callable[..., None]
    _setup_plasma_lut: Callable[..., None]
    set_line_from_inputs: Callable[..., None]
    export_line_data: Callable[..., None]
    toggle_y_axis_range: Callable[..., None]
    apply_manual_y_axis_range: Callable[..., None]
    update_axes_visibility: Callable[..., None]
    update_bounds_visibility: Callable[..., None]
    update_colorbar_visibility: Callable[..., None]
    reset_view: Callable[..., None]
    draw_new_vts_files: Callable[..., None]
