"""Multi-file VTS 3D plotting dialog."""
from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path

import vtk
from PySide6.QtCore import Qt, QSettings, QSignalBlocker
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QScrollArea, QSplitter, QVBoxLayout,
    QWidget, QSizePolicy,
)
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from .models import VtsDatasetConfig, VtsPlotterState, VtkPlotConfig, dataset_display_name
from .dataset_card import VtsDatasetCard
from .visualization import (
    get_vts_fields, get_vts_field_names, load_vts_file,
    render_scene, _background_rgb, hex_to_rgb,
)
from .vtk_properties import VtsPropertyDialog
from .style_formats import (
    make_3d_style_payload, parse_3d_style_payload, apply_3d_visual_style,
    sanitize_dataset_template, apply_dataset_template,
)
from .vtk_utils import build_cube_axes_bundle


UI_STATE_KEY = "vts_plotter/ui_v2"
STYLE_3D_KEY = "vts_plotter/visual_3d_v1"
STATE_KEY = "vts_plotter/state_v1"


class VTSPlotterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VTS Plotter")
        self.setWindowFlag(Qt.WindowType.Window, True)
        self._set_size(parent)
        self.settings = QSettings("MInDes", "MInDes-UI")
        self.state = self._load_state()
        self.vtk_config, self._dataset_style_templates = self._load_3d_visual_style()
        self.frames: dict[str, vtk.vtkStructuredGrid] = {}
        self.cards: list[VtsDatasetCard] = []
        self._select_all_loading = False
        self._closing = False
        self._build_ui()
        self._restore_datasets()

    def _set_size(self, parent):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        if parent is not None:
            geo = parent.geometry()
            w = max(1100, min(int(geo.width() * .95), screen.width() - 30))
            h = max(760, min(int(geo.height() * .95), screen.height() - 50))
            self.resize(w, h)
            self.move(max(screen.x(), geo.x() + (geo.width() - w) // 2),
                      max(screen.y(), geo.y() + (geo.height() - h) // 2))
        else:
            self.resize(max(1100, int(screen.width() * .8)),
                        max(760, int(screen.height() * .8)))

    def _load_state(self) -> VtsPlotterState:
        # Load datasets from state key
        try:
            raw_state = json.loads(self.settings.value(STATE_KEY, "{}", type=str))
        except (TypeError, ValueError, json.JSONDecodeError):
            raw_state = {}
        if not isinstance(raw_state, dict):
            raw_state = {}

        datasets = []
        for item in raw_state.get("datasets", []):
            if isinstance(item, dict):
                datasets.append(VtsDatasetConfig.from_dict(item))
        render_order = [v for v in raw_state.get("render_order", [])]
        active_id = str(raw_state.get("active_dataset_id", ""))

        # Load UI state (splitter sizes)
        try:
            raw_ui = json.loads(self.settings.value(UI_STATE_KEY, "{}", type=str))
        except (TypeError, ValueError, json.JSONDecodeError):
            raw_ui = {}
        if not isinstance(raw_ui, dict):
            raw_ui = {}
        sizes = [int(v) for v in raw_ui.get("splitter_sizes", []) if isinstance(v, (int, float))]

        # Validate render_order
        dataset_ids = {d.dataset_id for d in datasets}
        render_order = [v for v in render_order if v in dataset_ids] + [d.dataset_id for d in datasets if d.dataset_id not in render_order]

        return VtsPlotterState(
            datasets=datasets,
            vtk=VtkPlotConfig(),
            active_dataset_id=active_id if active_id in dataset_ids else (datasets[0].dataset_id if datasets else ""),
            render_order=render_order,
            splitter_sizes=sizes,
        )

    def _load_3d_visual_style(self):
        try:
            raw = json.loads(self.settings.value(STYLE_3D_KEY, "{}", type=str))
            style, templates = parse_3d_style_payload(raw)
            return apply_3d_visual_style(VtkPlotConfig(), style), templates
        except (TypeError, ValueError, json.JSONDecodeError):
            return VtkPlotConfig(), []

    def _persist_3d_visual_style(self, templates=None):
        templates = list(templates if templates is not None else self._dataset_style_templates)
        self._dataset_style_templates = [sanitize_dataset_template(v) for v in templates]
        payload = make_3d_style_payload(self.vtk_config, templates=self._dataset_style_templates)
        self.settings.setValue(STYLE_3D_KEY, json.dumps(payload, ensure_ascii=False))

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(self.splitter, 1)

        # Left panel
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()
        left_layout.addLayout(controls)
        self.select_all = QCheckBox("Select All")
        self.select_all.setTristate(True)
        self.select_all.clicked.connect(self._toggle_select_all)
        controls.addWidget(self.select_all)
        controls.addStretch()

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(2, 2, 4, 2)
        self.cards_layout.setSpacing(7)
        self.cards_layout.addStretch()
        self.cards_scroll.setWidget(self.cards_container)
        left_layout.addWidget(self.cards_scroll, 1)

        data_buttons = QHBoxLayout()
        data_buttons.setContentsMargins(0, 0, 0, 0)
        left_layout.addLayout(data_buttons)
        self.data_action_buttons = []
        for text, slot in [("Add", self.add_vts), ("Remove", self.remove_selected),
                           ("Reload", self.reload_selected)]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            data_buttons.addWidget(btn, 1)
            self.data_action_buttons.append(btn)
        min_w = max(btn.minimumSizeHint().width() for btn in self.data_action_buttons)
        for btn in self.data_action_buttons:
            btn.setMinimumWidth(min_w)

        # Right panel — 3D VTK view only
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.vtk_widget = QVTKRenderWindowInteractor(right)
        right_layout.addWidget(self.vtk_widget, 1)
        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(*_background_rgb("White"))
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
        self.iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        self.iren.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())
        self.iren.Initialize()

        self._build_3d_action_buttons(right_layout)

        self.splitter.addWidget(left)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes(self.state.splitter_sizes or [400, 800])
        self.splitter.splitterMoved.connect(lambda *_: self._save_state())

        self.status = QLabel("Add one or more .vts files to begin.")
        self.status.setStyleSheet("background:#f0f0f0;padding:4px;border-top:1px solid #bbb;")
        root.addWidget(self.status)

    def _build_3d_action_buttons(self, layout):
        buttons = QGridLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(buttons)
        actions = [
            ("Draw 3D", self.draw_3d, 0, 0),
            ("Property", self.open_3d_property, 0, 1),
            ("Screenshot", self.save_screenshot, 0, 3),
            ("Reset", self.reset_view, 1, 0),
            ("View X", lambda: self._view_axis("X"), 1, 1),
            ("View Y", lambda: self._view_axis("Y"), 1, 2),
            ("View Z", lambda: self._view_axis("Z"), 1, 3),
        ]
        self.view_action_buttons = []
        for text, slot, row, col in actions:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            buttons.addWidget(btn, row, col)
            self.view_action_buttons.append(btn)
        min_w = max(btn.minimumSizeHint().width() for btn in self.view_action_buttons)
        for btn in self.view_action_buttons:
            btn.setMinimumWidth(min_w)
        for c in range(4):
            buttons.setColumnStretch(c, 1)

    def _restore_datasets(self):
        for dataset in self.state.datasets:
            if Path(dataset.path).is_file():
                try:
                    grid = load_vts_file(dataset.path)
                    if grid:
                        self.frames[dataset.dataset_id] = grid
                except Exception as exc:
                    self.status.setText(f"Failed to restore {dataset.path}: {exc}")
            self._append_card(dataset)
        valid = {d.dataset_id for d in self.state.datasets}
        if self.state.active_dataset_id not in valid and self.state.datasets:
            self.state.active_dataset_id = self.state.datasets[0].dataset_id
        self._refresh_cards()

    def add_vts(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add VTS files", "", "VTS files (*.vts);;All files (*)")
        for path in paths:
            try:
                grid = load_vts_file(path)
            except Exception as exc:
                QMessageBox.warning(self, "VTS Error", f"Failed to read {path}:\\n{exc}")
                continue
            if grid is None:
                QMessageBox.warning(self, "VTS Error", f"{path} contains no valid data.")
                continue
            absolute_path = os.path.abspath(path)
            dataset = VtsDatasetConfig(
                path=absolute_path,
                label=self._unique_dataset_label(Path(path).stem, absolute_path))
            if len(self.state.datasets) < len(self._dataset_style_templates):
                dataset = apply_dataset_template(dataset, self._dataset_style_templates[len(self.state.datasets)])
            self.state.datasets.append(dataset)
            self.frames[dataset.dataset_id] = grid
            self.state.render_order.append(dataset.dataset_id)
            self._append_card(dataset)
            self._activate_dataset(dataset.dataset_id)
            self.status.setText(f"Loaded: {Path(path).name}")
        if paths:
            self._refresh_cards()
            self._save_state()

    def _unique_dataset_label(self, requested, source_path=""):
        labels = {item.label for item in self.state.datasets}
        base = str(requested).strip() or Path(source_path).stem or "dataset"
        prefix, sep, suffix = base.rpartition("-")
        if sep and suffix.isdigit() and int(suffix) >= 2 and source_path:
            normalized = os.path.normcase(os.path.abspath(source_path))
            same = {item.label for item in self.state.datasets
                    if os.path.normcase(os.path.abspath(item.path)) == normalized}
            if prefix in same:
                base = prefix
        if base not in labels:
            return base
        n = 2
        while f"{base}-{n}" in labels:
            n += 1
        return f"{base}-{n}"

    def _append_card(self, dataset, index=None):
        grid = self.frames.get(dataset.dataset_id)
        fields = get_vts_field_names(grid) if grid else []
        card = VtsDatasetCard(dataset, fields, grid is not None, self.cards_container)
        card.changed.connect(self._card_changed)
        card.activated.connect(self._activate_dataset)
        card.moveRequested.connect(self._move_card)
        card.reloadRequested.connect(self.reload_dataset)
        card.duplicateRequested.connect(self.duplicate_dataset)
        card.removeRequested.connect(lambda did: self.remove_dataset(did, True))
        if index is None:
            index = len(self.cards)
        index = max(0, min(int(index), len(self.cards)))
        self.cards.insert(index, card)
        self.cards_layout.insertWidget(index, card)

    def _dataset_by_id(self, dataset_id):
        return next((item for item in self.state.datasets if item.dataset_id == dataset_id), None)

    def _selected_dataset(self):
        return self._dataset_by_id(self.state.active_dataset_id)

    def _card_changed(self, _did=""):
        self._update_select_all()
        self._save_state()

    def _activate_dataset(self, dataset_id):
        if self._dataset_by_id(dataset_id) is None:
            return
        self.state.active_dataset_id = dataset_id
        self._refresh_cards()
        self._save_state()

    def _refresh_cards(self):
        total = len(self.cards)
        for idx, card in enumerate(self.cards):
            card.set_position(idx, total)
            card.set_active(card.dataset_id == self.state.active_dataset_id)
        self._update_select_all()

    def _update_select_all(self):
        available = [c for c in self.cards if c.available]
        checked = sum(c.is_checked() for c in available)
        state = Qt.CheckState.Unchecked
        if checked == len(available) and available:
            state = Qt.CheckState.Checked
        elif checked:
            state = Qt.CheckState.PartiallyChecked
        with QSignalBlocker(self.select_all):
            self.select_all.setCheckState(state)

    def _toggle_select_all(self, *_):
        available = [c for c in self.cards if c.available]
        check = not available or not all(c.is_checked() for c in available)
        for card in available:
            card.set_checked(check)
        self._update_select_all()
        self._save_state()

    def _move_card(self, dataset_id, action):
        idx = next((i for i, c in enumerate(self.cards) if c.dataset_id == dataset_id), -1)
        if idx < 0:
            return
        targets = {"up": max(0, idx - 1), "down": min(len(self.cards) - 1, idx + 1),
                   "top": 0, "bottom": len(self.cards) - 1}
        target = targets.get(action, idx)
        if target == idx:
            return
        card = self.cards.pop(idx)
        dataset = self.state.datasets.pop(idx)
        self.cards.insert(target, card)
        self.state.datasets.insert(target, dataset)
        self.cards_layout.removeWidget(card)
        self.cards_layout.insertWidget(target, card)
        self._refresh_cards()
        self._save_state()

    def remove_selected(self):
        selected = [d for d in self.state.datasets if d.enabled and d.dataset_id in self.frames]
        if not selected:
            self.status.setText("No On dataset is selected for removal.")
            return
        reply = QMessageBox.question(self, "Remove Datasets", f"Remove {len(selected)} On dataset(s)?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        for dataset in list(selected):
            self.remove_dataset(dataset.dataset_id, False)
        self._refresh_cards()
        self._save_state()
        self.status.setText(f"Removed {len(selected)} dataset(s).")

    def remove_dataset(self, dataset_id, confirm):
        if confirm:
            reply = QMessageBox.question(self, "Remove Dataset", "Remove this dataset?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
        idx = next((i for i, d in enumerate(self.state.datasets) if d.dataset_id == dataset_id), -1)
        if idx < 0:
            return
        self.state.datasets.pop(idx)
        self.frames.pop(dataset_id, None)
        card = next((c for c in self.cards if c.dataset_id == dataset_id), None)
        if card:
            self.cards.remove(card)
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self.state.render_order = [v for v in self.state.render_order if v != dataset_id]
        if self.state.active_dataset_id == dataset_id:
            if self.state.datasets:
                self.state.active_dataset_id = self.state.datasets[min(idx, len(self.state.datasets) - 1)].dataset_id
            else:
                self.state.active_dataset_id = ""
        self._refresh_cards()
        self._save_state()

    def reload_selected(self):
        selected = [d for d in self.state.datasets if d.enabled and d.dataset_id in self.frames]
        for dataset in selected:
            self.reload_dataset(dataset.dataset_id)

    def reload_dataset(self, dataset_id):
        dataset = self._dataset_by_id(dataset_id)
        if dataset is None:
            return
        try:
            grid = load_vts_file(dataset.path)
            if grid is None:
                self.status.setText(f"Failed to reload {dataset.path}: no data")
                return
            self.frames[dataset.dataset_id] = grid
            card = next((c for c in self.cards if c.dataset_id == dataset_id), None)
            if card:
                fields = get_vts_field_names(grid)
                card.update_fields(fields)
            self.status.setText(f"Reloaded: {Path(dataset.path).name}")
        except Exception as exc:
            QMessageBox.warning(self, "Reload Error", str(exc))

    def duplicate_dataset(self, dataset_id):
        source = self._dataset_by_id(dataset_id)
        if source is None:
            return
        duplicate = deepcopy(source)
        duplicate.dataset_id = VtsDatasetConfig().dataset_id
        duplicate.label = self._unique_dataset_label(source.label, source.path)
        src_idx = self.state.datasets.index(source)
        self.state.datasets.insert(src_idx + 1, duplicate)
        if dataset_id in self.frames:
            self.frames[duplicate.dataset_id] = self.frames[dataset_id]
        self.state.render_order = self._insert_above(self.state.render_order, dataset_id, duplicate.dataset_id)
        self._append_card(duplicate, src_idx + 1)
        self.state.active_dataset_id = duplicate.dataset_id
        self._refresh_cards()
        self._save_state()
        self.status.setText(f"Duplicated {dataset_display_name(source)} as {dataset_display_name(duplicate)}.")

    @staticmethod
    def _insert_above(order, source_id, new_id):
        result = [v for v in order if v != new_id]
        idx = result.index(source_id) if source_id in result else len(result)
        result.insert(idx, new_id)
        return result

    # ── Rendering ──────────────────────────────────────────

    def draw_3d(self):
        self.renderer.RemoveAllViewProps()
        self.renderer.SetBackground(*_background_rgb(self.vtk_config.background))

        for dataset in self.state.datasets:
            if not dataset.enabled:
                continue
            grid = self.frames.get(dataset.dataset_id)
            if grid is None:
                continue

            cfg = deepcopy(dataset)
            raw_field = cfg.field_name
            if not raw_field:
                continue

            is_vec = raw_field.startswith("[V] ")
            clean_name = raw_field[4:] if (raw_field.startswith("[S] ") or raw_field.startswith("[V] ")) else raw_field

            # Ensure scalar array exists
            from .visualization import _ensure_scalar_field
            scalar_name, _ = _ensure_scalar_field(grid, clean_name, is_vec)
            cfg._scalar_name = scalar_name

            # Update color range
            if cfg.auto_color_range:
                arr = grid.GetPointData().GetArray(scalar_name)
                if arr:
                    rmin, rmax = arr.GetRange()
                    cfg.color_min = rmin
                    cfg.color_max = rmax

            try:
                from .visualization import apply_data_pipeline
                processed = apply_data_pipeline(grid, cfg)
                if processed.GetNumberOfPoints() == 0:
                    continue

                from .vtk_utils import make_lookup_table
                lut = make_lookup_table(cfg.colormap, (cfg.color_min, cfg.color_max))

                from .visualization import _RENDERERS
                render_fn = _RENDERERS.get(cfg.mode3d)
                if render_fn:
                    render_fn(self.renderer, processed, cfg, lut)
            except Exception as exc:
                self.status.setText(f"Error rendering {dataset.label}: {exc}")
                continue

        # Post-processing: axes, colorbar, legend
        if self.vtk_config.show_axes:
            self._add_axes()
        if self.vtk_config.show_colorbar:
            self._add_colorbar()
        if self.vtk_config.show_legend:
            self._add_legend()

        self.renderer.ResetCamera()
        self.renderer.ResetCameraClippingRange()
        self.vtk_widget.GetRenderWindow().Render()
        enabled = sum(1 for d in self.state.datasets if d.enabled and d.dataset_id in self.frames)
        self.status.setText(f"3D: rendered {enabled} dataset(s).")

    def _add_axes(self):
        bounds = self.renderer.ComputeVisiblePropBounds()
        if not bounds or all(abs(v) < 1e-10 for v in bounds):
            return
        raw_min = (bounds[0], bounds[2], bounds[4])
        raw_max = (bounds[1], bounds[3], bounds[5])
        span = (raw_max[0] - raw_min[0], raw_max[1] - raw_min[1], raw_max[2] - raw_min[2])
        display_bounds = (0, span[0], 0, span[1], 0, span[2])
        bundle = build_cube_axes_bundle(self.vtk_config, display_bounds, raw_min, raw_max, self.renderer.GetActiveCamera())
        for actor in bundle.actors:
            self.renderer.AddActor(actor)

    def _add_colorbar(self):
        active = self._selected_dataset()
        if active is None:
            active = next((d for d in self.state.datasets if d.enabled and d.dataset_id in self.frames), None)
        if active is None:
            return
        from .vtk_utils import make_lookup_table
        lut = make_lookup_table(active.colormap, (active.color_min, active.color_max))
        bar = vtk.vtkScalarBarActor()
        bar.SetLookupTable(lut)
        title = active.field_name if active.field_name else active.label
        bar.SetTitle(title)
        bar.SetNumberOfLabels(5)
        bar.SetLabelFormat("%.3g")
        bar.SetPosition(.86, .15)
        bar.SetWidth(.1)
        bar.SetHeight(.7)
        color = hex_to_rgb(self.vtk_config.x_axis.label_style.color)
        bar.GetTitleTextProperty().SetColor(*color)
        bar.GetLabelTextProperty().SetColor(*color)
        self.renderer.AddActor2D(bar)

    def _add_legend(self):
        enabled = [d for d in self.state.datasets if d.enabled and d.dataset_id in self.frames]
        if not enabled:
            return
        legend = vtk.vtkLegendBoxActor()
        legend.SetNumberOfEntries(len(enabled))
        legend.SetPosition(.02, .02)
        legend.SetWidth(.22)
        legend.SetHeight(min(.35, .06 * len(enabled) + .05))
        sphere = vtk.vtkSphereSource()
        sphere.Update()
        for idx, ds in enumerate(enabled):
            legend.SetEntry(idx, sphere.GetOutput(), dataset_display_name(ds), hex_to_rgb(ds.color))
        legend.GetEntryTextProperty().SetColor(*hex_to_rgb("#000000"))
        self.renderer.AddActor2D(legend)

    # ── Property dialog ────────────────────────────────────

    def open_3d_property(self):
        available = [d for d in self.state.datasets if d.enabled and d.dataset_id in self.frames]
        ids = {d.dataset_id for d in available}
        active_id = self.state.active_dataset_id if self.state.active_dataset_id in ids else \
            next((v for v in self.state.render_order if v in ids), "")

        # Build field options from active dataset
        field_options = []
        active_ds = next((d for d in available if d.dataset_id == active_id), None)
        if active_ds:
            grid = self.frames.get(active_ds.dataset_id)
            if grid:
                field_options = get_vts_field_names(grid)

        dialog = VtsPropertyDialog(
            self.vtk_config, available, self.state.render_order, active_id,
            self._apply_3d_config, self,
            save_format_callback=self._save_3d_format_file,
            load_format_callback=self._load_3d_format_file,
            style_templates=self._dataset_style_templates,
            field_options=field_options,
        )
        dialog.exec()

    def _apply_3d_config(self, config, datasets, edited_order, active_id, format_templates=None):
        self.vtk_config = config
        edited = {d.dataset_id: d for d in datasets}
        edited_ids = set(edited)
        for idx, dataset in enumerate(self.state.datasets):
            if dataset.dataset_id in edited:
                self.state.datasets[idx] = edited[dataset.dataset_id]
        for card in self.cards:
            replacement = edited.get(card.dataset_id)
            if replacement is not None:
                card.dataset = replacement
        it = iter(edited_order)
        self.state.render_order = [next(it) if v in edited_ids else v for v in self.state.render_order]
        self.state.active_dataset_id = active_id
        self._refresh_cards()
        template_source = [edited[v] for v in edited_order if v in edited] or list(format_templates or self._dataset_style_templates)
        self._persist_3d_visual_style(template_source)
        self.draw_3d()
        self._save_state()

    def _save_3d_format_file(self, config, datasets, order, format_templates):
        path, _ = QFileDialog.getSaveFileName(self, "Save 3D Plot Format", "", "MInDes 3D style (*.mindes3dstyle.json)")
        if not path:
            return
        if not path.lower().endswith(".mindes3dstyle.json"):
            path += ".mindes3dstyle.json"
        by_id = {d.dataset_id: d for d in datasets}
        ordered = [by_id[v] for v in order if v in by_id]
        try:
            payload = make_3d_style_payload(config, ordered, format_templates or self._dataset_style_templates)
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Save Format", str(exc))
            return
        self.status.setText(f"Saved 3D plot format: {Path(path).name}")

    def _load_3d_format_file(self, current, datasets, order, _format_templates):
        path, _ = QFileDialog.getOpenFileName(self, "Load 3D Plot Format", "", "MInDes 3D style (*.mindes3dstyle.json);;JSON files (*.json)")
        if not path:
            return None
        try:
            style, templates = parse_3d_style_payload(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Load Format", str(exc))
            return None
        by_id = {d.dataset_id: d for d in datasets}
        for idx, dataset_id in enumerate(v for v in order if v in by_id):
            if idx < len(templates):
                by_id[dataset_id] = apply_dataset_template(by_id[dataset_id], templates[idx])
        return apply_3d_visual_style(current, style), [by_id.get(d.dataset_id, d) for d in datasets], templates

    # ── View helpers ───────────────────────────────────────

    def reset_view(self):
        self.renderer.ResetCamera()
        self.renderer.ResetCameraClippingRange()
        self.vtk_widget.GetRenderWindow().Render()

    def _view_axis(self, axis):
        bounds = self.renderer.ComputeVisiblePropBounds()
        center = [(bounds[i * 2] + bounds[i * 2 + 1]) / 2 for i in range(3)]
        dist = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4], 1) * 2.5
        camera = self.renderer.GetActiveCamera()
        camera.SetFocalPoint(*center)
        axis = axis.upper()
        if axis == "X":
            camera.SetPosition(center[0] + dist, center[1], center[2])
            camera.SetViewUp(0, 0, 1)
        elif axis == "Y":
            camera.SetPosition(center[0], center[1] + dist, center[2])
            camera.SetViewUp(0, 0, 1)
        else:
            camera.SetPosition(center[0], center[1], center[2] + dist)
            camera.SetViewUp(0, 1, 0)
        self.renderer.ResetCameraClippingRange()
        self.vtk_widget.GetRenderWindow().Render()

    def save_screenshot(self):
        path, selected = QFileDialog.getSaveFileName(self, "Save 3D Screenshot", "", "PNG (*.png);;JPEG (*.jpg);;TIFF (*.tif *.tiff)")
        if not path:
            return
        ext_map = {"PNG (*.png)": ".png", "JPEG (*.jpg)": ".jpg", "TIFF (*.tif *.tiff)": ".tif"}
        ext = ext_map.get(selected, ".png")
        if not Path(path).suffix:
            path += ext
        capture = vtk.vtkWindowToImageFilter()
        capture.SetInput(self.vtk_widget.GetRenderWindow())
        capture.SetScale(self.vtk_config.screenshot_scale)
        capture.ReadFrontBufferOff()
        capture.Update()
        ext_lower = Path(path).suffix.lower()
        if ext_lower == ".png":
            writer = vtk.vtkPNGWriter()
        elif ext_lower in (".jpg", ".jpeg"):
            writer = vtk.vtkJPEGWriter()
        else:
            writer = vtk.vtkTIFFWriter()
        writer.SetFileName(path)
        writer.SetInputConnection(capture.GetOutputPort())
        writer.Write()
        self.status.setText(f"Saved: {Path(path).name}")

    # ── State persistence ──────────────────────────────────

    def _save_state(self):
        if hasattr(self, "splitter"):
            self.state.splitter_sizes = self.splitter.sizes()
        # Save datasets + order
        state_payload = {
            "datasets": [json.loads(json.dumps(d.__dict__, default=str)) for d in self.state.datasets],
            "render_order": list(self.state.render_order),
            "active_dataset_id": self.state.active_dataset_id,
        }
        self.settings.setValue(STATE_KEY, json.dumps(state_payload, ensure_ascii=False))
        # Save UI state
        self.settings.setValue(UI_STATE_KEY, json.dumps({"splitter_sizes": self.state.splitter_sizes}, ensure_ascii=False))

    def closeEvent(self, event):
        self._closing = True
        self._save_state()
        try:
            self.vtk_widget.Finalize()
        except Exception:
            pass
        super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication([])
    dialog = VTSPlotterDialog()
    dialog.show()
    app.exec()


if __name__ == "__main__":
    main()
