"""Responsive dataset editor card used by CSV Plotter."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListView, QMenu, QSizePolicy, QVBoxLayout, QWidget,
)


class OpaqueColumnComboBox(QComboBox):
    """Column selector with a fully opaque popup on Windows native styles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        view = QListView(self); self.setView(view)
        view.setStyleSheet(
            "QListView{background:#ffffff;color:#000000;border:1px solid #9a9a9a;outline:0;}"
            "QListView::item{background:#ffffff;color:#000000;min-height:24px;padding:2px 8px;}"
            "QListView::item:hover{background:#e5f1fb;color:#000000;}"
            "QListView::item:selected{background:#1976d2;color:#ffffff;}"
        )
        self._make_popup_opaque()

    def _make_popup_opaque(self):
        view = self.view(); viewport = view.viewport()
        palette = view.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Window, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#000000"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#1976d2"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        view.setPalette(palette); viewport.setPalette(palette)
        view.setAutoFillBackground(True); viewport.setAutoFillBackground(True)
        view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        viewport.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        view.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        viewport.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        popup = view.window()
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        popup.setAutoFillBackground(True); popup.setPalette(palette)
        popup.setStyleSheet("background:#ffffff;border:1px solid #9a9a9a;")

    def showPopup(self):
        self._make_popup_opaque()
        super().showPopup()


