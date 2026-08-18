"""Property dialog for VTS Plotter's 3D view."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from ...i18n import add_combo_items, combo_value, set_combo_value, tr
from ...plot_property_dialog import ColorButton

from .models import dataset_display_name


class VtkFontStyleEditor(QGroupBox):
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        form = QFormLayout(self)
        self.family = QComboBox()
        self.family.addItems(["Arial", "Courier", "Times"])
        self.font_size = QSpinBox()
        self.font_size.setRange(6, 96)
        self.font_size.setSuffix(" px")
        self.bold = QCheckBox(tr("common.bold"))
        self.italic = QCheckBox(tr("common.italic"))
        self.color = ColorButton("#000000")
        flags = QHBoxLayout()
        flags.addWidget(self.bold)
        flags.addWidget(self.italic)
        flags.addStretch()
        form.addRow(tr("property.font"), self.family)
        form.addRow(tr("common.size"), self.font_size)
        form.addRow(tr("common.style"), flags)
        form.addRow(tr("common.color"), self.color)

    def load(self, style):
        self.family.setCurrentText(style.font)
        self.font_size.setValue(style.size)
        self.bold.setChecked(style.bold)
        self.italic.setChecked(style.italic)
        self.color.set_color(style.color)

    def save(self, style):
        style.font = self.family.currentText()
        style.size = self.font_size.value()
        style.bold = self.bold.isChecked()
        style.italic = self.italic.isChecked()
        style.color = self.color.color()


class VtsPropertyDialog(QDialog):
    def __init__(
        self,
        vtk_config,
        datasets,
        render_order,
        active_id,
        apply_callback,
        parent=None,
        *,
        save_format_callback=None,
        load_format_callback=None,
        style_templates=None,
        field_options=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("property.3d.title"))
        self.resize(820, 800)
        self.config = deepcopy(vtk_config)
        self.config.migrate_legacy_axes()
        self.datasets = {item.dataset_id: deepcopy(item) for item in datasets}
        self.render_order = [value for value in render_order if value in self.datasets]
        self.render_order += [
            value for value in self.datasets if value not in self.render_order
        ]
        self.active_id = (
            active_id
            if active_id in self.datasets
            else (self.render_order[0] if self.render_order else "")
        )
        self.apply_callback = apply_callback
        self._loading = False
        self._axis_index = 0
        self.save_format_callback = save_format_callback
        self.load_format_callback = load_format_callback
        self.style_templates = list(deepcopy(style_templates or []))
        self._field_options = field_options or []

        root = QVBoxLayout(self)
        self._tabs = QTabWidget()
        root.addWidget(self._tabs, 1)
        self._dataset_page = self._build_dataset_page()
        self._scene_page = self._build_scene_page()
        self._axes_page = self._build_axes_page()
        self._tabs.addTab(self._dataset_page, tr("property.tab.dataset"))
        self._tabs.addTab(self._scene_page, tr("property.tab.scene"))
        self._tabs.addTab(self._axes_page, tr("property.tab.axes"))

        buttons = QHBoxLayout()
        root.addLayout(buttons)
        save_btn = QPushButton(tr("property.save_format"))
        load_btn = QPushButton(tr("property.load_format"))
        buttons.addWidget(save_btn)
        buttons.addWidget(load_btn)
        buttons.addStretch()
        apply_btn = QPushButton(tr("common.apply"))
        ok_btn = QPushButton(tr("common.ok"))
        cancel_btn = QPushButton(tr("common.cancel"))
        buttons.addWidget(apply_btn)
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        apply_btn.clicked.connect(self._apply)
        ok_btn.clicked.connect(self._accept)
        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self._save_format)
        load_btn.clicked.connect(self._load_format)
        save_btn.setEnabled(self.save_format_callback is not None)
        load_btn.setEnabled(self.load_format_callback is not None)
        self._load_common()
        self._rebuild_selector(self.active_id)

    @staticmethod
    def _double(minimum=-1e12, maximum=1e12, decimals=6):
        w = QDoubleSpinBox()
        w.setRange(minimum, maximum)
        w.setDecimals(decimals)
        w.setKeyboardTracking(False)
        return w

    @staticmethod
    def _int_spin(minimum=0, maximum=10000):
        w = QSpinBox()
        w.setRange(minimum, maximum)
        w.setKeyboardTracking(False)
        return w

    def _build_dataset_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        self._dataset_scroll = QScrollArea()
        self._dataset_scroll.setWidgetResizable(True)
        outer.addWidget(self._dataset_scroll)
        self._dataset_content = QWidget()
        layout = QVBoxLayout(self._dataset_content)
        self._dataset_scroll.setWidget(self._dataset_content)

        # Top bar
        top = QHBoxLayout()
        layout.addLayout(top)
        self.dataset_combo = QComboBox()
        self.position_label = QLabel()
        self.up_btn = QPushButton(tr("dataset.move_up"))
        self.down_btn = QPushButton(tr("dataset.move_down"))
        top.addWidget(QLabel(tr("property.active_dataset")))
        top.addWidget(self.dataset_combo, 1)
        top.addWidget(self.position_label)
        top.addWidget(self.up_btn)
        top.addWidget(self.down_btn)

        form = QFormLayout()
        layout.addLayout(form)

        self.mode = QComboBox()
        add_combo_items(self.mode, [("choice.surface", "Surface"), ("choice.surface_grid", "Surface with Grid"), ("choice.volume", "Volume"), ("choice.clip", "Clip"), ("choice.slice", "Slice"), ("choice.contour", "Contour"), ("choice.vector_arrows", "Vector Arrows")])
        self.color_mode = QComboBox()
        add_combo_items(self.color_mode, [("choice.colormap", "Colormap"), ("choice.fixed_color", "Fixed Color")])
        self.color = ColorButton("#1f77b4")
        self.cmap = QComboBox()
        add_combo_items(self.cmap, [("choice.cool_warm", "Cool-Warm"), ("choice.viridis", "Viridis"), ("choice.plasma", "Plasma"), ("choice.rainbow", "Rainbow"), ("choice.grayscale", "Grayscale")])
        self.auto_range = QCheckBox(tr("common.auto"))
        self.range_min = self._double()
        self.range_max = self._double()
        self.opacity = self._double(0, 1, 2)
        self.point_size = self._double(1, 30, 1)
        self.mesh_color = ColorButton("#202020")
        self.mesh_width = self._double(0.1, 10, 2)

        for label, widget in [
            (tr("property.dataset.mode"), self.mode),
            (tr("property.dataset.color_mode"), self.color_mode),
            (tr("property.dataset.fixed_color"), self.color),
            (tr("property.dataset.colormap"), self.cmap),
            (tr("property.auto_color_range"), self.auto_range),
            (tr("common.min"), self.range_min),
            (tr("common.max"), self.range_max),
            (tr("common.opacity"), self.opacity),
            (tr("property.dataset.point_size"), self.point_size),
            (tr("property.dataset.mesh_color"), self.mesh_color),
            (tr("property.dataset.mesh_width"), self.mesh_width),
        ]:
            form.addRow(label, widget)

        # Mode-specific groups
        self._clip_group = self._make_clip_group()
        layout.addWidget(self._clip_group)
        self._slice_group = self._make_slice_group()
        layout.addWidget(self._slice_group)
        self._contour_group = self._make_contour_group()
        layout.addWidget(self._contour_group)
        self._glyph_group = self._make_glyph_group()
        layout.addWidget(self._glyph_group)

        # Filter group
        filter_group = QGroupBox(tr("property.data_filter"))
        filter_form = QFormLayout(filter_group)
        self.filter_enabled = QCheckBox(tr("property.filter.enable"))
        filter_form.addRow(self.filter_enabled)
        self.filter_field = QComboBox()
        self.filter_field.addItems([""] + self._field_options)
        self.filter_min = self._double()
        self.filter_max = self._double()
        filter_form.addRow(tr("property.filter.field"), self.filter_field)
        filter_form.addRow(tr("common.min"), self.filter_min)
        filter_form.addRow(tr("common.max"), self.filter_max)
        filter_form.addRow(
            QLabel(tr("property.filter.hint"))
        )
        layout.addWidget(filter_group)

        # Subregion group
        sub_group = QGroupBox(tr("property.subregion"))
        sub_form = QFormLayout(sub_group)
        self.sub_enabled = QCheckBox(tr("property.subregion.enable"))
        sub_form.addRow(self.sub_enabled)
        self.sub_imin = self._int_spin(0, 100000)
        self.sub_imax = self._int_spin(0, 100000)
        self.sub_jmin = self._int_spin(0, 100000)
        self.sub_jmax = self._int_spin(0, 100000)
        self.sub_kmin = self._int_spin(0, 100000)
        self.sub_kmax = self._int_spin(0, 100000)
        sub_form.addRow(tr("property.i_range"), self._hbox(self.sub_imin, self.sub_imax))
        sub_form.addRow(tr("property.j_range"), self._hbox(self.sub_jmin, self.sub_jmax))
        sub_form.addRow(tr("property.k_range"), self._hbox(self.sub_kmin, self.sub_kmax))
        sub_form.addRow(
            QLabel(tr("property.subregion.hint"))
        )
        layout.addWidget(sub_group)

        # With boundary
        self.with_boundary = QCheckBox(tr("property.with_boundary"))
        self.with_boundary.setChecked(True)
        layout.addWidget(self.with_boundary)

        self.dataset_controls = [
            self.mode,
            self.color_mode,
            self.color,
            self.cmap,
            self.auto_range,
            self.range_min,
            self.range_max,
            self.opacity,
            self.point_size,
            self.mesh_color,
            self.mesh_width,
        ]
        self.dataset_combo.currentIndexChanged.connect(self._switch_dataset)
        self.up_btn.clicked.connect(lambda: self._move_dataset(-1))
        self.down_btn.clicked.connect(lambda: self._move_dataset(1))
        self.mode.currentIndexChanged.connect(self._on_mode_changed)
        layout.addStretch()
        return page

    def _hbox(self, *widgets):
        box = QHBoxLayout()
        for w in widgets:
            box.addWidget(w)
        return box

    def _make_clip_group(self):
        g = QGroupBox(tr("choice.clip"))
        f = QFormLayout(g)
        self.clip_axis = QComboBox()
        self.clip_axis.addItems(["X", "Y", "Z"])
        self.clip_position = self._double()
        f.addRow(tr("common.axis"), self.clip_axis)
        f.addRow(tr("common.position"), self.clip_position)
        g.setVisible(False)
        return g

    def _make_slice_group(self):
        g = QGroupBox(tr("choice.slice"))
        f = QFormLayout(g)
        self.slice_axis = QComboBox()
        self.slice_axis.addItems(["X", "Y", "Z"])
        self.slice_position = self._double()
        f.addRow(tr("common.axis"), self.slice_axis)
        f.addRow(tr("common.position"), self.slice_position)
        g.setVisible(False)
        return g

    def _make_contour_group(self):
        g = QGroupBox(tr("choice.contour"))
        f = QFormLayout(g)
        self.contour_levels = QLineEdit()
        self.contour_levels.setPlaceholderText(tr("property.levels.placeholder"))
        f.addRow(tr("property.levels"), self.contour_levels)
        g.setVisible(False)
        return g

    def _make_glyph_group(self):
        g = QGroupBox(tr("choice.vector_arrows"))
        f = QFormLayout(g)
        self.glyph_color_mode = QComboBox()
        add_combo_items(self.glyph_color_mode, [("choice.single_color", "Single Color"), ("choice.colormap", "Colormap")])
        self.glyph_size_mode = QComboBox()
        add_combo_items(self.glyph_size_mode, [("choice.magnitude", "Magnitude"), ("choice.uniform", "Uniform")])
        self.glyph_scale = self._double(0.001, 1000, 3)
        f.addRow(tr("property.dataset.color_mode"), self.glyph_color_mode)
        f.addRow(tr("property.size_mode"), self.glyph_size_mode)
        f.addRow(tr("property.scale_factor"), self.glyph_scale)
        g.setVisible(False)
        return g

    def _on_mode_changed(self, _index=None):
        mode = combo_value(self.mode)
        self._clip_group.setVisible(mode == "Clip")
        self._slice_group.setVisible(mode == "Slice")
        self._contour_group.setVisible(mode == "Contour")
        self._glyph_group.setVisible(mode == "Vector Arrows")

    def _build_scene_page(self):
        page = QWidget()
        form = QFormLayout(page)
        self.background = QComboBox()
        add_combo_items(self.background, [("choice.white", "White"), ("choice.light_gray", "Light Gray"), ("choice.gray", "Gray"), ("choice.dark_gray", "Dark Gray"), ("choice.black", "Black")])
        self.show_colorbar = QCheckBox(tr("property.show_colorbar"))
        self.show_legend = QCheckBox(tr("property.show_legend"))
        self.auto_normalize = QCheckBox(tr("property.normalize_union"))
        self.x_scale = self._double(0.001, 1000, 3)
        self.y_scale = self._double(0.001, 1000, 3)
        self.z_scale = self._double(0.001, 1000, 3)
        self.screenshot_scale = QSpinBox()
        self.screenshot_scale.setRange(1, 8)
        for label, widget in [
            (tr("common.background"), self.background),
            (tr("property.scene.colorbar"), self.show_colorbar),
            (tr("property.scene.legend"), self.show_legend),
            (tr("property.scene.normalize"), self.auto_normalize),
            (tr("property.scene.x_factor"), self.x_scale),
            (tr("property.scene.y_factor"), self.y_scale),
            (tr("property.scene.z_factor"), self.z_scale),
            (tr("property.scene.screenshot_scale"), self.screenshot_scale),
        ]:
            form.addRow(label, widget)
        return page

    def _build_axes_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        self._axes_scroll = QScrollArea()
        self._axes_scroll.setWidgetResizable(True)
        outer.addWidget(self._axes_scroll)
        self._axes_content = QWidget()
        layout = QVBoxLayout(self._axes_content)
        self._axes_scroll.setWidget(self._axes_content)

        selector = QHBoxLayout()
        layout.addLayout(selector)
        self.show_axes = QCheckBox(tr("property.axes.show"))
        self.axis_combo = QComboBox()
        self.axis_combo.addItems([tr("property.axes.x"), tr("property.axes.y"), tr("property.axes.z")])
        selector.addWidget(self.show_axes)
        selector.addStretch()
        selector.addWidget(QLabel(tr("common.axis")))
        selector.addWidget(self.axis_combo)

        vis = QGroupBox(tr("property.axes.visibility"))
        f = QFormLayout(vis)
        self.axis_visible = QCheckBox(tr("property.axes.show_axis"))
        self.title_visible = QCheckBox(tr("property.axes.show_title"))
        self.label_visible = QCheckBox(tr("property.axes.show_labels"))
        self.axis_title = QLineEdit()
        f.addRow(tr("common.axis"), self.axis_visible)
        f.addRow(tr("common.title"), self.title_visible)
        f.addRow(tr("property.axes.show_labels"), self.label_visible)
        f.addRow(tr("property.axes.title_text"), self.axis_title)
        layout.addWidget(vis)

        self.title_font = VtkFontStyleEditor(tr("property.axes.title_font"))
        self.label_font = VtkFontStyleEditor(tr("property.axes.label_font"))
        layout.addWidget(self.title_font)
        layout.addWidget(self.label_font)

        ticks = QGroupBox(tr("property.axes.ticks"))
        f = QFormLayout(ticks)
        self.major_ticks = QCheckBox(tr("property.axes.major"))
        self.minor_ticks = QCheckBox(tr("property.axes.minor"))
        self.number_format = QComboBox()
        add_combo_items(self.number_format, [("common.auto", "Auto"), ("choice.fixed", "Fixed"), ("choice.scientific", "Scientific")])
        self.decimals = QSpinBox()
        self.decimals.setRange(0, 12)
        f.addRow(tr("property.axes.major"), self.major_ticks)
        f.addRow(tr("property.axes.minor"), self.minor_ticks)
        f.addRow(tr("property.axes.format"), self.number_format)
        f.addRow(tr("property.axes.decimals"), self.decimals)
        layout.addWidget(ticks)

        line_g = QGroupBox(tr("property.axes.line"))
        f = QFormLayout(line_g)
        self.axis_line_color = ColorButton("#000000")
        self.axis_line_width = self._double(0.1, 10, 2)
        f.addRow(tr("common.color"), self.axis_line_color)
        f.addRow(tr("common.width"), self.axis_line_width)
        layout.addWidget(line_g)

        grid_g = QGroupBox(tr("property.axes.grid"))
        f = QFormLayout(grid_g)
        self.grid_visible = QCheckBox(tr("property.axes.show_grid"))
        self.grid_color = ColorButton("#b0b0b0")
        self.grid_width = self._double(0.1, 10, 2)
        f.addRow(tr("property.axes.grid"), self.grid_visible)
        f.addRow(tr("common.color"), self.grid_color)
        f.addRow(tr("common.width"), self.grid_width)
        layout.addWidget(grid_g)

        bounds = QGroupBox(tr("property.axes.bounds"))
        f = QFormLayout(bounds)
        self.auto_bounds = QCheckBox(tr("property.axes.auto_bounds"))
        self.axis_min = self._double()
        self.axis_max = self._double()
        f.addRow(tr("common.mode"), self.auto_bounds)
        f.addRow(tr("common.min"), self.axis_min)
        f.addRow(tr("common.max"), self.axis_max)
        layout.addWidget(bounds)

        shared = QGroupBox(tr("property.axes.layout"))
        f = QFormLayout(shared)
        self.tick_location = QComboBox()
        add_combo_items(self.tick_location, [("choice.inside", "Inside"), ("choice.outside", "Outside"), ("choice.both", "Both")])
        self.fly_mode = QComboBox()
        add_combo_items(self.fly_mode, [("choice.closest_triad", "Closest Triad"), ("choice.furthest_triad", "Furthest Triad"), ("choice.outer_edges", "Outer Edges"), ("choice.static_triad", "Static Triad"), ("choice.static_edges", "Static Edges")])
        self.grid_location = QComboBox()
        add_combo_items(self.grid_location, [("choice.all", "All"), ("choice.closest", "Closest"), ("choice.furthest", "Furthest")])
        self.title_offset_x = self._double(-500, 500, 1)
        self.title_offset_y = self._double(-500, 500, 1)
        self.label_offset = self._double(-500, 500, 1)
        self.corner_offset = self._double(0, 1, 3)
        for label, widget in [
            (tr("property.axes.tick_location"), self.tick_location),
            (tr("property.axes.fly_mode"), self.fly_mode),
            (tr("property.axes.grid_location"), self.grid_location),
            (tr("property.axes.title_offset_x"), self.title_offset_x),
            (tr("property.axes.title_offset_y"), self.title_offset_y),
            (tr("property.axes.label_offset"), self.label_offset),
            (tr("property.axes.corner_offset"), self.corner_offset),
        ]:
            f.addRow(label, widget)
        layout.addWidget(shared)
        layout.addStretch()
        self.axis_combo.currentIndexChanged.connect(self._switch_axis)
        return page

    def _load_common(self):
        c = self.config
        self._loading = True
        set_combo_value(self.background, c.background)
        self.show_axes.setChecked(c.show_axes)
        self.show_colorbar.setChecked(c.show_colorbar)
        self.show_legend.setChecked(c.show_legend)
        self.auto_normalize.setChecked(c.auto_normalize)
        self.x_scale.setValue(c.x_scale)
        self.y_scale.setValue(c.y_scale)
        self.z_scale.setValue(c.z_scale)
        self.screenshot_scale.setValue(c.screenshot_scale)
        self.auto_bounds.setChecked(c.auto_bounds)
        set_combo_value(self.tick_location, c.tick_location)
        set_combo_value(self.fly_mode, c.fly_mode)
        set_combo_value(self.grid_location, c.grid_line_location)
        self.title_offset_x.setValue(c.title_offset_x)
        self.title_offset_y.setValue(c.title_offset_y)
        self.label_offset.setValue(c.label_offset)
        self.corner_offset.setValue(c.corner_offset)
        self._axis_index = max(0, self.axis_combo.currentIndex())
        self._loading = False
        self._load_axis()

    def _axis_config(self, index=None):
        return (self.config.x_axis, self.config.y_axis, self.config.z_axis)[
            self._axis_index if index is None else index
        ]

    def _axis_bounds(self, index=None):
        idx = self._axis_index if index is None else index
        return (
            (self.config.x_min, self.config.x_max),
            (self.config.y_min, self.config.y_max),
            (self.config.z_min, self.config.z_max),
        )[idx]

    def _load_axis(self):
        self._loading = True
        axis = self._axis_config()
        minimum, maximum = self._axis_bounds()
        self.axis_visible.setChecked(axis.axis_visible)
        self.title_visible.setChecked(axis.title_visible)
        self.label_visible.setChecked(axis.label_visible)
        self.axis_title.setText(axis.title)
        self.major_ticks.setChecked(axis.major_tick_visible)
        self.minor_ticks.setChecked(axis.minor_tick_visible)
        set_combo_value(self.number_format, axis.format_mode)
        self.decimals.setValue(axis.decimals)
        self.axis_line_color.set_color(axis.line_color)
        self.axis_line_width.setValue(axis.line_width)
        self.grid_visible.setChecked(axis.grid_visible)
        self.grid_color.set_color(axis.grid_color)
        self.grid_width.setValue(axis.grid_width)
        self.title_font.load(axis.title_style)
        self.label_font.load(axis.label_style)
        self.axis_min.setValue(minimum)
        self.axis_max.setValue(maximum)
        self._loading = False

    def _save_axis(self):
        if self._loading:
            return
        axis = self._axis_config()
        axis.axis_visible = self.axis_visible.isChecked()
        axis.title_visible = self.title_visible.isChecked()
        axis.label_visible = self.label_visible.isChecked()
        axis.title = self.axis_title.text()
        axis.major_tick_visible = self.major_ticks.isChecked()
        axis.minor_tick_visible = self.minor_ticks.isChecked()
        axis.format_mode = combo_value(self.number_format)
        axis.decimals = self.decimals.value()
        axis.line_color = self.axis_line_color.color()
        axis.line_width = self.axis_line_width.value()
        axis.grid_visible = self.grid_visible.isChecked()
        axis.grid_color = self.grid_color.color()
        axis.grid_width = self.grid_width.value()
        self.title_font.save(axis.title_style)
        self.label_font.save(axis.label_style)
        if self._axis_index == 0:
            self.config.x_min, self.config.x_max = (
                self.axis_min.value(),
                self.axis_max.value(),
            )
        elif self._axis_index == 1:
            self.config.y_min, self.config.y_max = (
                self.axis_min.value(),
                self.axis_max.value(),
            )
        else:
            self.config.z_min, self.config.z_max = (
                self.axis_min.value(),
                self.axis_max.value(),
            )

    def _switch_axis(self, index):
        if self._loading:
            return
        self._save_axis()
        self._axis_index = max(0, index)
        self._load_axis()

    def _rebuild_selector(self, active_id):
        self._loading = True
        self.dataset_combo.clear()
        for dataset_id in self.render_order:
            self.dataset_combo.addItem(
                dataset_display_name(self.datasets[dataset_id]), dataset_id
            )
        idx = (
            self.render_order.index(active_id) if active_id in self.render_order else 0
        )
        self.dataset_combo.setCurrentIndex(idx if self.render_order else -1)
        self._loading = False
        self.active_id = self.dataset_combo.currentData() or ""
        self._load_dataset()
        enabled = bool(self.active_id)
        for w in self.dataset_controls:
            w.setEnabled(enabled)
        self.up_btn.setEnabled(
            enabled and self.render_order.index(self.active_id) > 0
            if enabled
            else False
        )
        self.down_btn.setEnabled(
            enabled
            and self.render_order.index(self.active_id) + 1 < len(self.render_order)
            if enabled
            else False
        )
        if not enabled:
            self.position_label.setText(tr("property.no_enabled_dataset"))

    def _load_dataset(self):
        if not self.active_id:
            return
        self._loading = True
        d = self.datasets[self.active_id]
        set_combo_value(self.mode, d.mode3d)
        set_combo_value(self.color_mode, d.color_mode)
        self.color.set_color(d.color)
        set_combo_value(self.cmap, d.colormap)
        self.auto_range.setChecked(d.auto_color_range)
        self.range_min.setValue(d.color_min)
        self.range_max.setValue(d.color_max)
        self.opacity.setValue(d.opacity)
        self.point_size.setValue(d.point_size)
        self.mesh_color.set_color(d.mesh_color)
        self.mesh_width.setValue(d.mesh_width)
        self.clip_axis.setCurrentText(d.clip_axis)
        self.clip_position.setValue(d.clip_position)
        self.slice_axis.setCurrentText(d.slice_axis)
        self.slice_position.setValue(d.slice_position)
        self.contour_levels.setText(d.contour_levels)
        set_combo_value(self.glyph_color_mode, d.glyph_color_mode)
        set_combo_value(self.glyph_size_mode, d.glyph_size_mode)
        self.glyph_scale.setValue(d.glyph_scale_factor)
        self.filter_enabled.setChecked(d.filter_enabled)
        idx = self.filter_field.findText(d.filter_field)
        self.filter_field.setCurrentIndex(max(0, idx))
        self.filter_min.setValue(d.filter_min)
        self.filter_max.setValue(d.filter_max)
        self.sub_enabled.setChecked(d.subregion_enabled)
        self.sub_imin.setValue(d.subregion_imin)
        self.sub_imax.setValue(d.subregion_imax)
        self.sub_jmin.setValue(d.subregion_jmin)
        self.sub_jmax.setValue(d.subregion_jmax)
        self.sub_kmin.setValue(d.subregion_kmin)
        self.sub_kmax.setValue(d.subregion_kmax)
        self.with_boundary.setChecked(d.with_boundary)
        self._on_mode_changed(d.mode3d)
        idx = self.render_order.index(self.active_id)
        self.position_label.setText(f"{idx + 1}/{len(self.render_order)}")
        self.up_btn.setEnabled(idx > 0)
        self.down_btn.setEnabled(idx + 1 < len(self.render_order))
        self._loading = False

    def _save_dataset(self):
        if self._loading or not self.active_id:
            return
        d = self.datasets[self.active_id]
        d.mode3d = combo_value(self.mode)
        d.color_mode = combo_value(self.color_mode)
        d.color = self.color.color()
        d.colormap = combo_value(self.cmap)
        d.auto_color_range = self.auto_range.isChecked()
        d.color_min = self.range_min.value()
        d.color_max = self.range_max.value()
        d.opacity = self.opacity.value()
        d.point_size = self.point_size.value()
        d.mesh_color = self.mesh_color.color()
        d.mesh_width = self.mesh_width.value()
        d.clip_axis = self.clip_axis.currentText()
        d.clip_position = self.clip_position.value()
        d.slice_axis = self.slice_axis.currentText()
        d.slice_position = self.slice_position.value()
        d.contour_levels = self.contour_levels.text()
        d.glyph_color_mode = combo_value(self.glyph_color_mode)
        d.glyph_size_mode = combo_value(self.glyph_size_mode)
        d.glyph_scale_factor = self.glyph_scale.value()
        d.filter_enabled = self.filter_enabled.isChecked()
        d.filter_field = self.filter_field.currentText()
        d.filter_min = self.filter_min.value()
        d.filter_max = self.filter_max.value()
        d.subregion_enabled = self.sub_enabled.isChecked()
        d.subregion_imin = self.sub_imin.value()
        d.subregion_imax = self.sub_imax.value()
        d.subregion_jmin = self.sub_jmin.value()
        d.subregion_jmax = self.sub_jmax.value()
        d.subregion_kmin = self.sub_kmin.value()
        d.subregion_kmax = self.sub_kmax.value()
        d.with_boundary = self.with_boundary.isChecked()

    def _switch_dataset(self, *_):
        if self._loading:
            return
        self._save_dataset()
        self.active_id = self.dataset_combo.currentData() or ""
        self._load_dataset()

    def _move_dataset(self, delta):
        self._save_dataset()
        idx = self.render_order.index(self.active_id)
        target = idx + delta
        if target < 0 or target >= len(self.render_order):
            return
        self.render_order[idx], self.render_order[target] = (
            self.render_order[target],
            self.render_order[idx],
        )
        self._rebuild_selector(self.active_id)

    def _save_common(self):
        self._save_axis()
        c = self.config
        c.background = combo_value(self.background)
        c.show_axes = self.show_axes.isChecked()
        c.show_colorbar = self.show_colorbar.isChecked()
        c.show_legend = self.show_legend.isChecked()
        c.auto_normalize = self.auto_normalize.isChecked()
        c.x_scale = self.x_scale.value()
        c.y_scale = self.y_scale.value()
        c.z_scale = self.z_scale.value()
        c.screenshot_scale = self.screenshot_scale.value()
        c.auto_bounds = self.auto_bounds.isChecked()
        c.tick_location = combo_value(self.tick_location)
        c.fly_mode = combo_value(self.fly_mode)
        c.grid_line_location = combo_value(self.grid_location)
        c.title_offset_x = self.title_offset_x.value()
        c.title_offset_y = self.title_offset_y.value()
        c.label_offset = self.label_offset.value()
        c.corner_offset = self.corner_offset.value()
        c.x_title = c.x_axis.title
        c.y_title = c.y_axis.title
        c.z_title = c.z_axis.title
        c.text_color = c.x_axis.label_style.color
        c.title_font_size = c.x_axis.title_style.size
        c.label_font_size = c.x_axis.label_style.size

    def _valid(self):
        self._save_dataset()
        self._save_common()
        c = self.config
        if not c.auto_bounds and not (
            c.x_min < c.x_max and c.y_min < c.y_max and c.z_min < c.z_max
        ):
            QMessageBox.warning(
                self, tr("validation.invalid_bounds"), tr("validation.bounds")
            )
            return False
        for dataset in self.datasets.values():
            if not dataset.auto_color_range and dataset.color_min >= dataset.color_max:
                QMessageBox.warning(
                    self,
                    tr("validation.invalid_range"),
                    tr("validation.color_range", name=dataset_display_name(dataset)),
                )
                return False
        return True

    def _apply(self):
        if self._valid():
            self.apply_callback(
                deepcopy(self.config),
                deepcopy(list(self.datasets.values())),
                list(self.render_order),
                self.active_id,
                deepcopy(self.style_templates),
            )

    def _accept(self):
        if self._valid():
            self.apply_callback(
                deepcopy(self.config),
                deepcopy(list(self.datasets.values())),
                list(self.render_order),
                self.active_id,
                deepcopy(self.style_templates),
            )
            self.accept()

    def _save_format(self):
        if self.save_format_callback is not None and self._valid():
            self.save_format_callback(
                deepcopy(self.config),
                deepcopy(list(self.datasets.values())),
                list(self.render_order),
                deepcopy(self.style_templates),
            )

    def _load_format(self):
        if self.load_format_callback is None or not self._valid():
            return
        loaded = self.load_format_callback(
            deepcopy(self.config),
            deepcopy(list(self.datasets.values())),
            list(self.render_order),
            deepcopy(self.style_templates),
        )
        if loaded is None:
            return
        self.config, datasets, self.style_templates = loaded
        self.config.migrate_legacy_axes()
        self.datasets = {item.dataset_id: item for item in datasets}
        self._load_common()
        self._rebuild_selector(self.active_id)
