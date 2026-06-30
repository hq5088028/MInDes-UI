"""Shared type declarations for VTS viewer mixin classes.

This Protocol declares every cross-mixin attribute so that Pylance
can resolve ``self.xxx`` across mixin boundaries at static-analysis time.

At runtime this module is never imported — the ``TYPE_CHECKING`` guard in
each mixin substitutes ``object`` as the base class.
"""

from __future__ import annotations

from typing import Protocol, Any


class VTSViewerProtocol(Protocol):
    """Every attribute that any VTS mixin accesses via ``self``.

    Because these mixins are only ever combined into
    ``VTSViewerWidget(QWidget, VTKViewMixin, ControlPanelMixin, …)``,
    all of these will exist at runtime.
    """

    # ── VTKViewMixin ──
    vtk_widget: Any
    renderer: Any
    iren: Any
    tab_widget: Any
    plot_tab: Any
    plot_figure: Any
    plot_canvas: Any
    line_table_view: Any
    DEFAULT_COLOR_CYCLE: Any
    _line_styles: Any
    active_line_data: Any
    _last_valid_y_range: Any
    line_widget: Any
    plot_line_p1: Any
    plot_line_p2: Any

    # ── ControlPanelMixin ──
    load_btn: Any
    bg_color_combo: Any
    playback_group: Any
    draw_btns: Any
    play_button: Any
    stop_button: Any
    auto_update_checkbox: Any
    auto_update_interval_combo: Any
    playback_status_label: Any
    file_combo: Any
    refresh_btn: Any
    field_combo: Any
    colormap_combo: Any
    auto_range_checkbox: Any
    min_spin: Any
    max_spin: Any
    colorbar_label: Any
    vis_mode_combo: Any
    clip_group: Any
    clip_axis_combo: Any
    clip_slider: Any
    contour_group: Any
    contour_levels_edit: Any
    glyph_group: Any
    glyph_color_mode_combo: Any
    arrow_color_btn: Any
    glyph_size_mode_combo: Any
    glyph_scale_edit: Any
    opacity_slider: Any
    opacity_value_label: Any
    show_with_boundary_checkbox: Any
    plot_line_checkbox: Any
    line_endpoint_group: Any
    line_style_group: Any
    y_axis_range_group: Any
    p1x: Any
    p1y: Any
    p1z: Any
    p2x: Any
    p2y: Any
    p2z: Any
    auto_y_range_checkbox: Any
    y_min_spin: Any
    y_max_spin: Any
    line_style_layout: Any
    line_visible_checkbox: Any
    display_group: Any
    show_axes_checkbox: Any
    show_bounds_checkbox: Any
    show_colorbar_checkbox: Any
    control_scroll_area: Any
    color_arrows_by_mag_checkbox: Any
    scroll: Any
    set_line_btn: Any
    export_excel_btn: Any
    
    # ── VTSDataLoaderMixin ──
    vts_folder: Any
    vts_prefix: Any
    vts_file_list: Any
    current_file_index: Any
    auto_update_timer: Any
    auto_update_enabled: Any
    sequential_timer: Any
    is_sequential_playing: Any
    frame_buffer: Any
    playback_worker: Any
    stop_playback_event: Any
    _loaded_or_queued_indices: Any
    _loaded_indices_lock: Any
    field_selection: Any
    colormap_selection: Any
    auto_range_enabled: Any
    user_min_val: Any
    user_max_val: Any
    vis_mode: Any
    clip_axis: Any
    clip_position: Any
    contour_levels_text: Any
    default_opacity: Any
    opacity_value: Any
    show_axes: Any
    show_bounds: Any
    show_colorbar: Any
    show_with_boundary: Any
    glyph_enabled: Any
    arrow_color_rgb: Any
    color_arrows_by_mag: Any
    plot_line_enabled: Any
    current_vis_mode: Any
    camera_position: Any
    camera_focal_point: Any
    camera_view_up: Any
    camera_distance: Any
    should_reset_camera_on_load: Any

    # ── VisualizationMixin ──
    current_data: Any
    surface_mapper: Any
    surface_actor: Any
    wire_mapper: Any
    wire_actor: Any
    clipper: Any
    clip_mapper: Any
    clip_actor: Any
    contour_filter: Any
    contour_mapper: Any
    contour_actor: Any
    glyph_arrow_source: Any
    glyph_filter: Any
    glyph_mapper: Any
    glyph_actor: Any
    plane: Any
    lut: Any
    _boundary_extract_filter: Any
    _current_colormap: Any
    _current_lut_range: Any
    _is_surface_render_new: Any
    _is_surface_wire_render_new: Any
    _is_clip_render_new: Any
    _is_contour_render_new: Any
    _cube_axes_actor: Any
    orientation_marker: Any
    _scalar_bar_actor: Any
    arrow_color: Any
    control_panel_width: int

    # ── Cross-mixin methods (declared as Any attrs for Pylance resolution) ──
    update_background_color: Any
    on_file_combo_changed: Any
    start_sequential_playback: Any
    stop_sequential_playback: Any
    toggle_auto_update: Any
    on_glyph_scale_edit_finished: Any
    toggle_range_edit: Any
    on_opacity_slider_changed: Any
    on_field_selection_changed: Any
    update_colormap_preview: Any
    on_vis_mode_changed: Any
    on_clip_axis_changed: Any
    pick_arrow_color: Any
    on_glyph_color_mode_changed: Any
    toggle_plot_over_line: Any
    _load_vts_interactive: Any
    _load_vts_from_folder_or_series: Any
    load_single_vts_file: Any
    load_vts_from_folder: Any
    populate_field_combos: Any
    _reset_series_state: Any
    _update_current_state_snapshot: Any
    refresh_plot_over_line_for_current_data: Any
    update_playback_status: Any
    refresh_file_list: Any
    _update_file_combo: Any
    _extract_series_prefix: Any
    _update_playback_ui_enabled: Any
    update_range_inputs: Any
    _create_lookup_table: Any
    _disable_all_interactive_controls: Any
    update_visualization: Any
    array_magnitude_name: Any
    compute_magnitude_array: Any
    _hide_all_actors_except: Any
    _render_surface_actor: Any
    _render_clip_actor: Any
    _render_contour_actor: Any
    _render_glyph_actor: Any
    _update_text_colors: Any
    _update_line_input_fields: Any
    _rebuild_line_style_controls: Any
    _on_line_visible_changed: Any
    _pick_field_color: Any
    _on_linestyle_changed: Any
    update_plot_and_table: Any
    on_line_changed: Any
    start_plot_over_line: Any
    end_plot_over_line: Any
    _play_next_frame: Any
    _preload_frames_worker: Any
    _create_vtk_and_tabs: Any
    _create_control_panel: Any
    _setup_coolwarm_lut: Any
    _setup_rainbow_lut: Any
    _setup_grayscale_lut: Any
    _setup_viridis_lut: Any
    _setup_plasma_lut: Any
    set_line_from_inputs: Any
    export_line_data: Any
    toggle_y_axis_range: Any
    apply_manual_y_axis_range: Any
    update_axes_visibility: Any
    update_bounds_visibility: Any
    update_colorbar_visibility: Any
    reset_view: Any
    draw_new_vts_files: Any
