"""Responsive dataset editor card used by VTS Plotter."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListView, QMenu, QSizePolicy, QVBoxLayout, QWidget,
)


class OpaqueColumnComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        view = QListView(self)
        self.setView(view)
        view.setStyleSheet(
            "QListView{background:#ffffff;color:#000000;border:1px solid #9a9a9a;outline:0;}"
            "QListView::item{background:#ffffff;color:#000000;min-height:24px;padding:2px 8px;}"
            "QListView::item:hover{background:#e5f1fb;color:#000000;}"
            "QListView::item:selected{background:#1976d2;color:#ffffff;}"
        )
        self._make_popup_opaque()

    def _make_popup_opaque(self):
        view = self.view()
        viewport = view.viewport()
        palette = view.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Window, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#000000"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#1976d2"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        view.setPalette(palette)
        viewport.setPalette(palette)
        view.setAutoFillBackground(True)
        viewport.setAutoFillBackground(True)
        view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        viewport.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        view.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        viewport.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        popup = view.window()
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        popup.setAutoFillBackground(True)
        popup.setPalette(palette)
        popup.setStyleSheet("background:#ffffff;border:1px solid #9a9a9a;")

    def showPopup(self):
        self._make_popup_opaque()
        super().showPopup()


class VtsDatasetCard(QFrame):
    changed = Signal(str)
    activated = Signal(str)
    moveRequested = Signal(str, str)
    duplicateRequested = Signal(str)
    reloadRequested = Signal(str)
    removeRequested = Signal(str)

    def __init__(self, dataset, fields=None, available=True, parent=None):
        super().__init__(parent)
        self.dataset = dataset
        self.available = bool(available)
        self._active = False
        self._loading = True
        self.setObjectName("vtsDatasetCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 7)
        root.setSpacing(6)

        header = QHBoxLayout()
        root.addLayout(header)
        self.on_checkbox = QCheckBox("On")
        self.on_checkbox.setChecked(dataset.enabled and available)
        header.addWidget(self.on_checkbox)
        header.addStretch()
        self.position_label = QLabel("")
        self.position_label.setStyleSheet("color:#777;")
        header.addWidget(self.position_label)

        fields_widget = QWidget()
        fields_layout = QVBoxLayout(fields_widget)
        fields_layout.setContentsMargins(0, 0, 0, 0)
        fields_layout.setSpacing(5)

        self.label_edit = QLineEdit(dataset.label)
        self.file_label = QLabel(Path(dataset.path).name)
        self.file_label.setToolTip(dataset.path)
        self.file_label.setWordWrap(True)
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.field_combo = OpaqueColumnComboBox()
        if fields:
            self.field_combo.addItem("")
            self.field_combo.addItems(fields)
        else:
            self.field_combo.addItem("")
        idx = self.field_combo.findText(dataset.field_name)
        self.field_combo.setCurrentIndex(idx if idx >= 0 else 0)

        def make_field_box(title, widget):
            box = QWidget()
            layout = QVBoxLayout(box)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2)
            label = QLabel(title)
            label.setStyleSheet("color:#555;font-size:11px;")
            layout.addWidget(label)
            layout.addWidget(widget)
            return box

        fields_layout.addWidget(make_field_box("Label", self.label_edit))
        fields_layout.addWidget(make_field_box("File", self.file_label))
        fields_layout.addWidget(make_field_box("Data Field", self.field_combo))

        root.addWidget(fields_widget)

        for widget in (self, fields_widget, self.label_edit, self.file_label, self.field_combo):
            widget.installEventFilter(self)

        self.on_checkbox.stateChanged.connect(self._sync)
        self.label_edit.textChanged.connect(self._sync)
        self.field_combo.currentTextChanged.connect(self._on_field_changed)

        self._loading = False
        self.set_available(available)
        self._update_style()

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
        self.label_edit.setEnabled(self.available)
        self.field_combo.setEnabled(self.available)
        self._update_style()

    def set_position(self, index, total):
        self.position_label.setText(f"{index + 1}/{total}")

    def update_fields(self, fields):
        self._loading = True
        old = self.dataset.field_name
        self.field_combo.clear()
        self.field_combo.addItem("")
        self.field_combo.addItems(fields)
        value = old if old in fields else ""
        idx = self.field_combo.findText(value)
        self.field_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.dataset.field_name = value
        self._loading = False
        self.changed.emit(self.dataset_id)

    def _sync(self, *_):
        if self._loading:
            return
        self.dataset.enabled = self.is_checked()
        self.dataset.label = self.label_edit.text().strip() or Path(self.dataset.path).stem

    def _on_field_changed(self, text):
        if self._loading:
            return
        self.dataset.field_name = text
        self.changed.emit(self.dataset_id)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.FocusIn):
            self.activated.emit(self.dataset_id)
        return super().eventFilter(watched, event)

    def _update_style(self):
        if not self.available:
            border, background = "#d9534f", "#fff1f1"
        elif self._active:
            border, background = "#1976d2", "#eef6ff"
        else:
            border, background = "#bdbdbd", "#ffffff"
        self.setStyleSheet(
            f"QFrame#vtsDatasetCard{{border:2px solid {border};border-radius:5px;background:{background};}}"
            "QFrame#vtsDatasetCard QFrame{border:none;}"
        )

    def _show_menu(self, pos):
        menu = QMenu(self)
        up = menu.addAction("Move Up")
        down = menu.addAction("Move Down")
        top = menu.addAction("Move to Top")
        bottom = menu.addAction("Move to Bottom")
        menu.addSeparator()
        duplicate_action = menu.addAction("Duplicate Dataset")
        reload_action = menu.addAction("Reload This VTS")
        remove_action = menu.addAction("Remove This VTS")
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