class DatasetControlCard(QFrame):
    changed = Signal(str)
    activated = Signal(str)
    moveRequested = Signal(str, str)
    duplicateRequested = Signal(str)
    reloadRequested = Signal(str)
    removeRequested = Signal(str)

    def __init__(self, dataset, columns=None, available=True, parent=None):
        super().__init__(parent)
        self.dataset = dataset
        self.available = bool(available)
        self._active = False
        self._loading = True
        self.layout_columns = 1
        self.setObjectName("datasetCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

        root = QVBoxLayout(self); root.setContentsMargins(8, 6, 8, 7); root.setSpacing(6)
        header = QHBoxLayout(); root.addLayout(header)
        self.on_checkbox = QCheckBox("On"); self.on_checkbox.setChecked(dataset.enabled and available)
        header.addWidget(self.on_checkbox); header.addStretch()
        self.position_label = QLabel(""); self.position_label.setStyleSheet("color:#777;"); header.addWidget(self.position_label)

        self.fields_widget = QWidget(); self.fields_layout = QGridLayout(self.fields_widget)
        self.fields_layout.setContentsMargins(0, 0, 0, 0); self.fields_layout.setHorizontalSpacing(8); self.fields_layout.setVerticalSpacing(5)
        root.addWidget(self.fields_widget)

        self.label_edit = QLineEdit(dataset.label)
        self.file_label = QLabel(Path(dataset.path).name); self.file_label.setToolTip(dataset.path)
        self.file_label.setWordWrap(True); self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.x2d_combo = self._column_combo(columns, dataset.x2d)
        self.y2d_combo = self._column_combo(columns, dataset.y2d)
        self.x3d_combo = self._column_combo(columns, dataset.x3d)
        self.y3d_combo = self._column_combo(columns, dataset.y3d)
        self.z3d_combo = self._column_combo(columns, dataset.z3d)
        self._field_specs = [
            ("Label", self.label_edit), ("File", self.file_label),
            ("2D X", self.x2d_combo), ("2D Y", self.y2d_combo),
            ("3D X", self.x3d_combo), ("3D Y", self.y3d_combo), ("3D Z", self.z3d_combo),
        ]
        self._field_boxes = [self._make_field(label, widget) for label, widget in self._field_specs]
        for widget in (self, self.fields_widget, self.label_edit, self.file_label, self.x2d_combo,
                       self.y2d_combo, self.x3d_combo, self.y3d_combo, self.z3d_combo):
            widget.installEventFilter(self)
        self.on_checkbox.stateChanged.connect(self._sync)
        self.label_edit.textChanged.connect(self._sync)
        for combo in (self.x2d_combo, self.y2d_combo, self.x3d_combo, self.y3d_combo, self.z3d_combo):
            combo.currentTextChanged.connect(self._sync)
        self._loading = False
        self.set_available(available)
        self._reflow(520)

    @staticmethod
    def _make_field(label, widget):
        box = QWidget(); layout = QVBoxLayout(box); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(2)
        title = QLabel(label); title.setStyleSheet("color:#555;font-size:11px;")
        layout.addWidget(title); layout.addWidget(widget)
        return box

    @staticmethod
    def _column_combo(columns, selected):
        combo = OpaqueColumnComboBox(); combo.addItem(""); combo.addItems([str(value) for value in (columns or [])])
        combo.setCurrentText(selected if selected in [str(value) for value in (columns or [])] else "")
        return combo

    @property
    def dataset_id(self):
        return self.dataset.dataset_id

    def is_checked(self):
        return self.available and self.on_checkbox.isChecked()

    def set_checked(self, checked):
        self.on_checkbox.setChecked(bool(checked) and self.available)

    def set_active(self, active):
        self._active = bool(active)
        self._update_style()

    def set_available(self, available):
        self.available = bool(available)
        if not self.available:
            self.on_checkbox.setChecked(False)
        self.on_checkbox.setEnabled(self.available)
        for _, widget in self._field_specs:
            if widget is not self.file_label:
                widget.setEnabled(self.available)
        self._update_style()

    def set_position(self, index, total):
        self.position_label.setText(f"{index + 1}/{total}")

    def update_columns(self, columns):
        columns = [str(value) for value in columns]
        self._loading = True
        for combo, attr in ((self.x2d_combo, "x2d"), (self.y2d_combo, "y2d"),
                            (self.x3d_combo, "x3d"), (self.y3d_combo, "y3d"), (self.z3d_combo, "z3d")):
            old = getattr(self.dataset, attr)
            combo.clear(); combo.addItem(""); combo.addItems(columns)
            value = old if old in columns else ""
            combo.setCurrentText(value); setattr(self.dataset, attr, value)
        self._loading = False
        self.changed.emit(self.dataset_id)

    def _sync(self, *_):
        if self._loading:
            return
        self.dataset.enabled = self.is_checked()
        self.dataset.label = self.label_edit.text().strip() or Path(self.dataset.path).stem
        self.dataset.x2d = self.x2d_combo.currentText(); self.dataset.y2d = self.y2d_combo.currentText()
        self.dataset.x3d = self.x3d_combo.currentText(); self.dataset.y3d = self.y3d_combo.currentText(); self.dataset.z3d = self.z3d_combo.currentText()
        self.changed.emit(self.dataset_id)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.FocusIn):
            self.activated.emit(self.dataset_id)
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow(event.size().width())

    def _reflow(self, width):
        columns = 3 if width >= 760 else 2 if width >= 460 else 1
        if columns == self.layout_columns and self.fields_layout.count() == len(self._field_boxes):
            return
        self.layout_columns = columns
        for box in self._field_boxes:
            self.fields_layout.removeWidget(box)
        for index, box in enumerate(self._field_boxes):
            self.fields_layout.addWidget(box, index // columns, index % columns)
        for column in range(3):
            self.fields_layout.setColumnStretch(column, 1 if column < columns else 0)
        self.updateGeometry()

    def _update_style(self):
        if not self.available:
            border, background = "#d9534f", "#fff1f1"
        elif self._active:
            border, background = "#1976d2", "#eef6ff"
        else:
            border, background = "#bdbdbd", "#ffffff"
        self.setStyleSheet(
            f"QFrame#datasetCard{{border:2px solid {border};border-radius:5px;background:{background};}}"
            "QFrame#datasetCard QFrame{border:none;}"
        )

    def _show_menu(self, pos):
        menu = QMenu(self)
        up = menu.addAction("Move Up"); down = menu.addAction("Move Down")
        top = menu.addAction("Move to Top"); bottom = menu.addAction("Move to Bottom")
        menu.addSeparator(); duplicate_action = menu.addAction("Duplicate Dataset")
        reload_action = menu.addAction("Reload This CSV")
        remove_action = menu.addAction("Remove This CSV")
        action = menu.exec(self.mapToGlobal(pos))
        mapping = {up: "up", down: "down", top: "top", bottom: "bottom"}
        if action in mapping:
            self.moveRequested.emit(self.dataset_id, mapping[action])
        elif action == duplicate_action:
            self.duplicateRequested.emit(self.dataset_id)
        elif action == reload_action:
            self.reloadRequested.emit(self.dataset_id)
        elif action == remove_action:
            self.removeRequested.emit(self.dataset_id)
