"""Property dialog for CSV Plotter's VTK view."""
from __future__ import annotations

from copy import deepcopy

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from plot_property_dialog import ColorButton
from .models import dataset_display_name


class VtkFontStyleEditor(QGroupBox):
    def __init__(self, title, parent=None):
        super().__init__(title, parent); form = QFormLayout(self)
        self.family = QComboBox(); self.family.addItems(["Arial", "Courier", "Times"])
        self.size = QSpinBox(); self.size.setRange(6, 96); self.size.setSuffix(" px")
        self.bold = QCheckBox("Bold"); self.italic = QCheckBox("Italic"); self.color = ColorButton("#000000")
        flags = QHBoxLayout(); flags.addWidget(self.bold); flags.addWidget(self.italic); flags.addStretch()
        form.addRow("Font:", self.family); form.addRow("Size:", self.size)
        form.addRow("Style:", flags); form.addRow("Color:", self.color)

    def load(self, style):
        self.family.setCurrentText(style.font); self.size.setValue(style.size)
        self.bold.setChecked(style.bold); self.italic.setChecked(style.italic); self.color.set_color(style.color)

    def save(self, style):
        style.font = self.family.currentText(); style.size = self.size.value()
        style.bold = self.bold.isChecked(); style.italic = self.italic.isChecked(); style.color = self.color.color()


