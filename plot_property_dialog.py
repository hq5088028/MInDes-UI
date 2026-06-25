"""Property editor for publication-quality statistic figures."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFontComboBox, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from plot_config import FigureConfig, TextStyle, new_curve


class ColorButton(QPushButton):
    colorChanged = Signal(str)

    def __init__(self, color="#000000", parent=None):
        super().__init__(parent)
        self._color = color
        self.clicked.connect(self._choose)
        self.set_color(color)

    def color(self):
        return self._color

    def set_color(self, color):
        self._color = QColor(color).name()
        self.setText(self._color)
        self.setStyleSheet(
            f"QPushButton{{background:{self._color};color:"
            f"{'white' if QColor(self._color).lightness() < 120 else 'black'};}}"
        )

    def _choose(self):
        color = QColorDialog.getColor(QColor(self._color), self)
        if color.isValid():
            self.set_color(color.name())
            self.colorChanged.emit(self._color)


class FontStyleEditor(QGroupBox):
    changed = Signal()

    def __init__(self, title, include_text=True, parent=None):
        super().__init__(title, parent)
        form = QFormLayout(self)
        self.text_edit = QLineEdit()
        self.visible_cb = QCheckBox("Show")
        self.font_combo = QFontComboBox()
        self.size_spin = QDoubleSpinBox(); self.size_spin.setRange(4, 72); self.size_spin.setDecimals(1)
        self.bold_cb = QCheckBox("Bold")
        self.italic_cb = QCheckBox("Italic")
        self.color_btn = ColorButton()
        if include_text:
            form.addRow("Text:", self.text_edit)
            form.addRow("Visible:", self.visible_cb)
        form.addRow("Font:", self.font_combo)
        form.addRow("Size (pt):", self.size_spin)
        flags = QHBoxLayout(); flags.addWidget(self.bold_cb); flags.addWidget(self.italic_cb)
        form.addRow("Style:", flags)
        form.addRow("Color:", self.color_btn)
        for widget in (self.text_edit, self.visible_cb, self.font_combo, self.size_spin,
                       self.bold_cb, self.italic_cb):
            if hasattr(widget, "textChanged"):
                widget.textChanged.connect(self.changed)
            elif hasattr(widget, "currentFontChanged"):
                widget.currentFontChanged.connect(self.changed)
            elif hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self.changed)
            else:
                widget.toggled.connect(self.changed)
        self.color_btn.colorChanged.connect(self.changed)

    def load(self, style: TextStyle):
        self.blockSignals(True)
        self.text_edit.setText(style.text)
        self.visible_cb.setChecked(style.visible)
        self.font_combo.setCurrentFont(self.font_combo.currentFont().__class__(style.font))
        self.size_spin.setValue(style.size)
        self.bold_cb.setChecked(style.bold)
        self.italic_cb.setChecked(style.italic)
        self.color_btn.set_color(style.color)
        self.blockSignals(False)

    def save(self, style: TextStyle):
        style.text = self.text_edit.text()
        style.visible = self.visible_cb.isChecked()
        style.font = self.font_combo.currentFont().family()
        style.size = self.size_spin.value()
        style.bold = self.bold_cb.isChecked()
        style.italic = self.italic_cb.isChecked()
        style.color = self.color_btn.color()


class PlotPropertyDialog(QDialog):
    def __init__(self, config: FigureConfig, columns: list[str], apply_callback,
                 save_format_callback, parent=None, *, shared_y_axis=False,
                 curve_names=None, curve_columns=None, initial_curve_id=None,
                 load_format_callback=None, format_templates=None):
        super().__init__(parent)
        self.setWindowTitle("Figure Properties")
        self.resize(980, 720)
        self.config = config.copy()
        self.columns = list(columns)
        self.shared_y_axis = bool(shared_y_axis)
        self.curve_names = dict(curve_names or {})
        self.curve_columns = dict(curve_columns or {})
        self.initial_curve_id = initial_curve_id
        self._initial_curve_applied = False
        self._apply_callback = apply_callback
        self._save_format_callback = save_format_callback
        self._load_format_callback = load_format_callback
        self.format_templates = list(format_templates or [])
        self._loading = False
        self._last_unit = self.config.unit

        root = QVBoxLayout(self)
        body = QHBoxLayout(); root.addLayout(body, 1)
        self.nav = QListWidget(); self.nav.setFixedWidth(145)
        self.nav.addItems(["Overall", "Text", "Axes", "Grid", "Curves", "Legend", "Export"])
        self.stack = QStackedWidget()
        body.addWidget(self.nav); body.addWidget(self.stack, 1)
        self._build_overall(); self._build_text(); self._build_axes()
        self._build_grid(); self._build_curves(); self._build_legend(); self._build_export()
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        buttons = QHBoxLayout(); root.addLayout(buttons)
        self.factory_btn = QPushButton("Restore Factory")
        self.default_btn = QPushButton("Save Format...")
        self.load_format_btn = QPushButton("Load Format...")
        self.apply_btn = QPushButton("Apply")
        self.ok_btn = QPushButton("OK")
        self.cancel_btn = QPushButton("Cancel")
        buttons.addWidget(self.factory_btn); buttons.addWidget(self.default_btn); buttons.addWidget(self.load_format_btn); buttons.addStretch()
        buttons.addWidget(self.apply_btn); buttons.addWidget(self.ok_btn); buttons.addWidget(self.cancel_btn)
        self.factory_btn.clicked.connect(self._restore_factory)
        self.default_btn.clicked.connect(self._save_format)
        self.load_format_btn.clicked.connect(self._load_format)
        self.load_format_btn.setEnabled(self._load_format_callback is not None)
        self.apply_btn.clicked.connect(self._apply)
        self.ok_btn.clicked.connect(self._accept)
        self.cancel_btn.clicked.connect(self.reject)
        self._load_all()

    def _page(self):
        page = QWidget(); outer = QVBoxLayout(page)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget(); layout = QVBoxLayout(content); layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(content); outer.addWidget(scroll); self.stack.addWidget(page)
        return layout

    @staticmethod
    def _double(minimum=-1e12, maximum=1e12, decimals=6):
        w = QDoubleSpinBox(); w.setRange(minimum, maximum); w.setDecimals(decimals); w.setKeyboardTracking(False)
        return w

    def _build_overall(self):
        lay = self._page(); form = QFormLayout(); lay.addLayout(form)
        self.unit_combo = QComboBox(); self.unit_combo.addItems(["cm", "in", "mm"])
        self.width_spin = self._double(1, 500, 3); self.height_spin = self._double(1, 500, 3)
        self.background_combo = QComboBox(); self.background_combo.addItems(["White", "Transparent"])
        self.margin_left = self._double(0, 100, 3); self.margin_right = self._double(0, 100, 3)
        self.margin_top = self._double(0, 100, 3); self.margin_bottom = self._double(0, 100, 3)
        form.addRow("Unit:", self.unit_combo); form.addRow("Width:", self.width_spin)
        form.addRow("Height:", self.height_spin); form.addRow("Background:", self.background_combo)
        form.addRow("Left margin:", self.margin_left); form.addRow("Right margin:", self.margin_right)
        form.addRow("Top margin:", self.margin_top); form.addRow("Bottom margin:", self.margin_bottom)
        self.unit_combo.currentTextChanged.connect(self._unit_changed)

    def _build_text(self):
        lay = self._page()
        self.title_editor = FontStyleEditor("Title"); self.xlabel_editor = FontStyleEditor("X axis label")
        lay.addWidget(self.title_editor); lay.addWidget(self.xlabel_editor)
        self.text_curve_combo = QComboBox(); lay.addWidget(QLabel("Y curve:")); lay.addWidget(self.text_curve_combo)
        self.ylabel_editor = FontStyleEditor("Selected Y axis label")
        self.ytick_editor = FontStyleEditor("Selected Y tick numbers", include_text=False)
        lay.addWidget(self.ylabel_editor); lay.addWidget(self.ytick_editor)
        self.latex_cb = QCheckBox("Use external LaTeX (fallback to MathText if unavailable)")
        lay.addWidget(self.latex_cb)
        self.text_curve_combo.currentIndexChanged.connect(self._load_curve_text)
        self.ylabel_editor.changed.connect(self._save_curve_text)
        self.ytick_editor.changed.connect(self._save_curve_text)

    def _build_axes(self):
        lay = self._page(); self.axis_combo = QComboBox(); lay.addWidget(QLabel("Axis:")); lay.addWidget(self.axis_combo)
        form = QFormLayout(); lay.addLayout(form)
        self.scale_combo = QComboBox(); self.scale_combo.addItems(["Linear", "Log10", "SymLog"])
        self.auto_range_cb = QCheckBox("Auto")
        self.axis_min = self._double(); self.axis_max = self._double(); self.invert_cb = QCheckBox("Reverse axis")
        self.major_cb = QCheckBox("Show"); self.minor_cb = QCheckBox("Show")
        self.tick_bottom_cb = QCheckBox("Bottom"); self.tick_top_cb = QCheckBox("Top")
        self.tick_left_cb = QCheckBox("Left"); self.tick_right_cb = QCheckBox("Right")
        tick_sides = QHBoxLayout()
        for widget in (self.tick_bottom_cb, self.tick_top_cb, self.tick_left_cb, self.tick_right_cb):
            tick_sides.addWidget(widget)
        self.tick_direction = QComboBox(); self.tick_direction.addItems(["in", "out", "inout"])
        self.major_length = self._double(0, 30, 2); self.minor_length = self._double(0, 30, 2)
        self.tick_width = self._double(0.1, 10, 2); self.tick_color = ColorButton()
        self.format_combo = QComboBox(); self.format_combo.addItems(["Auto", "Fixed", "Scientific", "Percent"])
        self.decimals_spin = QSpinBox(); self.decimals_spin.setRange(0, 12)
        self.manual_combo = QComboBox(); self.manual_combo.addItems(["Auto", "Positions", "Start/Stop/Step"])
        self.positions_edit = QLineEdit(); self.positions_edit.setPlaceholderText("0, 0.2, 0.5, 1.0")
        self.tick_start = self._double(); self.tick_stop = self._double(); self.tick_step = self._double(1e-12, 1e12)
        self.spine_cb = QCheckBox("Show"); self.spine_width = self._double(0.1, 10, 2); self.spine_color = ColorButton()
        self.top_spine_cb = QCheckBox("Top"); self.bottom_spine_cb = QCheckBox("Bottom")
        self.left_spine_cb = QCheckBox("Left"); self.right_spine_cb = QCheckBox("Right")
        global_spines = QHBoxLayout()
        for widget in (self.top_spine_cb, self.bottom_spine_cb, self.left_spine_cb, self.right_spine_cb):
            global_spines.addWidget(widget)
        self.xtick_editor = FontStyleEditor("Tick number font", include_text=False)
        for label, widget in [("Scale:", self.scale_combo), ("Range:", self.auto_range_cb),
                              ("Minimum:", self.axis_min), ("Maximum:", self.axis_max), ("Direction:", self.invert_cb),
                              ("Major ticks:", self.major_cb), ("Minor ticks:", self.minor_cb),
                              ("Tick direction:", self.tick_direction), ("Major length:", self.major_length),
                              ("Minor length:", self.minor_length), ("Tick width:", self.tick_width),
                              ("Tick color:", self.tick_color), ("Number format:", self.format_combo),
                              ("Decimals:", self.decimals_spin), ("Tick positions:", self.manual_combo),
                              ("Position list:", self.positions_edit), ("Start:", self.tick_start),
                              ("Stop:", self.tick_stop), ("Step:", self.tick_step), ("Spine:", self.spine_cb),
                              ("Spine width:", self.spine_width), ("Spine color:", self.spine_color)]:
            form.addRow(label, widget)
        form.insertRow(8, "Tick sides:", tick_sides)
        form.addRow("Main frame sides:", global_spines)
        lay.addWidget(self.xtick_editor)
        self.axis_combo.currentIndexChanged.connect(self._load_axis)
        for widget in (self.scale_combo, self.auto_range_cb, self.axis_min, self.axis_max, self.invert_cb,
                       self.major_cb, self.minor_cb, self.tick_direction, self.major_length, self.minor_length,
                       self.tick_bottom_cb, self.tick_top_cb, self.tick_left_cb, self.tick_right_cb,
                       self.tick_width, self.format_combo, self.decimals_spin, self.manual_combo,
                       self.positions_edit, self.tick_start, self.tick_stop, self.tick_step,
                       self.spine_cb, self.spine_width):
            signal = getattr(widget, "currentTextChanged", None) or getattr(widget, "toggled", None) or getattr(widget, "valueChanged", None) or getattr(widget, "textChanged")
            signal.connect(self._save_axis)
        self.tick_color.colorChanged.connect(self._save_axis); self.spine_color.colorChanged.connect(self._save_axis)
        self.xtick_editor.changed.connect(self._save_axis)

    def _build_grid(self):
        lay = self._page(); self.grid_axis_combo = QComboBox(); lay.addWidget(QLabel("Axis:")); lay.addWidget(self.grid_axis_combo)
        form = QFormLayout(); lay.addLayout(form)
        self.grid_cb = QCheckBox("Show major grid")
        self.grid_color = ColorButton("#b0b0b0")
        self.grid_line = QComboBox(); self.grid_line.addItems(["-", "--", "-.", ":"])
        self.grid_width = self._double(0.1, 10, 2); self.grid_alpha = self._double(0, 1, 2)
        form.addRow("Visible:", self.grid_cb); form.addRow("Color:", self.grid_color)
        form.addRow("Line style:", self.grid_line); form.addRow("Line width:", self.grid_width); form.addRow("Alpha:", self.grid_alpha)
        self.grid_axis_combo.currentIndexChanged.connect(self._load_grid)
        self.grid_cb.toggled.connect(self._save_grid); self.grid_color.colorChanged.connect(self._save_grid)
        self.grid_line.currentTextChanged.connect(self._save_grid); self.grid_width.valueChanged.connect(self._save_grid); self.grid_alpha.valueChanged.connect(self._save_grid)

    def _build_curves(self):
        lay = self._page(); top = QHBoxLayout(); lay.addLayout(top)
        self.curve_combo = QComboBox(); self.up_btn = QPushButton("Move Up"); self.down_btn = QPushButton("Move Down")
        self.curve_position_label = QLabel()
        top.addWidget(QLabel("Active dataset:")); top.addWidget(self.curve_combo, 1)
        top.addWidget(self.curve_position_label); top.addWidget(self.up_btn); top.addWidget(self.down_btn)
        form = QFormLayout(); lay.addLayout(form)
        self.curve_visible = QCheckBox("Show"); self.legend_edit = QLineEdit()
        self.line_color = ColorButton(); self.line_width = self._double(0.1, 20, 2)
        self.line_style = QComboBox(); self.line_style.addItems(["-", "--", "-.", ":", "None"])
        self.marker_combo = QComboBox(); self.marker_combo.addItems(["None", "o", "s", "^", "v", "D", "+", "x", "*"])
        self.marker_size = self._double(0.1, 30, 2); self.marker_face = ColorButton("#ffffff"); self.marker_edge = ColorButton()
        self.marker_edge_width = self._double(0, 10, 2); self.mark_every = QSpinBox(); self.mark_every.setRange(1, 100000)
        self.error_mode = QComboBox(); self.error_mode.addItems(["None", "Bars", "Band", "Bars + Band"])
        self.error_source = QComboBox(); self.error_source.addItems(["Constant", "Column"])
        self.error_column = QComboBox(); self.error_constant = self._double(0, 1e12)
        self.error_every = QSpinBox(); self.error_every.setRange(1, 100000)
        self.capsize = self._double(0, 30, 2); self.capthick = self._double(0.1, 10, 2); self.error_width = self._double(0.1, 10, 2)
        self.error_color = ColorButton(); self.band_color = ColorButton(); self.band_alpha = self._double(0, 1, 2)
        fields = [("Visible:", self.curve_visible), ("Legend text:", self.legend_edit), ("Line color:", self.line_color),
                  ("Line width:", self.line_width), ("Line style:", self.line_style), ("Marker:", self.marker_combo),
                  ("Marker size:", self.marker_size), ("Marker face:", self.marker_face), ("Marker edge:", self.marker_edge),
                  ("Marker edge width:", self.marker_edge_width), ("Marker every N:", self.mark_every),
                  ("Error display:", self.error_mode), ("Error source:", self.error_source), ("Error column:", self.error_column),
                  ("Constant error:", self.error_constant), ("Error every N:", self.error_every), ("Cap length:", self.capsize),
                  ("Cap width:", self.capthick), ("Error line width:", self.error_width), ("Error color:", self.error_color),
                  ("Band color:", self.band_color), ("Band alpha:", self.band_alpha)]
        for label, widget in fields: form.addRow(label, widget)
        self.curve_combo.currentIndexChanged.connect(self._load_curve)
        self.up_btn.clicked.connect(lambda: self._move_curve(-1)); self.down_btn.clicked.connect(lambda: self._move_curve(1))
        for widget in (self.curve_visible, self.legend_edit, self.line_width, self.line_style, self.marker_combo,
                       self.marker_size, self.marker_edge_width, self.mark_every, self.error_mode, self.error_source,
                       self.error_column, self.error_constant, self.error_every, self.capsize, self.capthick,
                       self.error_width, self.band_alpha):
            signal = getattr(widget, "currentTextChanged", None) or getattr(widget, "toggled", None) or getattr(widget, "valueChanged", None) or getattr(widget, "textChanged")
            signal.connect(self._save_curve)
        for button in (self.line_color, self.marker_face, self.marker_edge, self.error_color, self.band_color):
            button.colorChanged.connect(self._save_curve)

    def _build_legend(self):
        lay = self._page(); form = QFormLayout(); lay.addLayout(form)
        self.legend_cb = QCheckBox("Show")
        self.legend_loc = QComboBox(); self.legend_loc.addItems(["best", "upper left", "upper right", "lower left", "lower right", "center left", "center right", "lower center", "upper center", "center"])
        self.anchor_cb = QCheckBox("Use custom anchor"); self.anchor_x = self._double(-10, 10, 3); self.anchor_y = self._double(-10, 10, 3)
        self.legend_cols = QSpinBox(); self.legend_cols.setRange(1, 20)
        self.frame_cb = QCheckBox("Show frame"); self.frame_edge = ColorButton(); self.frame_face = ColorButton("#ffffff"); self.frame_alpha = self._double(0, 1, 2)
        form.addRow("Visible:", self.legend_cb); form.addRow("Location:", self.legend_loc); form.addRow("Anchor:", self.anchor_cb)
        form.addRow("Anchor X:", self.anchor_x); form.addRow("Anchor Y:", self.anchor_y); form.addRow("Columns:", self.legend_cols)
        form.addRow("Frame:", self.frame_cb); form.addRow("Frame edge:", self.frame_edge); form.addRow("Frame face:", self.frame_face); form.addRow("Frame alpha:", self.frame_alpha)
        self.legend_font = FontStyleEditor("Legend font", include_text=False); lay.addWidget(self.legend_font)

    def _build_export(self):
        lay = self._page(); form = QFormLayout(); lay.addLayout(form)
        self.dpi_spin = QSpinBox(); self.dpi_spin.setRange(72, 2400); self.dpi_spin.setSuffix(" dpi")
        form.addRow("Raster resolution:", self.dpi_spin)
        lay.addWidget(QLabel("PNG, JPEG and TIFF use this DPI. PDF and SVG remain vector outputs."))

    def _curve_names(self):
        if self.shared_y_axis:
            return [self.curve_names.get(c.column, c.legend_text or c.column) for c in self.config.curves]
        return [f"{'Left' if c.side == 'left' else 'Right'}: {self.curve_names.get(c.column, c.column)}" for c in self.config.curves]

    def _axis_style(self, combo):
        idx = combo.currentIndex()
        if self.shared_y_axis:
            return self.config.x_axis if idx <= 0 else self.config.shared_y_axis
        return self.config.x_axis if idx <= 0 else self.config.curves[idx - 1].axis

    def _load_all(self):
        self._loading = True
        from plot_config import convert_length
        c = self.config; unit = c.unit
        self.unit_combo.setCurrentText(unit); self._last_unit = unit
        self.width_spin.setValue(convert_length(c.width_cm, "cm", unit)); self.height_spin.setValue(convert_length(c.height_cm, "cm", unit))
        self.background_combo.setCurrentText(c.background)
        for widget, value in ((self.margin_left, c.margin_left_cm), (self.margin_right, c.margin_right_cm),
                              (self.margin_top, c.margin_top_cm), (self.margin_bottom, c.margin_bottom_cm)):
            widget.setValue(convert_length(value, "cm", unit))
        self.title_editor.load(c.title); self.xlabel_editor.load(c.x_axis.label); self.latex_cb.setChecked(c.use_latex)
        self.top_spine_cb.setChecked(c.show_top_spine); self.bottom_spine_cb.setChecked(c.show_bottom_spine)
        self.left_spine_cb.setChecked(c.show_left_spine); self.right_spine_cb.setChecked(c.show_right_spine)
        names = self._curve_names()
        for combo in (self.text_curve_combo, self.curve_combo):
            combo.clear(); combo.addItems(names)
        if not self._initial_curve_applied and self.initial_curve_id:
            initial_index = next((index for index, curve in enumerate(c.curves) if curve.column == self.initial_curve_id), -1)
            if initial_index >= 0:
                self.curve_combo.setCurrentIndex(initial_index); self.text_curve_combo.setCurrentIndex(initial_index)
            self._initial_curve_applied = True
        for combo in (self.axis_combo, self.grid_axis_combo):
            combo.clear(); combo.addItem("X Axis")
            combo.addItems(["Y Axis"] if self.shared_y_axis else names)
        self.error_column.clear(); self.error_column.addItems(self.columns)
        l = c.legend; self.legend_cb.setChecked(l.visible); self.legend_loc.setCurrentText(l.location)
        self.anchor_cb.setChecked(l.custom_anchor); self.anchor_x.setValue(l.anchor_x); self.anchor_y.setValue(l.anchor_y)
        self.legend_cols.setValue(l.columns); self.frame_cb.setChecked(l.frame_visible); self.frame_edge.set_color(l.edge_color)
        self.frame_face.set_color(l.face_color); self.frame_alpha.setValue(l.frame_alpha); self.legend_font.load(l.font)
        self.dpi_spin.setValue(c.export_dpi)
        self._loading = False
        self._load_curve_text(); self._load_axis(); self._load_grid(); self._load_curve()

    def _unit_changed(self, unit):
        if self._loading or unit == self._last_unit: return
        from plot_config import convert_length
        for widget in (self.width_spin, self.height_spin, self.margin_left, self.margin_right, self.margin_top, self.margin_bottom):
            widget.setValue(convert_length(widget.value(), self._last_unit, unit))
        self._last_unit = unit

    def _save_overall(self):
        from plot_config import convert_length
        unit = self.unit_combo.currentText(); c = self.config; c.unit = unit
        c.width_cm = convert_length(self.width_spin.value(), unit, "cm"); c.height_cm = convert_length(self.height_spin.value(), unit, "cm")
        c.background = self.background_combo.currentText()
        c.show_top_spine = self.top_spine_cb.isChecked(); c.show_bottom_spine = self.bottom_spine_cb.isChecked()
        c.show_left_spine = self.left_spine_cb.isChecked(); c.show_right_spine = self.right_spine_cb.isChecked()
        c.margin_left_cm = convert_length(self.margin_left.value(), unit, "cm"); c.margin_right_cm = convert_length(self.margin_right.value(), unit, "cm")
        c.margin_top_cm = convert_length(self.margin_top.value(), unit, "cm"); c.margin_bottom_cm = convert_length(self.margin_bottom.value(), unit, "cm")
        self.title_editor.save(c.title); self.xlabel_editor.save(c.x_axis.label); c.use_latex = self.latex_cb.isChecked()
        l = c.legend; l.visible = self.legend_cb.isChecked(); l.location = self.legend_loc.currentText(); l.custom_anchor = self.anchor_cb.isChecked()
        l.anchor_x = self.anchor_x.value(); l.anchor_y = self.anchor_y.value(); l.columns = self.legend_cols.value(); l.frame_visible = self.frame_cb.isChecked()
        l.edge_color = self.frame_edge.color(); l.face_color = self.frame_face.color(); l.frame_alpha = self.frame_alpha.value(); self.legend_font.save(l.font)
        c.export_dpi = self.dpi_spin.value()

    def _load_curve_text(self, *_):
        if self._loading: return
        if self.shared_y_axis:
            self._loading = True
            self.ylabel_editor.load(self.config.shared_y_axis.label)
            self.ytick_editor.load(self.config.shared_y_axis.tick.font)
            self.text_curve_combo.setVisible(False)
            self._loading = False
            return
        if self.text_curve_combo.currentIndex() < 0: return
        self._loading = True; curve = self.config.curves[self.text_curve_combo.currentIndex()]
        self.ylabel_editor.load(curve.axis.label); self.ytick_editor.load(curve.axis.tick.font); self._loading = False

    def _save_curve_text(self):
        if self._loading: return
        if self.shared_y_axis:
            self.ylabel_editor.save(self.config.shared_y_axis.label)
            self.ytick_editor.save(self.config.shared_y_axis.tick.font)
            return
        if self.text_curve_combo.currentIndex() < 0: return
        curve = self.config.curves[self.text_curve_combo.currentIndex()]
        self.ylabel_editor.save(curve.axis.label); self.ytick_editor.save(curve.axis.tick.font)

    def _load_axis(self, *_):
        if self._loading: return
        self._loading = True; a = self._axis_style(self.axis_combo); t = a.tick
        self.scale_combo.setCurrentText(a.scale); self.auto_range_cb.setChecked(a.auto_range); self.axis_min.setValue(a.minimum); self.axis_max.setValue(a.maximum); self.invert_cb.setChecked(a.inverted)
        self.major_cb.setChecked(t.major_visible); self.minor_cb.setChecked(t.minor_visible); self.tick_direction.setCurrentText(t.direction)
        self.tick_bottom_cb.setChecked(t.show_bottom); self.tick_top_cb.setChecked(t.show_top)
        self.tick_left_cb.setChecked(t.show_left); self.tick_right_cb.setChecked(t.show_right)
        self.major_length.setValue(t.major_length); self.minor_length.setValue(t.minor_length); self.tick_width.setValue(t.width); self.tick_color.set_color(t.color)
        self.format_combo.setCurrentText(t.format_mode); self.decimals_spin.setValue(t.decimals); self.manual_combo.setCurrentText(t.manual_mode); self.positions_edit.setText(t.positions)
        self.tick_start.setValue(t.start); self.tick_stop.setValue(t.stop); self.tick_step.setValue(t.step); self.spine_cb.setChecked(a.spine_visible); self.spine_width.setValue(a.spine_width); self.spine_color.set_color(a.spine_color); self.xtick_editor.load(t.font)
        self._loading = False

    def _save_axis(self, *_):
        if self._loading: return
        a = self._axis_style(self.axis_combo); t = a.tick
        a.scale = self.scale_combo.currentText(); a.auto_range = self.auto_range_cb.isChecked(); a.minimum = self.axis_min.value(); a.maximum = self.axis_max.value(); a.inverted = self.invert_cb.isChecked()
        t.major_visible = self.major_cb.isChecked(); t.minor_visible = self.minor_cb.isChecked(); t.direction = self.tick_direction.currentText(); t.major_length = self.major_length.value(); t.minor_length = self.minor_length.value(); t.width = self.tick_width.value(); t.color = self.tick_color.color()
        t.show_bottom = self.tick_bottom_cb.isChecked(); t.show_top = self.tick_top_cb.isChecked()
        t.show_left = self.tick_left_cb.isChecked(); t.show_right = self.tick_right_cb.isChecked()
        t.format_mode = self.format_combo.currentText(); t.decimals = self.decimals_spin.value(); t.manual_mode = self.manual_combo.currentText(); t.positions = self.positions_edit.text(); t.start = self.tick_start.value(); t.stop = self.tick_stop.value(); t.step = self.tick_step.value(); self.xtick_editor.save(t.font)
        a.spine_visible = self.spine_cb.isChecked(); a.spine_width = self.spine_width.value(); a.spine_color = self.spine_color.color()

    def _load_grid(self, *_):
        if self._loading: return
        self._loading = True; g = self._axis_style(self.grid_axis_combo).grid
        self.grid_cb.setChecked(g.visible); self.grid_color.set_color(g.color); self.grid_line.setCurrentText(g.linestyle); self.grid_width.setValue(g.linewidth); self.grid_alpha.setValue(g.alpha); self._loading = False

    def _save_grid(self, *_):
        if self._loading: return
        g = self._axis_style(self.grid_axis_combo).grid; g.visible = self.grid_cb.isChecked(); g.color = self.grid_color.color(); g.linestyle = self.grid_line.currentText(); g.linewidth = self.grid_width.value(); g.alpha = self.grid_alpha.value()

    def _load_curve(self, *_):
        if self._loading or self.curve_combo.currentIndex() < 0: return
        self._loading = True; c = self.config.curves[self.curve_combo.currentIndex()]; e = c.error
        self.curve_position_label.setText(f"{self.curve_combo.currentIndex() + 1}/{len(self.config.curves)} (top first)")
        available = self.curve_columns.get(c.column, self.columns)
        self.error_column.clear(); self.error_column.addItems(available)
        self.curve_visible.setChecked(c.visible); self.legend_edit.setText(c.legend_text); self.line_color.set_color(c.color); self.line_width.setValue(c.linewidth); self.line_style.setCurrentText(c.linestyle)
        self.marker_combo.setCurrentText(c.marker); self.marker_size.setValue(c.markersize); self.marker_face.set_color(c.marker_face_color); self.marker_edge.set_color(c.marker_edge_color); self.marker_edge_width.setValue(c.marker_edge_width); self.mark_every.setValue(c.markevery)
        self.error_mode.setCurrentText(e.mode); self.error_source.setCurrentText(e.source); self.error_column.setCurrentText(e.column); self.error_constant.setValue(e.constant); self.error_every.setValue(e.every); self.capsize.setValue(e.capsize); self.capthick.setValue(e.capthick); self.error_width.setValue(e.linewidth); self.error_color.set_color(e.color); self.band_color.set_color(e.fill_color); self.band_alpha.setValue(e.fill_alpha); self._loading = False

    def _save_curve(self, *_):
        if self._loading or self.curve_combo.currentIndex() < 0: return
        c = self.config.curves[self.curve_combo.currentIndex()]; e = c.error
        c.visible = self.curve_visible.isChecked(); c.legend_text = self.legend_edit.text(); c.color = self.line_color.color(); c.linewidth = self.line_width.value(); c.linestyle = self.line_style.currentText(); c.marker = self.marker_combo.currentText(); c.markersize = self.marker_size.value(); c.marker_face_color = self.marker_face.color(); c.marker_edge_color = self.marker_edge.color(); c.marker_edge_width = self.marker_edge_width.value(); c.markevery = self.mark_every.value()
        e.mode = self.error_mode.currentText(); e.source = self.error_source.currentText(); e.column = self.error_column.currentText(); e.constant = self.error_constant.value(); e.every = self.error_every.value(); e.capsize = self.capsize.value(); e.capthick = self.capthick.value(); e.linewidth = self.error_width.value(); e.color = self.error_color.color(); e.fill_color = self.band_color.color(); e.fill_alpha = self.band_alpha.value()

    def _move_curve(self, delta):
        idx = self.curve_combo.currentIndex(); new = idx + delta
        if idx < 0 or new < 0 or new >= len(self.config.curves): return
        if self.config.curves[idx].side != self.config.curves[new].side: return
        self.config.curves[idx], self.config.curves[new] = self.config.curves[new], self.config.curves[idx]
        self._load_all(); self.curve_combo.setCurrentIndex(new)
        self._load_curve()

    def _validate(self):
        self._save_overall(); self._save_curve_text(); self._save_axis(); self._save_grid(); self._save_curve()
        c = self.config
        if c.width_cm <= c.margin_left_cm + c.margin_right_cm or c.height_cm <= c.margin_top_cm + c.margin_bottom_cm:
            QMessageBox.warning(self, "Invalid Figure", "Margins must leave a positive plotting area."); return False
        if self.shared_y_axis:
            a = c.shared_y_axis
            if not a.auto_range and a.minimum >= a.maximum:
                QMessageBox.warning(self, "Invalid Range", "Y Axis: minimum must be smaller than maximum."); return False
            if a.tick.manual_mode == "Start/Stop/Step" and a.tick.step <= 0:
                QMessageBox.warning(self, "Invalid Ticks", "Y Axis: tick step must be positive."); return False
        for curve in c.curves:
            if self.shared_y_axis:
                continue
            a = curve.axis
            if not a.auto_range and a.minimum >= a.maximum:
                QMessageBox.warning(self, "Invalid Range", f"{curve.column}: minimum must be smaller than maximum."); return False
            if a.tick.manual_mode == "Start/Stop/Step" and a.tick.step <= 0:
                QMessageBox.warning(self, "Invalid Ticks", f"{curve.column}: tick step must be positive."); return False
        return True

    def _apply(self):
        if self._validate(): self._apply_callback(self.config.copy())

    def _accept(self):
        if self._validate(): self._apply_callback(self.config.copy()); self.accept()

    def _save_format(self):
        if self._validate():
            self._save_format_callback(self.config.copy(), list(self.format_templates))

    def _load_format(self):
        if self._load_format_callback is None or not self._validate(): return
        loaded = self._load_format_callback(self.config.copy(), list(self.format_templates))
        if loaded is None: return
        self.config, self.format_templates = loaded
        self._last_unit = self.config.unit; self._load_all()

    def _restore_factory(self):
        old = [(c.column, c.side) for c in self.config.curves]
        self.config = FigureConfig()
        for i, (column, side) in enumerate(old): self.config.curves.append(new_curve(column, side, i))
        self._last_unit = self.config.unit; self._load_all()
