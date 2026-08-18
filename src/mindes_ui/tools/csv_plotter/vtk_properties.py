"""Property dialog for CSV Plotter's VTK view."""

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


class VtkPropertyDialog(QDialog):
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
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("property.3d.title"))
        self.resize(780, 780)
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
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)
        tabs.addTab(self._build_dataset_page(), tr("property.tab.dataset"))
        tabs.addTab(self._build_scene_page(), tr("property.tab.scene"))
        tabs.addTab(self._build_axes_page(), tr("property.tab.axes"))
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
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(decimals)
        widget.setKeyboardTracking(False)
        return widget

    def _build_dataset_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        top = QHBoxLayout()
        outer.addLayout(top)
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
        outer.addLayout(form)
        self.mode = QComboBox()
        add_combo_items(self.mode, [("choice.surface", "Surface"), ("choice.mesh", "Mesh"), ("choice.scatter", "Scatter")])
        self.color_mode = QComboBox()
        add_combo_items(self.color_mode, [("choice.fixed_color", "Fixed Color"), ("choice.z_colormap", "Z Colormap")])
        self.color = ColorButton("#1f77b4")
        self.cmap = QComboBox()
        add_combo_items(self.cmap, [("choice.viridis", "Viridis"), ("choice.plasma", "Plasma"), ("choice.coolwarm", "Coolwarm"), ("choice.rainbow", "Rainbow"), ("choice.grayscale", "Grayscale")])
        self.auto_range = QCheckBox(tr("common.auto"))
        self.range_min = self._double()
        self.range_max = self._double()
        self.opacity = self._double(0, 1, 2)
        self.point_size = self._double(1, 30, 1)
        self.mesh_color = ColorButton("#202020")
        self.mesh_width = self._double(0.1, 10, 2)
        for label, widget in (
            (tr("property.dataset.mode"), self.mode),
            (tr("property.dataset.color_mode"), self.color_mode),
            (tr("property.dataset.fixed_color"), self.color),
            (tr("property.dataset.colormap"), self.cmap),
            (tr("property.dataset.color_range"), self.auto_range),
            (tr("property.dataset.range_min"), self.range_min),
            (tr("property.dataset.range_max"), self.range_max),
            (tr("common.opacity"), self.opacity),
            (tr("property.dataset.point_size"), self.point_size),
            (tr("property.dataset.mesh_color"), self.mesh_color),
            (tr("property.dataset.mesh_width"), self.mesh_width),
        ):
            form.addRow(label, widget)
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
        return page

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
        for label, widget in (
            (tr("common.background"), self.background),
            (tr("property.scene.colorbar"), self.show_colorbar),
            (tr("property.scene.legend"), self.show_legend),
            (tr("property.scene.normalize"), self.auto_normalize),
            (tr("property.scene.x_factor"), self.x_scale),
            (tr("property.scene.y_factor"), self.y_scale),
            (tr("property.scene.z_factor"), self.z_scale),
            (tr("property.scene.screenshot_scale"), self.screenshot_scale),
        ):
            form.addRow(label, widget)
        return page

    def _build_axes_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        selector = QHBoxLayout()
        layout.addLayout(selector)
        self.show_axes = QCheckBox(tr("property.axes.show"))
        self.axis_combo = QComboBox()
        self.axis_combo.addItems([tr("property.axes.x"), tr("property.axes.y"), tr("property.axes.z")])
        selector.addWidget(self.show_axes)
        selector.addStretch()
        selector.addWidget(QLabel(tr("common.axis")))
        selector.addWidget(self.axis_combo)
        visibility = QGroupBox(tr("property.axes.visibility"))
        form = QFormLayout(visibility)
        layout.addWidget(visibility)
        self.axis_visible = QCheckBox(tr("property.axes.show_axis"))
        self.title_visible = QCheckBox(tr("property.axes.show_title"))
        self.label_visible = QCheckBox(tr("property.axes.show_labels"))
        self.axis_title = QLineEdit()
        form.addRow(tr("common.axis"), self.axis_visible)
        form.addRow(tr("common.title"), self.title_visible)
        form.addRow(tr("property.axes.show_labels"), self.label_visible)
        form.addRow(tr("property.axes.title_text"), self.axis_title)
        self.title_font = VtkFontStyleEditor(tr("property.axes.title_font"))
        self.label_font = VtkFontStyleEditor(tr("property.axes.label_font"))
        layout.addWidget(self.title_font)
        layout.addWidget(self.label_font)
        ticks = QGroupBox(tr("property.axes.ticks"))
        form = QFormLayout(ticks)
        layout.addWidget(ticks)
        self.major_ticks = QCheckBox(tr("property.axes.major"))
        self.minor_ticks = QCheckBox(tr("property.axes.minor"))
        self.number_format = QComboBox()
        add_combo_items(self.number_format, [("common.auto", "Auto"), ("choice.fixed", "Fixed"), ("choice.scientific", "Scientific")])
        self.decimals = QSpinBox()
        self.decimals.setRange(0, 12)
        form.addRow(tr("property.axes.major"), self.major_ticks)
        form.addRow(tr("property.axes.minor"), self.minor_ticks)
        form.addRow(tr("property.axes.format"), self.number_format)
        form.addRow(tr("property.axes.decimals"), self.decimals)
        line = QGroupBox(tr("property.axes.line"))
        form = QFormLayout(line)
        layout.addWidget(line)
        self.axis_line_color = ColorButton("#000000")
        self.axis_line_width = self._double(0.1, 10, 2)
        form.addRow(tr("common.color"), self.axis_line_color)
        form.addRow(tr("common.width"), self.axis_line_width)
        grid = QGroupBox(tr("property.axes.grid"))
        form = QFormLayout(grid)
        layout.addWidget(grid)
        self.grid_visible = QCheckBox(tr("property.axes.show_grid"))
        self.grid_color = ColorButton("#b0b0b0")
        self.grid_width = self._double(0.1, 10, 2)
        form.addRow(tr("property.axes.grid"), self.grid_visible)
        form.addRow(tr("common.color"), self.grid_color)
        form.addRow(tr("common.width"), self.grid_width)
        bounds = QGroupBox(tr("property.axes.bounds"))
        form = QFormLayout(bounds)
        layout.addWidget(bounds)
        self.auto_bounds = QCheckBox(tr("property.axes.auto_bounds"))
        self.axis_min = self._double()
        self.axis_max = self._double()
        form.addRow(tr("common.mode"), self.auto_bounds)
        form.addRow(tr("common.minimum"), self.axis_min)
        form.addRow(tr("common.maximum"), self.axis_max)
        shared = QGroupBox(tr("property.axes.layout"))
        form = QFormLayout(shared)
        layout.addWidget(shared)
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
        for label, widget in (
            (tr("property.axes.tick_location"), self.tick_location),
            (tr("property.axes.fly_mode"), self.fly_mode),
            (tr("property.axes.grid_location"), self.grid_location),
            (tr("property.axes.title_offset_x"), self.title_offset_x),
            (tr("property.axes.title_offset_y"), self.title_offset_y),
            (tr("property.axes.label_offset"), self.label_offset),
            (tr("property.axes.corner_offset"), self.corner_offset),
        ):
            form.addRow(label, widget)
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
        index = self._axis_index if index is None else index
        return (
            (self.config.x_min, self.config.x_max),
            (self.config.y_min, self.config.y_max),
            (self.config.z_min, self.config.z_max),
        )[index]

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
        index = (
            self.render_order.index(active_id) if active_id in self.render_order else 0
        )
        self.dataset_combo.setCurrentIndex(index if self.render_order else -1)
        self._loading = False
        self.active_id = self.dataset_combo.currentData() or ""
        self._load_dataset()
        enabled = bool(self.active_id)
        for widget in self.dataset_controls:
            widget.setEnabled(enabled)
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
        index = self.render_order.index(self.active_id)
        self.position_label.setText(
            tr(
                "figure_property.position_top_first",
                current=index + 1,
                total=len(self.render_order),
            )
        )
        self.up_btn.setEnabled(index > 0)
        self.down_btn.setEnabled(index + 1 < len(self.render_order))
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

    def _switch_dataset(self, *_):
        if self._loading:
            return
        self._save_dataset()
        self.active_id = self.dataset_combo.currentData() or ""
        self._load_dataset()

    def _move_dataset(self, delta):
        self._save_dataset()
        index = self.render_order.index(self.active_id)
        target = index + delta
        if target < 0 or target >= len(self.render_order):
            return
        self.render_order[index], self.render_order[target] = (
            self.render_order[target],
            self.render_order[index],
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