class VtkPropertyDialog(QDialog):
    def __init__(self, vtk_config, datasets, render_order, active_id, apply_callback, parent=None,
                 *, save_format_callback=None, load_format_callback=None, style_templates=None):
        super().__init__(parent)
        self.setWindowTitle("3D Properties"); self.resize(780, 780)
        self.config = deepcopy(vtk_config); self.config.migrate_legacy_axes()
        self.datasets = {item.dataset_id: deepcopy(item) for item in datasets}
        self.render_order = [value for value in render_order if value in self.datasets]
        self.render_order += [value for value in self.datasets if value not in self.render_order]
        self.active_id = active_id if active_id in self.datasets else (self.render_order[0] if self.render_order else "")
        self.apply_callback = apply_callback; self._loading = False; self._axis_index = 0
        self.save_format_callback = save_format_callback; self.load_format_callback = load_format_callback
        self.style_templates = list(deepcopy(style_templates or []))
        root = QVBoxLayout(self); tabs = QTabWidget(); root.addWidget(tabs, 1)
        tabs.addTab(self._build_dataset_page(), "Dataset"); tabs.addTab(self._build_scene_page(), "Scene"); tabs.addTab(self._build_axes_page(), "Axes")
        buttons = QHBoxLayout(); root.addLayout(buttons)
        save_btn = QPushButton("Save Format..."); load_btn = QPushButton("Load Format...")
        buttons.addWidget(save_btn); buttons.addWidget(load_btn); buttons.addStretch()
        apply_btn = QPushButton("Apply"); ok_btn = QPushButton("OK"); cancel_btn = QPushButton("Cancel")
        buttons.addWidget(apply_btn); buttons.addWidget(ok_btn); buttons.addWidget(cancel_btn)
        apply_btn.clicked.connect(self._apply); ok_btn.clicked.connect(self._accept); cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self._save_format); load_btn.clicked.connect(self._load_format)
        save_btn.setEnabled(self.save_format_callback is not None); load_btn.setEnabled(self.load_format_callback is not None)
        self._load_common(); self._rebuild_selector(self.active_id)

    @staticmethod
    def _double(minimum=-1e12, maximum=1e12, decimals=6):
        widget = QDoubleSpinBox(); widget.setRange(minimum, maximum); widget.setDecimals(decimals); widget.setKeyboardTracking(False)
        return widget

    def _build_dataset_page(self):
        page = QWidget(); outer = QVBoxLayout(page); top = QHBoxLayout(); outer.addLayout(top)
        self.dataset_combo = QComboBox(); self.position_label = QLabel(); self.up_btn = QPushButton("Move Up"); self.down_btn = QPushButton("Move Down")
        top.addWidget(QLabel("Active dataset:")); top.addWidget(self.dataset_combo, 1); top.addWidget(self.position_label); top.addWidget(self.up_btn); top.addWidget(self.down_btn)
        form = QFormLayout(); outer.addLayout(form)
        self.mode = QComboBox(); self.mode.addItems(["Surface", "Mesh", "Scatter"])
        self.color_mode = QComboBox(); self.color_mode.addItems(["Fixed Color", "Z Colormap"])
        self.color = ColorButton("#1f77b4"); self.cmap = QComboBox(); self.cmap.addItems(["Viridis", "Plasma", "Coolwarm", "Rainbow", "Grayscale"])
        self.auto_range = QCheckBox("Auto"); self.range_min = self._double(); self.range_max = self._double()
        self.opacity = self._double(0, 1, 2); self.point_size = self._double(1, 30, 1); self.mesh_color = ColorButton("#202020"); self.mesh_width = self._double(0.1, 10, 2)
        for label, widget in (("Mode:", self.mode), ("Color mode:", self.color_mode), ("Fixed color:", self.color), ("Colormap:", self.cmap),
                              ("Color range:", self.auto_range), ("Range minimum:", self.range_min), ("Range maximum:", self.range_max),
                              ("Opacity:", self.opacity), ("Point size:", self.point_size), ("Mesh color:", self.mesh_color), ("Mesh width:", self.mesh_width)): form.addRow(label, widget)
        self.dataset_controls = [self.mode, self.color_mode, self.color, self.cmap, self.auto_range, self.range_min, self.range_max, self.opacity, self.point_size, self.mesh_color, self.mesh_width]
        self.dataset_combo.currentIndexChanged.connect(self._switch_dataset); self.up_btn.clicked.connect(lambda: self._move_dataset(-1)); self.down_btn.clicked.connect(lambda: self._move_dataset(1))
        return page

    def _build_scene_page(self):
        page = QWidget(); form = QFormLayout(page)
        self.background = QComboBox(); self.background.addItems(["White", "Light Gray", "Gray", "Dark Gray", "Black"])
        self.show_colorbar = QCheckBox("Show active colorbar"); self.show_legend = QCheckBox("Show dataset legend"); self.auto_normalize = QCheckBox("Normalize union ranges")
        self.x_scale = self._double(0.001, 1000, 3); self.y_scale = self._double(0.001, 1000, 3); self.z_scale = self._double(0.001, 1000, 3)
        self.screenshot_scale = QSpinBox(); self.screenshot_scale.setRange(1, 8)
        for label, widget in (("Background:", self.background), ("Colorbar:", self.show_colorbar), ("Legend:", self.show_legend),
                              ("Auto visual normalization:", self.auto_normalize), ("X visual factor:", self.x_scale),
                              ("Y visual factor:", self.y_scale), ("Z visual factor:", self.z_scale), ("Screenshot scale:", self.screenshot_scale)): form.addRow(label, widget)
        return page

    def _build_axes_page(self):
        page = QWidget(); outer = QVBoxLayout(page); scroll = QScrollArea(); scroll.setWidgetResizable(True); outer.addWidget(scroll)
        content = QWidget(); layout = QVBoxLayout(content); scroll.setWidget(content)
        selector = QHBoxLayout(); layout.addLayout(selector)
        self.show_axes = QCheckBox("Show cube axes"); self.axis_combo = QComboBox(); self.axis_combo.addItems(["X Axis", "Y Axis", "Z Axis"])
        selector.addWidget(self.show_axes); selector.addStretch(); selector.addWidget(QLabel("Axis:")); selector.addWidget(self.axis_combo)
        visibility = QGroupBox("Visibility and title"); form = QFormLayout(visibility); layout.addWidget(visibility)
        self.axis_visible = QCheckBox("Show axis"); self.title_visible = QCheckBox("Show title"); self.label_visible = QCheckBox("Show tick labels"); self.axis_title = QLineEdit()
        form.addRow("Axis:", self.axis_visible); form.addRow("Title:", self.title_visible); form.addRow("Tick labels:", self.label_visible); form.addRow("Title text:", self.axis_title)
        self.title_font = VtkFontStyleEditor("Title font"); self.label_font = VtkFontStyleEditor("Tick-label font"); layout.addWidget(self.title_font); layout.addWidget(self.label_font)
        ticks = QGroupBox("Ticks and numeric format"); form = QFormLayout(ticks); layout.addWidget(ticks)
        self.major_ticks = QCheckBox("Show major ticks"); self.minor_ticks = QCheckBox("Show minor ticks")
        self.number_format = QComboBox(); self.number_format.addItems(["Auto", "Fixed", "Scientific"]); self.decimals = QSpinBox(); self.decimals.setRange(0, 12)
        form.addRow("Major ticks:", self.major_ticks); form.addRow("Minor ticks:", self.minor_ticks); form.addRow("Number format:", self.number_format); form.addRow("Decimals:", self.decimals)
        line = QGroupBox("Axis line"); form = QFormLayout(line); layout.addWidget(line)
        self.axis_line_color = ColorButton("#000000"); self.axis_line_width = self._double(0.1, 10, 2); form.addRow("Color:", self.axis_line_color); form.addRow("Width:", self.axis_line_width)
        grid = QGroupBox("Grid"); form = QFormLayout(grid); layout.addWidget(grid)
        self.grid_visible = QCheckBox("Show grid lines"); self.grid_color = ColorButton("#b0b0b0"); self.grid_width = self._double(0.1, 10, 2)
        form.addRow("Grid:", self.grid_visible); form.addRow("Color:", self.grid_color); form.addRow("Width:", self.grid_width)
        bounds = QGroupBox("Bounds"); form = QFormLayout(bounds); layout.addWidget(bounds)
        self.auto_bounds = QCheckBox("Auto from visible data"); self.axis_min = self._double(); self.axis_max = self._double()
        form.addRow("Mode:", self.auto_bounds); form.addRow("Minimum:", self.axis_min); form.addRow("Maximum:", self.axis_max)
        shared = QGroupBox("Axis layout"); form = QFormLayout(shared); layout.addWidget(shared)
        self.tick_location = QComboBox(); self.tick_location.addItems(["Inside", "Outside", "Both"])
        self.fly_mode = QComboBox(); self.fly_mode.addItems(["Closest Triad", "Furthest Triad", "Outer Edges", "Static Triad", "Static Edges"])
        self.grid_location = QComboBox(); self.grid_location.addItems(["All", "Closest", "Furthest"])
        self.title_offset_x = self._double(-500, 500, 1); self.title_offset_y = self._double(-500, 500, 1)
        self.label_offset = self._double(-500, 500, 1); self.corner_offset = self._double(0, 1, 3)
        for label, widget in (("Tick location:", self.tick_location), ("Fly mode:", self.fly_mode), ("Grid location:", self.grid_location),
                              ("Title offset X:", self.title_offset_x), ("Title offset Y:", self.title_offset_y),
                              ("Label offset:", self.label_offset), ("Corner offset:", self.corner_offset)): form.addRow(label, widget)
        layout.addStretch(); self.axis_combo.currentIndexChanged.connect(self._switch_axis)
        return page

    def _load_common(self):
        c = self.config; self._loading = True
        self.background.setCurrentText(c.background); self.show_axes.setChecked(c.show_axes); self.show_colorbar.setChecked(c.show_colorbar); self.show_legend.setChecked(c.show_legend)
        self.auto_normalize.setChecked(c.auto_normalize); self.x_scale.setValue(c.x_scale); self.y_scale.setValue(c.y_scale); self.z_scale.setValue(c.z_scale); self.screenshot_scale.setValue(c.screenshot_scale)
        self.auto_bounds.setChecked(c.auto_bounds); self.tick_location.setCurrentText(c.tick_location); self.fly_mode.setCurrentText(c.fly_mode); self.grid_location.setCurrentText(c.grid_line_location)
        self.title_offset_x.setValue(c.title_offset_x); self.title_offset_y.setValue(c.title_offset_y); self.label_offset.setValue(c.label_offset); self.corner_offset.setValue(c.corner_offset)
        self._axis_index = max(0, self.axis_combo.currentIndex()); self._loading = False; self._load_axis()

    def _axis_config(self, index=None): return (self.config.x_axis, self.config.y_axis, self.config.z_axis)[self._axis_index if index is None else index]
    def _axis_bounds(self, index=None):
        index = self._axis_index if index is None else index
        return ((self.config.x_min, self.config.x_max), (self.config.y_min, self.config.y_max), (self.config.z_min, self.config.z_max))[index]

    def _load_axis(self):
        self._loading = True; axis = self._axis_config(); minimum, maximum = self._axis_bounds()
        self.axis_visible.setChecked(axis.axis_visible); self.title_visible.setChecked(axis.title_visible); self.label_visible.setChecked(axis.label_visible); self.axis_title.setText(axis.title)
        self.major_ticks.setChecked(axis.major_tick_visible); self.minor_ticks.setChecked(axis.minor_tick_visible); self.number_format.setCurrentText(axis.format_mode); self.decimals.setValue(axis.decimals)
        self.axis_line_color.set_color(axis.line_color); self.axis_line_width.setValue(axis.line_width); self.grid_visible.setChecked(axis.grid_visible); self.grid_color.set_color(axis.grid_color); self.grid_width.setValue(axis.grid_width)
        self.title_font.load(axis.title_style); self.label_font.load(axis.label_style); self.axis_min.setValue(minimum); self.axis_max.setValue(maximum); self._loading = False

    def _save_axis(self):
        if self._loading: return
        axis = self._axis_config(); axis.axis_visible = self.axis_visible.isChecked(); axis.title_visible = self.title_visible.isChecked(); axis.label_visible = self.label_visible.isChecked(); axis.title = self.axis_title.text()
        axis.major_tick_visible = self.major_ticks.isChecked(); axis.minor_tick_visible = self.minor_ticks.isChecked(); axis.format_mode = self.number_format.currentText(); axis.decimals = self.decimals.value()
        axis.line_color = self.axis_line_color.color(); axis.line_width = self.axis_line_width.value(); axis.grid_visible = self.grid_visible.isChecked(); axis.grid_color = self.grid_color.color(); axis.grid_width = self.grid_width.value()
        self.title_font.save(axis.title_style); self.label_font.save(axis.label_style)
        if self._axis_index == 0: self.config.x_min, self.config.x_max = self.axis_min.value(), self.axis_max.value()
        elif self._axis_index == 1: self.config.y_min, self.config.y_max = self.axis_min.value(), self.axis_max.value()
        else: self.config.z_min, self.config.z_max = self.axis_min.value(), self.axis_max.value()

    def _switch_axis(self, index):
        if self._loading: return
        self._save_axis(); self._axis_index = max(0, index); self._load_axis()

    def _rebuild_selector(self, active_id):
        self._loading = True; self.dataset_combo.clear()
        for dataset_id in self.render_order: self.dataset_combo.addItem(dataset_display_name(self.datasets[dataset_id]), dataset_id)
        index = self.render_order.index(active_id) if active_id in self.render_order else 0
        self.dataset_combo.setCurrentIndex(index if self.render_order else -1); self._loading = False
        self.active_id = self.dataset_combo.currentData() or ""; self._load_dataset(); enabled = bool(self.active_id)
        for widget in self.dataset_controls: widget.setEnabled(enabled)
        self.up_btn.setEnabled(enabled and self.render_order.index(self.active_id) > 0 if enabled else False); self.down_btn.setEnabled(enabled and self.render_order.index(self.active_id) + 1 < len(self.render_order) if enabled else False)
        if not enabled: self.position_label.setText("No On dataset")

    def _load_dataset(self):
        if not self.active_id: return
        self._loading = True; d = self.datasets[self.active_id]
        self.mode.setCurrentText(d.mode3d); self.color_mode.setCurrentText(d.color_mode); self.color.set_color(d.color); self.cmap.setCurrentText(d.colormap); self.auto_range.setChecked(d.auto_color_range)
        self.range_min.setValue(d.color_min); self.range_max.setValue(d.color_max); self.opacity.setValue(d.opacity); self.point_size.setValue(d.point_size); self.mesh_color.set_color(d.mesh_color); self.mesh_width.setValue(d.mesh_width)
        index = self.render_order.index(self.active_id); self.position_label.setText(f"{index + 1}/{len(self.render_order)} (top first)"); self.up_btn.setEnabled(index > 0); self.down_btn.setEnabled(index + 1 < len(self.render_order)); self._loading = False

    def _save_dataset(self):
        if self._loading or not self.active_id: return
        d = self.datasets[self.active_id]; d.mode3d = self.mode.currentText(); d.color_mode = self.color_mode.currentText(); d.color = self.color.color(); d.colormap = self.cmap.currentText(); d.auto_color_range = self.auto_range.isChecked()
        d.color_min = self.range_min.value(); d.color_max = self.range_max.value(); d.opacity = self.opacity.value(); d.point_size = self.point_size.value(); d.mesh_color = self.mesh_color.color(); d.mesh_width = self.mesh_width.value()

    def _switch_dataset(self, *_):
        if self._loading: return
        self._save_dataset(); self.active_id = self.dataset_combo.currentData() or ""; self._load_dataset()

    def _move_dataset(self, delta):
        self._save_dataset(); index = self.render_order.index(self.active_id); target = index + delta
        if target < 0 or target >= len(self.render_order): return
        self.render_order[index], self.render_order[target] = self.render_order[target], self.render_order[index]; self._rebuild_selector(self.active_id)

    def _save_common(self):
        self._save_axis(); c = self.config
        c.background = self.background.currentText(); c.show_axes = self.show_axes.isChecked(); c.show_colorbar = self.show_colorbar.isChecked(); c.show_legend = self.show_legend.isChecked(); c.auto_normalize = self.auto_normalize.isChecked()
        c.x_scale = self.x_scale.value(); c.y_scale = self.y_scale.value(); c.z_scale = self.z_scale.value(); c.screenshot_scale = self.screenshot_scale.value(); c.auto_bounds = self.auto_bounds.isChecked()
        c.tick_location = self.tick_location.currentText(); c.fly_mode = self.fly_mode.currentText(); c.grid_line_location = self.grid_location.currentText(); c.title_offset_x = self.title_offset_x.value(); c.title_offset_y = self.title_offset_y.value(); c.label_offset = self.label_offset.value(); c.corner_offset = self.corner_offset.value()
        c.x_title = c.x_axis.title; c.y_title = c.y_axis.title; c.z_title = c.z_axis.title; c.text_color = c.x_axis.label_style.color; c.title_font_size = c.x_axis.title_style.size; c.label_font_size = c.x_axis.label_style.size

    def _valid(self):
        self._save_dataset(); self._save_common(); c = self.config
        if not c.auto_bounds and not (c.x_min < c.x_max and c.y_min < c.y_max and c.z_min < c.z_max): QMessageBox.warning(self, "Invalid Bounds", "Each minimum must be smaller than its maximum."); return False
        for dataset in self.datasets.values():
            if not dataset.auto_color_range and dataset.color_min >= dataset.color_max: QMessageBox.warning(self, "Invalid Range", f"{dataset_display_name(dataset)}: color minimum must be smaller than maximum."); return False
        return True

    def _apply(self):
        if self._valid(): self.apply_callback(deepcopy(self.config), deepcopy(list(self.datasets.values())), list(self.render_order), self.active_id, deepcopy(self.style_templates))

    def _accept(self):
        if self._valid(): self.apply_callback(deepcopy(self.config), deepcopy(list(self.datasets.values())), list(self.render_order), self.active_id, deepcopy(self.style_templates)); self.accept()

    def _save_format(self):
        if self.save_format_callback is not None and self._valid(): self.save_format_callback(deepcopy(self.config), deepcopy(list(self.datasets.values())), list(self.render_order), deepcopy(self.style_templates))

    def _load_format(self):
        if self.load_format_callback is None or not self._valid(): return
        loaded = self.load_format_callback(deepcopy(self.config), deepcopy(list(self.datasets.values())), list(self.render_order), deepcopy(self.style_templates))
        if loaded is None: return
        self.config, datasets, self.style_templates = loaded; self.config.migrate_legacy_axes(); self.datasets = {item.dataset_id: item for item in datasets}
        self._load_common(); self._rebuild_selector(self.active_id)
