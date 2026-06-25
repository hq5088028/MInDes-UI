"""Multi-file 2D/3D CSV plotting dialog."""
from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import vtk
from PySide6.QtCore import Qt, QSettings, QSignalBlocker
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QScrollArea, QSplitter, QTabWidget, QVBoxLayout,
    QWidget, QSizePolicy,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from plot_config import FigureConfig, new_curve
from plot_property_dialog import PlotPropertyDialog
from .models import CsvDatasetConfig, CsvPlotterState, VtkPlotConfig, dataset_display_name, load_csv, numeric_series
from .dataset_card import DatasetControlCard
from .rendering import render_shared_figure
from .style_formats import (
    apply_2d_visual_style, apply_3d_visual_style, apply_curve_template,
    apply_dataset_template, make_2d_style_payload, make_3d_style_payload,
    parse_2d_style_payload, parse_3d_style_payload, sanitize_curve_template,
    sanitize_dataset_template,
)
from .vtk_properties import VtkPropertyDialog
from .vtk_utils import build_cube_axes_bundle, build_scatter, build_surface_with_holes, hex_to_rgb, make_lookup_table


STATE_KEY = "csv_plotter/state_v1"
UI_STATE_KEY = "csv_plotter/ui_v2"
STYLE_2D_KEY = "csv_plotter/visual_2d_v1"
STYLE_3D_KEY = "csv_plotter/visual_3d_v1"
class CSVPlotterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CSV Plotter")
        self.setWindowFlag(Qt.WindowType.Window, True)
        self._set_size(parent)
        self.settings = QSettings("MInDes", "MInDes-UI")
        self._migrate_legacy_state()
        self.state = self._load_state()
        self.figure_config, self._curve_style_templates = self._load_2d_visual_style()
        self.vtk_config, self._dataset_style_templates = self._load_3d_visual_style()
        self.frames: dict[str, pd.DataFrame] = {}
        self.cards: list[DatasetControlCard] = []
        self._select_all_loading = False
        self._closing = False
        self._build_ui()
        self._restore_datasets()

    def _set_size(self, parent):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        if parent is not None:
            geo = parent.geometry(); width = max(1100, min(int(geo.width() * .95), screen.width() - 30)); height = max(760, min(int(geo.height() * .95), screen.height() - 50))
            self.resize(width, height); self.move(max(screen.x(), geo.x() + (geo.width() - width) // 2), max(screen.y(), geo.y() + (geo.height() - height) // 2))
        else:
            self.resize(max(1100, int(screen.width() * .8)), max(760, int(screen.height() * .8)))

    def _load_state(self):
        try:
            raw = json.loads(self.settings.value(UI_STATE_KEY, "{}", type=str))
        except (TypeError, ValueError, json.JSONDecodeError):
            raw = {}
        sizes = raw.get("splitter_sizes", []) if isinstance(raw, dict) else []
        return CsvPlotterState(splitter_sizes=[int(value) for value in sizes if isinstance(value, (int, float))])

    def _migrate_legacy_state(self):
        try: legacy_raw = json.loads(self.settings.value(STATE_KEY, "{}", type=str))
        except (TypeError, ValueError, json.JSONDecodeError): legacy_raw = {}
        legacy = CsvPlotterState.from_dict(legacy_raw)
        if not self.settings.contains(STYLE_2D_KEY):
            figure = FigureConfig.from_dict(legacy.figure)
            if not legacy.figure:
                try: figure = FigureConfig.from_dict(json.loads(self.settings.value("csv_plotter/default_2d_v1", "{}", type=str)))
                except (TypeError, ValueError, json.JSONDecodeError): pass
            self.settings.setValue(STYLE_2D_KEY, json.dumps(make_2d_style_payload(figure), ensure_ascii=False))
        if not self.settings.contains(STYLE_3D_KEY):
            ordered = {item.dataset_id: item for item in legacy.datasets}
            datasets = [ordered[value] for value in legacy.render_order_3d if value in ordered]
            self.settings.setValue(STYLE_3D_KEY, json.dumps(make_3d_style_payload(legacy.vtk, datasets), ensure_ascii=False))
        self.settings.remove(STATE_KEY); self.settings.remove("csv_plotter/default_2d_v1")

    def _load_2d_visual_style(self):
        try:
            raw = json.loads(self.settings.value(STYLE_2D_KEY, "{}", type=str))
            style, templates = parse_2d_style_payload(raw)
            return apply_2d_visual_style(FigureConfig(), style, templates), templates
        except (TypeError, ValueError, json.JSONDecodeError):
            return FigureConfig(), []

    def _load_3d_visual_style(self):
        try:
            raw = json.loads(self.settings.value(STYLE_3D_KEY, "{}", type=str))
            style, templates = parse_3d_style_payload(raw)
            return apply_3d_visual_style(VtkPlotConfig(), style), templates
        except (TypeError, ValueError, json.JSONDecodeError):
            return VtkPlotConfig(), []

    def _persist_2d_visual_style(self, templates=None):
        templates = list(templates if templates is not None else self._curve_style_templates)
        self._curve_style_templates = [sanitize_curve_template(value) for value in templates]
        payload = make_2d_style_payload(self.figure_config, self._curve_style_templates)
        self.settings.setValue(STYLE_2D_KEY, json.dumps(payload, ensure_ascii=False))

    def _persist_3d_visual_style(self, templates=None):
        templates = list(templates if templates is not None else self._dataset_style_templates)
        self._dataset_style_templates = [sanitize_dataset_template(value) for value in templates]
        payload = make_3d_style_payload(self.vtk_config, templates=self._dataset_style_templates)
        self.settings.setValue(STYLE_3D_KEY, json.dumps(payload, ensure_ascii=False))

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(6, 6, 6, 6)
        self.splitter = QSplitter(Qt.Orientation.Horizontal); root.addWidget(self.splitter, 1)
        left = QWidget(); left_layout = QVBoxLayout(left); left_layout.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout(); left_layout.addLayout(controls)
        self.select_all = QCheckBox("Select All"); self.select_all.setTristate(True)
        self.select_all.clicked.connect(self._toggle_select_all); controls.addWidget(self.select_all)
        controls.addStretch()
        self.cards_scroll = QScrollArea(); self.cards_scroll.setWidgetResizable(True)
        self.cards_container = QWidget(); self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(2, 2, 4, 2); self.cards_layout.setSpacing(7); self.cards_layout.addStretch()
        self.cards_scroll.setWidget(self.cards_container); left_layout.addWidget(self.cards_scroll, 1)
        data_buttons = QHBoxLayout(); data_buttons.setContentsMargins(0, 0, 0, 0); left_layout.addLayout(data_buttons)
        self.data_action_buttons = []
        for text, slot in (("Add", self.add_csv), ("Remove", self.remove_selected),
                           ("Reload", self.reload_selected)):
            button = QPushButton(text); button.clicked.connect(slot)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            data_buttons.addWidget(button, 1); self.data_action_buttons.append(button)
        data_minimum = max(button.minimumSizeHint().width() for button in self.data_action_buttons)
        for button in self.data_action_buttons: button.setMinimumWidth(data_minimum)
        right = QWidget(); right_layout = QVBoxLayout(right); right_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(); right_layout.addWidget(self.tabs, 1)
        self._build_2d_tab(); self._build_3d_tab()
        self.splitter.addWidget(left); self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 0); self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes(self.state.splitter_sizes or [420, 780])
        self.splitter.splitterMoved.connect(lambda *_: self._save_state())
        self.status = QLabel("Add one or more CSV files to begin.")
        self.status.setStyleSheet("background:#f0f0f0;padding:4px;border-top:1px solid #bbb;")
        root.addWidget(self.status)

    def _build_2d_tab(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0)
        self.figure = Figure(figsize=(6.3, 3.94), dpi=100); self.canvas = FigureCanvas(self.figure)
        layout.addWidget(NavigationToolbar(self.canvas, page))
        self.plot_scroll = QScrollArea(); self.plot_scroll.setWidgetResizable(False); self.plot_scroll.setAlignment(Qt.AlignCenter); self.plot_scroll.setWidget(self.canvas)
        layout.addWidget(self.plot_scroll, 1)
        buttons = QHBoxLayout(); layout.addLayout(buttons)
        for text, slot in (("Draw 2D", self.draw_2d), ("Property", self.open_2d_property), ("Export Figure", self.export_2d)):
            button = QPushButton(text); button.clicked.connect(slot); buttons.addWidget(button)
        buttons.addStretch(); self.tabs.addTab(page, "2D Plot")
        self._apply_canvas_size()

    def _build_3d_tab(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0)
        self.vtk_widget = QVTKRenderWindowInteractor(page); layout.addWidget(self.vtk_widget, 1)
        self.renderer = vtk.vtkRenderer(); self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
        self.iren = self.vtk_widget.GetRenderWindow().GetInteractor(); self.iren.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera()); self.iren.Initialize()
        self.axes = vtk.vtkCubeAxesActor(); self.axes.SetCamera(self.renderer.GetActiveCamera()); self.axes_bundle = None
        self.scalarbar = vtk.vtkScalarBarActor(); self.scalarbar.SetNumberOfLabels(5); self.scalarbar.SetPosition(.86, .15); self.scalarbar.SetWidth(.1); self.scalarbar.SetHeight(.7)
        self._build_3d_action_buttons(layout)
        self.tabs.addTab(page, "3D Plot")

    def _build_3d_action_buttons(self, layout):
        buttons = QGridLayout(); buttons.setContentsMargins(0, 0, 0, 0); layout.addLayout(buttons)
        actions = [
            ("Draw 3D", self.draw_3d, 0, 0), ("Property", self.open_3d_property, 0, 1),
            ("Screenshot", self.save_screenshot, 0, 3), ("Reset", self.reset_view, 1, 0),
            ("View X", lambda: self.view_axis("X"), 1, 1), ("View Y", lambda: self.view_axis("Y"), 1, 2),
            ("View Z", lambda: self.view_axis("Z"), 1, 3),
        ]
        self.view_action_buttons = []
        for text, slot, row, column in actions:
            button = QPushButton(text); button.clicked.connect(slot)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            buttons.addWidget(button, row, column); self.view_action_buttons.append(button)
        view_minimum = max(button.minimumSizeHint().width() for button in self.view_action_buttons)
        for button in self.view_action_buttons: button.setMinimumWidth(view_minimum)
        for column in range(4): buttons.setColumnStretch(column, 1)

    def _restore_datasets(self):
        for dataset in self.state.datasets:
            if Path(dataset.path).is_file():
                try:
                    self.frames[dataset.dataset_id] = load_csv(dataset.path)
                except Exception as exc:
                    self.status.setText(f"Failed to restore {dataset.path}: {exc}")
            self._append_card(dataset)
        valid_ids = {d.dataset_id for d in self.state.datasets}
        if self.state.active_dataset_id not in valid_ids:
            self.state.active_dataset_id = self.state.datasets[0].dataset_id if self.state.datasets else ""
        self._refresh_cards()
        self._sync_figure_curves()

    def add_csv(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add CSV files", "", "CSV files (*.csv);;All files (*)")
        for path in paths:
            try:
                frame = load_csv(path)
            except Exception as exc:
                QMessageBox.warning(self, "CSV Error", f"Failed to read {path}:\n{exc}"); continue
            absolute_path = os.path.abspath(path)
            dataset = CsvDatasetConfig(
                path=absolute_path,
                label=self._unique_dataset_label(Path(path).stem, absolute_path))
            palette = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf"]
            dataset.color = palette[len(self.state.datasets) % len(palette)]
            if len(self.state.datasets) < len(self._dataset_style_templates):
                dataset = apply_dataset_template(dataset, self._dataset_style_templates[len(self.state.datasets)])
            self.state.datasets.append(dataset); self.frames[dataset.dataset_id] = frame
            self.state.render_order_2d.append(dataset.dataset_id); self.state.render_order_3d.append(dataset.dataset_id)
            self._append_card(dataset); self._activate_dataset(dataset.dataset_id)
        if paths:
            self._sync_figure_curves(); self._refresh_cards(); self._save_state()

    def _unique_dataset_label(self, requested, source_path=""):
        labels = {item.label for item in self.state.datasets}
        base = str(requested).strip() or Path(source_path).stem or "dataset"
        prefix, separator, suffix = base.rpartition("-")
        if separator and suffix.isdigit() and int(suffix) >= 2 and source_path:
            normalized = os.path.normcase(os.path.abspath(source_path))
            same_path_labels = {
                item.label for item in self.state.datasets
                if os.path.normcase(os.path.abspath(item.path)) == normalized
            }
            if prefix in same_path_labels:
                base = prefix
        if base not in labels:
            return base
        number = 2
        while f"{base}-{number}" in labels:
            number += 1
        return f"{base}-{number}"

    def _append_card(self, dataset, index=None):
        frame = self.frames.get(dataset.dataset_id)
        columns = [str(value) for value in frame.columns] if frame is not None else []
        card = DatasetControlCard(dataset, columns, frame is not None, self.cards_container)
        card.changed.connect(self._card_changed); card.activated.connect(self._activate_dataset)
        card.moveRequested.connect(self._move_card); card.reloadRequested.connect(self.reload_dataset)
        card.duplicateRequested.connect(self.duplicate_dataset)
        card.removeRequested.connect(lambda dataset_id: self.remove_dataset(dataset_id, True))
        if index is None:
            index = len(self.cards)
        index = max(0, min(int(index), len(self.cards)))
        self.cards.insert(index, card); self.cards_layout.insertWidget(index, card)

    @staticmethod
    def _insert_above_source(order, source_id, duplicate_id):
        result = [value for value in order if value != duplicate_id]
        index = result.index(source_id) if source_id in result else len(result)
        result.insert(index, duplicate_id)
        return result

    def duplicate_dataset(self, dataset_id):
        source = self._dataset_by_id(dataset_id)
        if source is None:
            return
        self._sync_figure_curves()
        duplicate = deepcopy(source)
        duplicate.dataset_id = CsvDatasetConfig().dataset_id
        duplicate.label = self._unique_dataset_label(source.label, source.path)
        source_index = self.state.datasets.index(source)
        self.state.datasets.insert(source_index + 1, duplicate)
        if dataset_id in self.frames:
            # Rendering treats frames as read-only. Reload replaces only the
            # selected dictionary entry, so the two datasets remain independent.
            self.frames[duplicate.dataset_id] = self.frames[dataset_id]
        self.state.render_order_2d = self._insert_above_source(
            self.state.render_order_2d, dataset_id, duplicate.dataset_id)
        self.state.render_order_3d = self._insert_above_source(
            self.state.render_order_3d, dataset_id, duplicate.dataset_id)
        source_curve = next(
            (curve for curve in self.figure_config.curves if curve.column == dataset_id), None)
        if source_curve is not None:
            duplicate_curve = deepcopy(source_curve)
            duplicate_curve.column = duplicate.dataset_id
            self.figure_config.curves.append(duplicate_curve)
        self._append_card(duplicate, source_index + 1)
        self.state.active_dataset_id = duplicate.dataset_id
        self._sync_figure_curves(); self._refresh_cards(); self._save_state()
        self.status.setText(
            f"Duplicated {dataset_display_name(source)} as {dataset_display_name(duplicate)}.")

    def _dataset_by_id(self, dataset_id):
        return next((item for item in self.state.datasets if item.dataset_id == dataset_id), None)

    def _selected_dataset(self):
        return self._dataset_by_id(self.state.active_dataset_id)

    def _card_changed(self, _dataset_id=""):
        self._sync_figure_curves(); self._update_select_all(); self._save_state()

    def _activate_dataset(self, dataset_id):
        if self._dataset_by_id(dataset_id) is None: return
        self.state.active_dataset_id = dataset_id; self._refresh_cards(); self._save_state()

    def _refresh_cards(self):
        total = len(self.cards)
        for index, card in enumerate(self.cards):
            card.set_position(index, total); card.set_active(card.dataset_id == self.state.active_dataset_id)
        self._update_select_all()

    def _update_select_all(self):
        available = [card for card in self.cards if card.available]
        checked = sum(card.is_checked() for card in available)
        state = Qt.CheckState.Unchecked if not checked else Qt.CheckState.Checked if checked == len(available) else Qt.CheckState.PartiallyChecked
        with QSignalBlocker(self.select_all): self.select_all.setCheckState(state)

    def _toggle_select_all(self, *_):
        available = [card for card in self.cards if card.available]
        check = not available or not all(card.is_checked() for card in available)
        for card in available: card.set_checked(check)
        self._update_select_all(); self._save_state()

    def _move_card(self, dataset_id, action):
        index = next((i for i, card in enumerate(self.cards) if card.dataset_id == dataset_id), -1)
        if index < 0: return
        targets = {"up": max(0, index - 1), "down": min(len(self.cards) - 1, index + 1), "top": 0, "bottom": len(self.cards) - 1}
        target = targets.get(action, index)
        if target == index: return
        card = self.cards.pop(index); dataset = self.state.datasets.pop(index)
        self.cards.insert(target, card); self.state.datasets.insert(target, dataset)
        self.cards_layout.removeWidget(card); self.cards_layout.insertWidget(target, card)
        self._refresh_cards(); self._save_state()

    def remove_selected(self):
        selected = [dataset for dataset in self.state.datasets if dataset.enabled and dataset.dataset_id in self.frames]
        if not selected: self.status.setText("No On dataset is selected for removal."); return
        names = "\n".join(f"• {dataset_display_name(item)}" for item in selected)
        if QMessageBox.question(self, "Remove CSV", f"Remove these datasets?\n\n{names}") != QMessageBox.StandardButton.Yes: return
        for item in list(selected): self.remove_dataset(item.dataset_id, False)

    def reload_selected(self):
        targets = [dataset for dataset in self.state.datasets if dataset.enabled]
        if not targets: self.status.setText("No On dataset is selected for reload."); return
        errors = [message for item in targets if (message := self.reload_dataset(item.dataset_id, False))]
        if errors: QMessageBox.warning(self, "Reload CSV", "Some files could not be reloaded:\n\n" + "\n".join(errors))
        else: self.status.setText(f"Reloaded {len(targets)} dataset(s).")

    def reload_dataset(self, dataset_id, show_error=True):
        dataset = self._dataset_by_id(dataset_id)
        if dataset is None: return "Dataset no longer exists."
        try: frame = load_csv(dataset.path)
        except Exception as exc:
            message = f"{dataset_display_name(dataset)}: {exc}"
            if show_error: QMessageBox.warning(self, "CSV Error", message)
            return message
        self.frames[dataset_id] = frame
        card = next(card for card in self.cards if card.dataset_id == dataset_id)
        card.set_available(True); card.update_columns([str(value) for value in frame.columns])
        self._save_state(); return ""

    def remove_dataset(self, dataset_id, confirm=True):
        dataset = self._dataset_by_id(dataset_id)
        if dataset is None: return
        if confirm and QMessageBox.question(self, "Remove CSV", f"Remove {dataset_display_name(dataset)}?") != QMessageBox.StandardButton.Yes: return
        index = self.state.datasets.index(dataset); card = self.cards.pop(index); self.state.datasets.pop(index)
        self.cards_layout.removeWidget(card); card.deleteLater(); self.frames.pop(dataset_id, None)
        self.state.render_order_2d = [value for value in self.state.render_order_2d if value != dataset_id]
        self.state.render_order_3d = [value for value in self.state.render_order_3d if value != dataset_id]
        self.figure_config.curves = [curve for curve in self.figure_config.curves if curve.column != dataset_id]
        if self.state.active_dataset_id == dataset_id:
            self.state.active_dataset_id = self.state.datasets[0].dataset_id if self.state.datasets else ""
        self._refresh_cards(); self._save_state()

    def _sync_figure_curves(self):
        existing = {curve.column: curve for curve in self.figure_config.curves}; curves = []
        datasets = {dataset.dataset_id: dataset for dataset in self.state.datasets}
        order = [value for value in self.state.render_order_2d if value in datasets]
        order += [value for value in datasets if value not in order]
        self.state.render_order_2d = order
        for index, dataset_id in enumerate(order):
            dataset = datasets[dataset_id]
            curve = existing.get(dataset.dataset_id)
            if curve is None:
                curve = new_curve(dataset.dataset_id, "left", index); curve.color = dataset.color; curve.marker_edge_color = dataset.color
                curve.legend_text = dataset_display_name(dataset)
                if index < len(self._curve_style_templates):
                    curve = apply_curve_template(curve, self._curve_style_templates[index])
            curves.append(curve)
        self.figure_config.curves = curves

    def _series_2d(self):
        output = []
        datasets = {dataset.dataset_id: dataset for dataset in self.state.datasets}
        for dataset_id in reversed(self.state.render_order_2d):
            dataset = datasets.get(dataset_id)
            if dataset is None: continue
            frame = self.frames.get(dataset.dataset_id)
            if not dataset.enabled or frame is None or not dataset.x2d or not dataset.y2d: continue
            x, y = numeric_series(frame, dataset.x2d), numeric_series(frame, dataset.y2d)
            errors = {str(column): numeric_series(frame, str(column)) for column in frame.columns}
            output.append({"key": dataset.dataset_id, "label": dataset_display_name(dataset), "x": x, "y": y, "errors": errors})
        return output

    def draw_2d(self):
        series = self._series_2d()
        if not series:
            self.status.setText("No enabled dataset has complete 2D X/Y mappings."); return
        try:
            render_shared_figure(self.figure, self.figure_config, series); self._apply_canvas_size(); self.canvas.draw()
            self.status.setText(f"2D: rendered {len(series)} dataset(s); NaN/Inf values remain as gaps.")
        except Exception as exc:
            if self.figure_config.use_latex:
                self.figure_config.use_latex = False
                try: render_shared_figure(self.figure, self.figure_config, series); self.canvas.draw(); self.status.setText(f"LaTeX failed; using MathText: {exc}"); return
                except Exception: pass
            QMessageBox.warning(self, "2D Plot Error", str(exc))

    def _apply_canvas_size(self):
        width_in, height_in = self.figure_config.width_cm / 2.54, self.figure_config.height_cm / 2.54
        self.figure.set_size_inches(width_in, height_in, forward=False)
        screen = self.screen(); dpi = screen.logicalDotsPerInch() if screen else 96
        self.canvas.setFixedSize(max(100, round(width_in * dpi)), max(100, round(height_in * dpi)))

    def open_2d_property(self):
        self._sync_figure_curves()
        available = [d for d in self.state.datasets if d.enabled and d.dataset_id in self.frames]
        available_ids = {d.dataset_id for d in available}
        draft = self.figure_config.copy()
        curves = {curve.column: curve for curve in draft.curves}
        draft.curves = [curves[value] for value in self.state.render_order_2d if value in available_ids and value in curves]
        names = {d.dataset_id: dataset_display_name(d) for d in available}
        columns = {d.dataset_id: [str(c) for c in self.frames[d.dataset_id].columns] for d in available}
        initial = self.state.active_dataset_id if self.state.active_dataset_id in available_ids else (draft.curves[0].column if draft.curves else "")
        dialog = None
        def apply_config(config):
            active = config.curves[dialog.curve_combo.currentIndex()].column if config.curves and dialog.curve_combo.currentIndex() >= 0 else initial
            self._apply_2d_config(config, active, available_ids, dialog.format_templates)
        dialog = PlotPropertyDialog(draft, [], apply_config, self._save_2d_format_file,
                                    self, shared_y_axis=True, curve_names=names, curve_columns=columns,
                                    initial_curve_id=initial, load_format_callback=self._load_2d_format_file,
                                    format_templates=self._curve_style_templates)
        dialog.exec()

    def _apply_2d_config(self, config, active_id=None, edited_ids=None, format_templates=None):
        edited_ids = set(edited_ids or [curve.column for curve in config.curves])
        edited_order = [curve.column for curve in config.curves]
        edited = {curve.column: curve for curve in config.curves}
        previous = {curve.column: curve for curve in self.figure_config.curves}
        config.curves = [edited.get(value, previous.get(value)) for value in self.state.render_order_2d if edited.get(value, previous.get(value)) is not None]
        self.figure_config = config
        iterator = iter(edited_order)
        self.state.render_order_2d = [next(iterator) if value in edited_ids else value for value in self.state.render_order_2d]
        curve_map = {curve.column: curve for curve in self.figure_config.curves}
        self.figure_config.curves = [curve_map[value] for value in self.state.render_order_2d if value in curve_map]
        if active_id: self._activate_dataset(active_id)
        template_source = [edited[value] for value in edited_order if value in edited] or list(format_templates or self._curve_style_templates)
        self._persist_2d_visual_style(template_source)
        self.draw_2d(); self._save_state()

    def _save_2d_format_file(self, config, format_templates):
        path, _ = QFileDialog.getSaveFileName(self, "Save 2D Plot Format", "", "MInDes 2D style (*.mindes2dstyle.json)")
        if not path: return
        if not path.lower().endswith(".mindes2dstyle.json"): path += ".mindes2dstyle.json"
        templates = config.curves or format_templates or self._curve_style_templates
        try: Path(path).write_text(json.dumps(make_2d_style_payload(config, templates), ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc: QMessageBox.warning(self, "Save Format", str(exc)); return
        self.status.setText(f"Saved 2D plot format: {Path(path).name}")

    def _load_2d_format_file(self, current, _format_templates):
        path, _ = QFileDialog.getOpenFileName(self, "Load 2D Plot Format", "", "MInDes 2D style (*.mindes2dstyle.json);;JSON files (*.json)")
        if not path: return None
        try:
            style, templates = parse_2d_style_payload(json.loads(Path(path).read_text(encoding="utf-8")))
            return apply_2d_visual_style(current, style, templates), templates
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Load Format", str(exc)); return None

    def export_2d(self):
        if not self.figure.axes: self.draw_2d()
        if not self.figure.axes: return
        path, selected = QFileDialog.getSaveFileName(self, "Export 2D Figure", "", "PNG (*.png);;JPEG (*.jpg);;TIFF (*.tif *.tiff);;PDF (*.pdf);;SVG (*.svg)")
        if not path: return
        ext = {"PNG (*.png)": ".png", "JPEG (*.jpg)": ".jpg", "TIFF (*.tif *.tiff)": ".tif", "PDF (*.pdf)": ".pdf", "SVG (*.svg)": ".svg"}.get(selected, ".png")
        if not Path(path).suffix: path += ext
        transparent = self.figure_config.background == "Transparent"
        self.figure.savefig(path, dpi=self.figure_config.export_dpi, transparent=transparent, facecolor="none" if transparent else "white")
        self.status.setText(f"Saved 2D figure: {Path(path).name}")

    def _configured_3d(self):
        items = []
        datasets = {dataset.dataset_id: dataset for dataset in self.state.datasets}
        for dataset_id in reversed(self.state.render_order_3d):
            dataset = datasets.get(dataset_id)
            if dataset is None: continue
            frame = self.frames.get(dataset.dataset_id)
            if not dataset.enabled or frame is None or not all((dataset.x3d, dataset.y3d, dataset.z3d)): continue
            items.append((dataset, numeric_series(frame, dataset.x3d), numeric_series(frame, dataset.y3d), numeric_series(frame, dataset.z3d)))
        return items

    def draw_3d(self):
        items = self._configured_3d()
        if not items: self.status.setText("No enabled dataset has complete 3D X/Y/Z mappings."); return
        self.renderer.RemoveAllViewProps(); cfg = self.vtk_config
        arrays = []
        for _, x, y, z in items:
            valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
            if valid.any(): arrays.append(np.column_stack([x[valid], y[valid], z[valid]]))
        if not arrays: self.status.setText("No finite 3D points are available."); return
        union = np.vstack(arrays); raw_min = np.nanmin(union, axis=0); raw_max = np.nanmax(union, axis=0)
        if not cfg.auto_bounds:
            raw_min = np.array([cfg.x_min, cfg.y_min, cfg.z_min]); raw_max = np.array([cfg.x_max, cfg.y_max, cfg.z_max])
        span = np.where(raw_max > raw_min, raw_max - raw_min, 1.0)
        factors = np.array([cfg.x_scale, cfg.y_scale, cfg.z_scale], float)
        scale = factors / span if cfg.auto_normalize else factors
        transform = lambda points: (np.asarray(points) - raw_min) * scale
        fallback_messages = []
        lut_by_id = {}
        actor_entries = []
        for dataset, x, y, z in items:
            if not cfg.auto_bounds:
                in_range = ((x >= raw_min[0]) & (x <= raw_max[0]) & (y >= raw_min[1]) & (y <= raw_max[1]) &
                            (~np.isfinite(z) | ((z >= raw_min[2]) & (z <= raw_max[2]))))
                x = np.where(in_range, x, np.nan); y = np.where(in_range, y, np.nan); z = np.where(in_range, z, np.nan)
            mode = dataset.mode3d
            if mode == "Scatter": poly = build_scatter(x, y, z, transform)
            else:
                result = build_surface_with_holes(x, y, z, transform)
                if result.polydata is None:
                    poly = build_scatter(x, y, z, transform); fallback_messages.append(f"{dataset.label}: {result.reason}; Scatter used")
                    mode = "Scatter"
                else: poly = result.polydata
            mapper = vtk.vtkPolyDataMapper(); mapper.SetInputData(poly)
            valid_z = z[np.isfinite(z)]
            if dataset.color_mode == "Z Colormap" and len(valid_z):
                value_range = (float(np.min(valid_z)), float(np.max(valid_z))) if dataset.auto_color_range else (dataset.color_min, dataset.color_max)
                lut = make_lookup_table(dataset.colormap, value_range); mapper.SetLookupTable(lut); mapper.SetScalarRange(*value_range); mapper.ScalarVisibilityOn(); lut_by_id[dataset.dataset_id] = lut
            else: mapper.ScalarVisibilityOff()
            actor = vtk.vtkActor(); actor.SetMapper(mapper); actor.GetProperty().SetOpacity(dataset.opacity)
            actor.GetProperty().SetColor(*hex_to_rgb(dataset.color))
            if mode == "Scatter": actor.GetProperty().SetRepresentationToPoints(); actor.GetProperty().SetPointSize(dataset.point_size)
            elif mode == "Mesh": actor.GetProperty().EdgeVisibilityOn(); actor.GetProperty().SetEdgeColor(*hex_to_rgb(dataset.mesh_color)); actor.GetProperty().SetLineWidth(dataset.mesh_width)
            self.renderer.AddActor(actor); actor_entries.append((dataset, poly))
        display_max = (raw_max - raw_min) * scale
        self._add_axes((0, display_max[0], 0, display_max[1], 0, display_max[2]), raw_min, raw_max)
        self._add_active_scalarbar(lut_by_id)
        self._add_legend(actor_entries)
        self.renderer.SetBackground(*self._background_rgb(cfg.background)); self.renderer.ResetCamera(); self.renderer.ResetCameraClippingRange(); self.vtk_widget.GetRenderWindow().Render()
        text = f"3D: rendered {len(actor_entries)} dataset(s)."
        if fallback_messages: text += " " + " | ".join(fallback_messages)
        self.status.setText(text); self._save_state()

    def _add_axes(self, bounds, raw_min, raw_max):
        cfg = self.vtk_config
        if not cfg.show_axes: self.axes_bundle = None; return
        self.axes_bundle = build_cube_axes_bundle(cfg, bounds, raw_min, raw_max, self.renderer.GetActiveCamera())
        self.axes = self.axes_bundle.base
        for actor in self.axes_bundle.actors: self.renderer.AddActor(actor)

    def _add_active_scalarbar(self, luts):
        if not self.vtk_config.show_colorbar or not luts: return
        active = self._selected_dataset()
        dataset_id = active.dataset_id if active and active.dataset_id in luts else next((value for value in self.state.render_order_3d if value in luts), next(iter(luts)))
        dataset = next(d for d in self.state.datasets if d.dataset_id == dataset_id)
        self.scalarbar.SetLookupTable(luts[dataset_id]); self.scalarbar.SetTitle(dataset.z3d or dataset.label)
        color = hex_to_rgb(self.vtk_config.x_axis.label_style.color); self.scalarbar.GetTitleTextProperty().SetColor(*color); self.scalarbar.GetLabelTextProperty().SetColor(*color)
        self.renderer.AddActor2D(self.scalarbar)

    def _add_legend(self, entries):
        if not self.vtk_config.show_legend or not entries: return
        legend = vtk.vtkLegendBoxActor(); legend.SetNumberOfEntries(len(entries)); legend.SetPosition(.02, .02); legend.SetWidth(.22); legend.SetHeight(min(.35, .06 * len(entries) + .05))
        sphere = vtk.vtkSphereSource(); sphere.Update()
        for index, (dataset, _) in enumerate(entries):
            legend.SetEntry(index, sphere.GetOutput(), dataset_display_name(dataset), hex_to_rgb(dataset.color))
        legend.GetEntryTextProperty().SetColor(*hex_to_rgb(self.vtk_config.x_axis.label_style.color)); self.renderer.AddActor2D(legend)

    @staticmethod
    def _background_rgb(name):
        return {"White": (1, 1, 1), "Light Gray": (.85, .85, .85), "Gray": (.5, .5, .5), "Dark Gray": (.2, .2, .2), "Black": (0, 0, 0)}.get(name, (1, 1, 1))

    def open_3d_property(self):
        available = [dataset for dataset in self.state.datasets if dataset.enabled and dataset.dataset_id in self.frames]
        ids = {dataset.dataset_id for dataset in available}
        active_id = self.state.active_dataset_id if self.state.active_dataset_id in ids else next((value for value in self.state.render_order_3d if value in ids), "")
        dialog = VtkPropertyDialog(
            self.vtk_config, available, self.state.render_order_3d, active_id, self._apply_3d_config, self,
            save_format_callback=self._save_3d_format_file, load_format_callback=self._load_3d_format_file,
            style_templates=self._dataset_style_templates,
        )
        dialog.exec()

    def _apply_3d_config(self, config, datasets, edited_order, active_id, format_templates=None):
        self.vtk_config = config
        edited = {dataset.dataset_id: dataset for dataset in datasets}; edited_ids = set(edited)
        for index, dataset in enumerate(self.state.datasets):
            if dataset.dataset_id in edited: self.state.datasets[index] = edited[dataset.dataset_id]
        for card in self.cards:
            replacement = edited.get(card.dataset_id)
            if replacement is not None: card.dataset = replacement
        iterator = iter(edited_order)
        self.state.render_order_3d = [next(iterator) if value in edited_ids else value for value in self.state.render_order_3d]
        self.state.active_dataset_id = active_id; self._refresh_cards()
        template_source = [edited[value] for value in edited_order if value in edited] or list(format_templates or self._dataset_style_templates)
        self._persist_3d_visual_style(template_source)
        self.draw_3d(); self._save_state()

    def _save_3d_format_file(self, config, datasets, order, format_templates):
        path, _ = QFileDialog.getSaveFileName(self, "Save 3D Plot Format", "", "MInDes 3D style (*.mindes3dstyle.json)")
        if not path: return
        if not path.lower().endswith(".mindes3dstyle.json"): path += ".mindes3dstyle.json"
        by_id = {dataset.dataset_id: dataset for dataset in datasets}
        ordered = [by_id[value] for value in order if value in by_id]
        try:
            payload = make_3d_style_payload(config, ordered, format_templates or self._dataset_style_templates)
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc: QMessageBox.warning(self, "Save Format", str(exc)); return
        self.status.setText(f"Saved 3D plot format: {Path(path).name}")

    def _load_3d_format_file(self, current, datasets, order, _format_templates):
        path, _ = QFileDialog.getOpenFileName(self, "Load 3D Plot Format", "", "MInDes 3D style (*.mindes3dstyle.json);;JSON files (*.json)")
        if not path: return None
        try:
            style, templates = parse_3d_style_payload(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Load Format", str(exc)); return None
        by_id = {dataset.dataset_id: dataset for dataset in datasets}
        for index, dataset_id in enumerate(value for value in order if value in by_id):
            if index < len(templates): by_id[dataset_id] = apply_dataset_template(by_id[dataset_id], templates[index])
        return apply_3d_visual_style(current, style), [by_id.get(dataset.dataset_id, dataset) for dataset in datasets], templates

    def reset_view(self):
        self.renderer.ResetCamera(); self.renderer.ResetCameraClippingRange(); self.vtk_widget.GetRenderWindow().Render()

    def view_axis(self, axis):
        bounds = self.renderer.ComputeVisiblePropBounds(); center = [(bounds[i * 2] + bounds[i * 2 + 1]) / 2 for i in range(3)]; distance = max(bounds[1]-bounds[0], bounds[3]-bounds[2], bounds[5]-bounds[4], 1) * 2.5
        camera = self.renderer.GetActiveCamera(); camera.SetFocalPoint(*center)
        if axis == "X": camera.SetPosition(center[0] + distance, center[1], center[2]); camera.SetViewUp(0, 0, 1)
        elif axis == "Y": camera.SetPosition(center[0], center[1] + distance, center[2]); camera.SetViewUp(0, 0, 1)
        else: camera.SetPosition(center[0], center[1], center[2] + distance); camera.SetViewUp(0, 1, 0)
        self.renderer.ResetCameraClippingRange(); self.vtk_widget.GetRenderWindow().Render()

    def save_screenshot(self):
        path, selected = QFileDialog.getSaveFileName(self, "Save 3D Screenshot", "", "PNG (*.png);;JPEG (*.jpg);;TIFF (*.tif *.tiff)")
        if not path: return
        ext = {"PNG (*.png)": ".png", "JPEG (*.jpg)": ".jpg", "TIFF (*.tif *.tiff)": ".tif"}.get(selected, ".png")
        if not Path(path).suffix: path += ext
        capture = vtk.vtkWindowToImageFilter(); capture.SetInput(self.vtk_widget.GetRenderWindow()); capture.SetScale(self.vtk_config.screenshot_scale); capture.ReadFrontBufferOff(); capture.Update()
        suffix = Path(path).suffix.lower()
        writer = vtk.vtkPNGWriter() if suffix == ".png" else vtk.vtkJPEGWriter() if suffix in (".jpg", ".jpeg") else vtk.vtkTIFFWriter()
        writer.SetFileName(path); writer.SetInputConnection(capture.GetOutputPort()); writer.Write(); self.status.setText(f"Saved 3D screenshot: {Path(path).name}")

    def _save_state(self):
        if hasattr(self, "splitter"): self.state.splitter_sizes = self.splitter.sizes()
        self.settings.setValue(UI_STATE_KEY, json.dumps({"splitter_sizes": self.state.splitter_sizes}, ensure_ascii=False))

    def closeEvent(self, event):
        self._closing = True; self._save_state()
        try: self.vtk_widget.Finalize()
        except Exception: pass
        super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication([]); dialog = CSVPlotterDialog(); dialog.show(); app.exec()


if __name__ == "__main__":
    main()
