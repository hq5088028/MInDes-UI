# Tools/CommonTangentTools/common_tangent_o3_gui.py
"""
两相吉布斯自由能公切面: VTK + PySide6 交互 GUI (重构版, 无 PyVista 依赖).

三元体系 A-B-C (x1 + x2 + x3 = 1), 两相 alpha 和 beta,
固定温度下的两个吉布斯自由能曲面 G_alpha(x1,x2), G_beta(x1,x2).

用法:
  1) 独立运行:  python common_tangent_o3_gui.py
  2) 作为子对话框: CommonTangentDialog(parent).exec()

CSV 文件格式: 三列 x1, x2, G (表头可有可无), 要求 x1>=0, x2>=0, x1+x2<=1.

依赖: PySide6, vtk, numpy, pandas, matplotlib.
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd
try:
    from .common_tangent_core import (
        CompositionSection, LinearTriangleInterpolator, PhaseTable,
        compute_common_tangent as _core_compute_common_tangent,
        lower_hull_simplices as _core_lower_hull_simplices,
        phase_fraction as _core_phase_fraction,
        triangle_grid as _core_triangle_grid,
    )
except ImportError:  # Support direct execution from this directory.
    from common_tangent_core import (
        CompositionSection, LinearTriangleInterpolator, PhaseTable,
        compute_common_tangent as _core_compute_common_tangent,
        lower_hull_simplices as _core_lower_hull_simplices,
        phase_fraction as _core_phase_fraction,
        triangle_grid as _core_triangle_grid,
    )

from PySide6.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QDoubleSpinBox, QSpinBox, QPushButton, QSplitter,
    QFileDialog, QMessageBox, QGroupBox, QComboBox, QTableWidget,
    QTableWidgetItem, QDialogButtonBox, QListWidget, QListWidgetItem,
    QFormLayout,
)
from PySide6.QtCore import Qt, QTimer

import vtk
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavToolbar
from PySide6.QtGui import QGuiApplication


# =============================================================
# 数据源抽象 (原样保留)
# =============================================================
class PhaseGFunction:
    def __init__(self, func, label="", meta=None):
        self._func = func
        self.label = label
        self.meta = meta or {}

    def __call__(self, x1, x2):
        return self._func(x1, x2)

    @classmethod
    def from_callable(cls, func, label=""):
        return cls(func, label=label, meta={"source": "callable"})

    @classmethod
    def from_table(cls, x1, x2, G, label=""):
        x1 = np.asarray(x1, float)
        x2 = np.asarray(x2, float)
        G = np.asarray(G, float)
        if not (len(x1) == len(x2) == len(G)):
            raise ValueError("x1, x2, G must have same length")
        interpolator = LinearTriangleInterpolator(x1, x2, G)

        def _f(a, b):
            a = np.atleast_1d(a).astype(float)
            b = np.atleast_1d(b).astype(float)
            return interpolator(a, b)

        finite = np.isfinite(x1) & np.isfinite(x2) & np.isfinite(G)
        meta = {"source": "table", "n_points": int(finite.sum()),
                "x1_range": (float(x1[finite].min()), float(x1[finite].max())),
                "x2_range": (float(x2[finite].min()), float(x2[finite].max())),
                "G_range":  (float(G[finite].min()),  float(G[finite].max()))}
        return cls(_f, label=label, meta=meta)


class ColumnMappingDialog(QDialog):
    def __init__(self, frame, parent=None):
        super().__init__(parent); self.setWindowTitle("Map composition and Gibbs columns"); self.resize(430, 480)
        layout = QVBoxLayout(self); form = QFormLayout(); layout.addLayout(form)
        self.g_combo = QComboBox(); self.g_combo.addItems([str(value) for value in frame.columns]); form.addRow("Gibbs energy:", self.g_combo)
        names = [str(value).strip().lower() for value in frame.columns]
        suggested = next((index for index, value in enumerate(names) if value in ("g", "gibbs", "gibbs_energy") or value.startswith("fchem")), len(names) - 1)
        self.g_combo.setCurrentIndex(max(0, suggested)); layout.addWidget(QLabel("Composition columns (select at least three):"))
        self.columns = QListWidget(); layout.addWidget(self.columns, 1)
        for column in frame.columns:
            item = QListWidgetItem(str(column)); item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            numeric = pd.to_numeric(frame[column], errors="coerce").notna().sum() >= max(3, len(frame) // 2)
            item.setCheckState(Qt.CheckState.Checked if numeric and str(column) != self.g_combo.currentText() else Qt.CheckState.Unchecked); self.columns.addItem(item)
        self.g_combo.currentTextChanged.connect(self._g_changed)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); layout.addWidget(buttons)
        buttons.accepted.connect(self._accept); buttons.rejected.connect(self.reject)

    def _g_changed(self, name):
        for index in range(self.columns.count()):
            if self.columns.item(index).text() == name: self.columns.item(index).setCheckState(Qt.CheckState.Unchecked)

    def selected_components(self):
        return [self.columns.item(index).text() for index in range(self.columns.count()) if self.columns.item(index).checkState() == Qt.CheckState.Checked]

    def _accept(self):
        selected = self.selected_components()
        if self.g_combo.currentText() in selected:
            QMessageBox.warning(self, "Column mapping", "The Gibbs-energy column cannot also be a composition column.")
            return
        if len(selected) < 3: QMessageBox.warning(self, "Column mapping", "Select at least three composition columns."); return
        self.accept()


def _read_csv_frame(path):
    frame = pd.read_csv(path)
    try: numeric_headers = all(np.isfinite(float(value)) for value in frame.columns)
    except (TypeError, ValueError): numeric_headers = False
    if numeric_headers:
        frame = pd.read_csv(path, header=None)
        if frame.shape[1] == 3: frame.columns = ["x1", "x2", "G"]
        else: frame.columns = [f"column_{index + 1}" for index in range(frame.shape[1])]
    return frame


def load_csv_phase_table(path, parent=None, label=""):
    try: frame = _read_csv_frame(path)
    except Exception as exc: raise ValueError(f"Failed to read CSV: {exc}") from exc
    if frame.shape[1] < 3: raise ValueError("CSV must contain composition columns and a Gibbs-energy column.")
    if list(map(str, frame.columns)) == ["x1", "x2", "G"]:
        x1 = pd.to_numeric(frame["x1"], errors="coerce").to_numpy(float); x2 = pd.to_numeric(frame["x2"], errors="coerce").to_numpy(float)
        compositions = np.column_stack([x1, x2, 1.0 - x1 - x2]); gibbs = pd.to_numeric(frame["G"], errors="coerce").to_numpy(float)
        return PhaseTable(("x1", "x2", "x3"), compositions, gibbs, label)
    dialog = ColumnMappingDialog(frame, parent)
    if dialog.exec() != QDialog.DialogCode.Accepted: return None
    components = dialog.selected_components(); g_column = dialog.g_combo.currentText()
    compositions = np.column_stack([pd.to_numeric(frame[value], errors="coerce").to_numpy(float) for value in components])
    gibbs = pd.to_numeric(frame[g_column], errors="coerce").to_numpy(float)
    return PhaseTable(tuple(components), compositions, gibbs, label)


def load_csv_phase(path, label=""):
    try:
        df = pd.read_csv(path)
        if df.shape[1] < 3:
            raise ValueError("CSV must have at least 3 columns")
        cols_lower = [str(c).strip().lower() for c in df.columns]
        if "x1" in cols_lower and "x2" in cols_lower and \
           ("g" in cols_lower or "gibbs" in cols_lower):
            x1 = df.iloc[:, cols_lower.index("x1")].to_numpy(float)
            x2 = df.iloc[:, cols_lower.index("x2")].to_numpy(float)
            g_idx = cols_lower.index("g") if "g" in cols_lower \
                else cols_lower.index("gibbs")
            G = df.iloc[:, g_idx].to_numpy(float)
        else:
            df = pd.read_csv(path, header=None)
            x1 = df.iloc[:, 0].to_numpy(float)
            x2 = df.iloc[:, 1].to_numpy(float)
            G = df.iloc[:, 2].to_numpy(float)
    except Exception as e:
        raise ValueError(f"Failed to read CSV: {e}")

    if np.any(x1 < -1e-6) or np.any(x2 < -1e-6) or \
       np.any(x1 + x2 > 1.0 + 1e-6):
        raise ValueError(
            "CSV contains points outside the ternary simplex. "
            "Require x1>=0, x2>=0, x1+x2<=1.")
    return PhaseGFunction.from_table(x1, x2, G, label=label)


# =============================================================
# 核心算法 (原样保留)
# =============================================================
def triangle_grid(n):
    return _core_triangle_grid(n)


def lower_hull_simplices(points3d):
    return _core_lower_hull_simplices(points3d)


def compute_common_tangent(Ga_func, Gb_func, n=60):
    return _core_compute_common_tangent(Ga_func, Gb_func, n)


def phase_fraction(x_total, tie_segments_xy):
    return _core_phase_fraction(x_total, tie_segments_xy)


# =============================================================
# VTK 几何构造 (原 PyVista 版本的等价实现)
# =============================================================
def _build_surface_vtk(grid, G_values, zscale=1.0):
    """将 (x1, x2, G) 散点三角剖分, 返回带标量 "G" 的 vtkPolyData."""
    n = len(grid)
    points = vtk.vtkPoints()
    for (x, y), z in zip(grid, G_values):
        points.InsertNextPoint(float(x), float(y), float(z) * zscale)

    # 用 vtkDelaunay2D 做 2D 三角剖分(仅看 x-y)
    src = vtk.vtkPolyData()
    src.SetPoints(points)
    delaunay = vtk.vtkDelaunay2D()
    delaunay.SetInputData(src)
    delaunay.Update()
    surf = delaunay.GetOutput()

    # 把 G 作为标量挂上去 (原 z 坐标已是 G*zscale, 这里标量用未缩放的 G)
    scalars = vtk.vtkFloatArray()
    scalars.SetName("G")
    for g in G_values:
        scalars.InsertNextValue(float(g))
    surf.GetPointData().SetScalars(scalars)
    return surf


def _build_tie_lines_vtk(tie_segments_3d, zscale=1.0):
    if not tie_segments_3d:
        return None
    pts = vtk.vtkPoints()
    lines = vtk.vtkCellArray()
    for (a, b) in tie_segments_3d:
        i0 = pts.InsertNextPoint(float(a[0]), float(a[1]), float(a[2]) * zscale)
        i1 = pts.InsertNextPoint(float(b[0]), float(b[1]), float(b[2]) * zscale)
        lines.InsertNextCell(2)
        lines.InsertCellPoint(i0)
        lines.InsertCellPoint(i1)
    pd = vtk.vtkPolyData()
    pd.SetPoints(pts)
    pd.SetLines(lines)
    return pd


def _build_mixed_faces_vtk(mixed_faces_3d, zscale=1.0):
    if not mixed_faces_3d:
        return None
    pts = vtk.vtkPoints()
    tris = vtk.vtkCellArray()
    for tri in mixed_faces_3d:
        i = [
            pts.InsertNextPoint(float(v[0]), float(v[1]), float(v[2]) * zscale)
            for v in tri
        ]
        tris.InsertNextCell(3)
        for k in i:
            tris.InsertCellPoint(k)
    pd = vtk.vtkPolyData()
    pd.SetPoints(pts)
    pd.SetPolys(tris)
    return pd


def _make_lut(cmap_name, rng):
    """粗糙的 colormap: 用 matplotlib 颜色表构造 vtkLookupTable."""
    import matplotlib.cm as cm
    import matplotlib.colors as mcolors
    cmap = cm.get_cmap(cmap_name, 256)
    lut = vtk.vtkLookupTable()
    lut.SetNumberOfTableValues(256)
    lut.SetRange(float(rng[0]), float(rng[1]))
    for i in range(256):
        r, g, b, a = cmap(i / 255.0)
        lut.SetTableValue(i, r, g, b, 1.0)
    lut.Build()
    return lut


# =============================================================
# 主对话框
# =============================================================
class CommonTangentDialog(QDialog):
    """两相吉布斯自由能公切面浏览器 (三元体系 A-B-C).

    Parameters
    ----------
    Ga_func, Gb_func : callable 或 PhaseGFunction, 可选
        两相的 G(x1, x2) 函数. 若为 None, 需用户通过 GUI 导入 CSV.
    parent : QWidget, 可选
    n_init : int
        初始网格细度.
    """

    def __init__(self, Ga_func=None, Gb_func=None, parent=None, n_init=60):
        super().__init__(parent)
        self.phase_table_a = None; self.phase_table_b = None
        self.section_a = None; self.section_b = None
        self.component_names = ("x1", "x2", "x3"); self.active_components = self.component_names
        self.phase_a = self._wrap(Ga_func, "alpha") if Ga_func else None
        self.phase_b = self._wrap(Gb_func, "beta") if Gb_func else None
        self.result = None

        self.setWindowTitle(
            "Two-phase Gibbs common-tangent viewer  (ternary A-B-C)")
        self.setWindowFlag(Qt.WindowType.Window, True)  # 允许最大化/最小化按钮
        self._set_adaptive_dialog_size(parent)
        self._zscale = 1.0      # 3D 显示的 Z 方向压缩比, compute 时重设
        self._closing = False
        self._build_ui(n_init)
        self._pending_initial_compute = (
            self.phase_a is not None and self.phase_b is not None
        )
        self._vtk_initialized = False

    def _set_adaptive_dialog_size(self, parent):
        screen = QGuiApplication.primaryScreen().availableGeometry()

        if parent is not None:
            pg = parent.geometry()

            # 相对父窗口放大一点，但不超过父窗口
            w = int(pg.width() * 0.9)
            h = int(pg.height() * 0.9)

            # 同时不超过屏幕可用区域
            w = min(w, screen.width() - 40)
            h = min(h, screen.height() - 60)

            # 下限，避免太小
            w = max(w, 980)
            h = max(h, 680)

            self.resize(w, h)

            # 居中到父窗口
            x = pg.x() + (pg.width() - w) // 2
            y = pg.y() + (pg.height() - h) // 2
            x = max(screen.x(), min(x, screen.right() - w))
            y = max(screen.y(), min(y, screen.bottom() - h))
            self.move(x, y)
        else:
            w = int(screen.width() * 0.7)
            h = int(screen.height() * 0.7)
            w = max(1000, min(w, 1600))
            h = max(700, min(h, 1000))
            self.resize(w, h)

    @staticmethod
    def _wrap(f, label):
        return f if isinstance(f, PhaseGFunction) \
            else PhaseGFunction.from_callable(f, label=label)

    def _fixed_table_values(self):
        result = {}
        for row in range(self.fixed_table.rowCount()):
            name = self.fixed_table.item(row, 0).text()
            try:
                result[name] = (
                    float(self.fixed_table.item(row, 1).text()),
                    float(self.fixed_table.item(row, 2).text()))
            except (AttributeError, ValueError) as exc:
                raise ValueError(
                    f"Fixed value and tolerance for {name} must be numbers.") from exc
        return result

    def _refresh_fixed_rows(self, *_):
        if getattr(self, "_updating_section", False): return
        try:
            previous = self._fixed_table_values()
        except ValueError:
            previous = {}
        active = {combo.currentText() for combo in self.active_combos}
        fixed = [name for name in self.component_names if name not in active]
        self.fixed_table.setRowCount(len(fixed))
        for row, name in enumerate(fixed):
            value, tolerance = previous.get(name, (0.0, 1e-6))
            name_item = QTableWidgetItem(name); name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.fixed_table.setItem(row, 0, name_item); self.fixed_table.setItem(row, 1, QTableWidgetItem(f"{value:.8g}")); self.fixed_table.setItem(row, 2, QTableWidgetItem(f"{tolerance:.8g}"))

    def _configure_component_ui(self, components):
        self.component_names = tuple(components); self._updating_section = True
        for index, combo in enumerate(self.active_combos):
            combo.clear(); combo.addItems(self.component_names); combo.setCurrentIndex(min(index, len(self.component_names) - 1))
        self._updating_section = False; self._refresh_fixed_rows(); self._update_dynamic_labels()

    def _apply_section(self):
        active = tuple(combo.currentText() for combo in self.active_combos)
        if len(set(active)) != 3: QMessageBox.warning(self, "Section", "Choose three distinct active components."); return
        self.active_components = active
        if self.phase_table_a is not None or self.phase_table_b is not None:
            if self.phase_table_a is None or self.phase_table_b is None: QMessageBox.information(self, "Section", "Load both phase tables first."); return
            try:
                values = self._fixed_table_values(); fixed = {name: pair[0] for name, pair in values.items()}; tolerances = {name: pair[1] for name, pair in values.items()}
                self.section_a = self.phase_table_a.section(active, fixed, tolerances); self.section_b = self.phase_table_b.section(active, fixed, tolerances)
            except Exception as exc: QMessageBox.critical(self, "Invalid section", str(exc)); return
            self.phase_a, self.phase_b = self.section_a, self.section_b
        self._update_dynamic_labels()
        total = self.section_a.active_total if self.section_a is not None else 1.0
        self.spin_x1.setValue(0.5 * total)
        self.spin_x2.setValue(0.2 * total)
        self.on_compute()

    def _update_dynamic_labels(self):
        a, b, c = self.active_components
        if hasattr(self, "axes"):
            self.axes.SetXTitle(a); self.axes.SetYTitle(b); self.axes.SetZTitle("G (scaled)")
        if hasattr(self, "lbl_input_a"):
            self.lbl_input_a.setText(f"{a}:"); self.lbl_input_b.setText(f"{b}:")
            total = self.section_a.active_total if self.section_a is not None else 1.0
            self.inp_group.setTitle(f"Input composition ({c} = {total:.4g} − {a} − {b})")
            for spin in (self.spin_x1, self.spin_x2): spin.setRange(0.0, total)
        if hasattr(self, "ax2d"): self._init_2d_empty()

    # --------- UI ---------
    def _build_ui(self, n_init):
        from PySide6.QtWidgets import QSizePolicy

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        banner = QLabel(
            "<b>Constrained ternary section at fixed T/P.</b> "
            "Both phases must be at the <b>same temperature</b>, "
            "with consistent reference state and units. "
            "For multicomponent data choose three active components and fix all remaining components."
        )
        banner.setStyleSheet(
            "background:#fff8dc; padding:6px; border:1px solid #d2b48c;"
            "font-size:12px;")
        banner.setWordWrap(True)
        banner.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Fixed)
        root.addWidget(banner)

        section_group = QGroupBox("Multicomponent section")
        section_layout = QVBoxLayout(section_group); active_row = QHBoxLayout(); section_layout.addLayout(active_row)
        self.active_combos = []
        for index in range(3):
            combo = QComboBox(); combo.addItems(self.component_names); combo.setCurrentIndex(index)
            active_row.addWidget(QLabel(f"Active {index + 1}:")); active_row.addWidget(combo); self.active_combos.append(combo)
            combo.currentTextChanged.connect(self._refresh_fixed_rows)
        self.btn_apply_section = QPushButton("Apply section"); self.btn_apply_section.clicked.connect(self._apply_section); active_row.addWidget(self.btn_apply_section); active_row.addStretch()
        self.fixed_table = QTableWidget(0, 3); self.fixed_table.setHorizontalHeaderLabels(["Fixed component", "Value", "Tolerance"])
        self.fixed_table.verticalHeader().setVisible(False); self.fixed_table.setMaximumHeight(130); section_layout.addWidget(self.fixed_table)
        self.section_group = section_group; root.addWidget(section_group)

        # -------------------------
        # 顶部双图区域：固定 1:1 等宽，不再使用 splitter
        # 这样既满足左右固定等宽，也可显著减少拖动 splitter 时的残影问题
        # -------------------------
        self._layout_refresh_timer = QTimer(self)
        self._layout_refresh_timer.setSingleShot(True)
        self._layout_refresh_timer.setInterval(60)
        self._layout_refresh_timer.timeout.connect(self._refresh_views_after_layout)

        self.plots_row = QWidget()
        self.plots_row.setAutoFillBackground(True)
        self.plots_row.setStyleSheet("background: white;")
        plots_lay = QHBoxLayout(self.plots_row)
        plots_lay.setContentsMargins(0, 0, 0, 0)
        plots_lay.setSpacing(0)
        root.addWidget(self.plots_row, stretch=1)

        # ---- 左: VTK 3D 视图 ----
        self.vtk_holder = QWidget()
        self.vtk_holder.setAutoFillBackground(True)
        self.vtk_holder.setStyleSheet("background: white;")
        vtk_lay = QVBoxLayout(self.vtk_holder)
        vtk_lay.setContentsMargins(0, 0, 0, 0)
        vtk_lay.setSpacing(0)

        # 顶部占位栏, 与右侧 matplotlib NavToolbar 等高, 保证两侧作图区对齐
        self._vtk_top_spacer = QWidget()
        self._vtk_top_spacer.setFixedHeight(1)
        self._vtk_top_spacer.setSizePolicy(QSizePolicy.Policy.Expanding,
                                           QSizePolicy.Policy.Fixed)
        self._vtk_top_spacer.setStyleSheet("background: white;")
        vtk_lay.addWidget(self._vtk_top_spacer)

        self.vtk_widget = QVTKRenderWindowInteractor(self.vtk_holder)
        vtk_lay.addWidget(self.vtk_widget, stretch=1)

        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(1.0, 1.0, 1.0)
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
        self.iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        style = vtk.vtkInteractorStyleTrackballCamera()
        self.iren.SetInteractorStyle(style)

        # 坐标轴
        self.axes = vtk.vtkCubeAxesActor()
        self.axes.SetCamera(self.renderer.GetActiveCamera())
        self.axes.SetXTitle("x1")
        self.axes.SetYTitle("x2")
        self.axes.SetZTitle("G (scaled)")
        for prop in (
            self.axes.GetTitleTextProperty(0),
            self.axes.GetTitleTextProperty(1),
            self.axes.GetTitleTextProperty(2),
            self.axes.GetLabelTextProperty(0),
            self.axes.GetLabelTextProperty(1),
            self.axes.GetLabelTextProperty(2),
        ):
            prop.SetColor(0.0, 0.0, 0.0)
        self.axes.GetXAxesLinesProperty().SetColor(0, 0, 0)
        self.axes.GetYAxesLinesProperty().SetColor(0, 0, 0)
        self.axes.GetZAxesLinesProperty().SetColor(0, 0, 0)

        # 两个 colorbar
        self._scalar_bar_a = vtk.vtkScalarBarActor()
        self._scalar_bar_a.SetTitle("G_alpha")
        self._scalar_bar_a.SetNumberOfLabels(5)
        self._scalar_bar_a.GetTitleTextProperty().SetColor(0, 0, 0)
        self._scalar_bar_a.GetLabelTextProperty().SetColor(0, 0, 0)
        self._scalar_bar_a.SetPosition(0.01, 0.25)
        self._scalar_bar_a.SetWidth(0.06)
        self._scalar_bar_a.SetHeight(0.5)

        self._scalar_bar_b = vtk.vtkScalarBarActor()
        self._scalar_bar_b.SetTitle("G_beta")
        self._scalar_bar_b.SetNumberOfLabels(5)
        self._scalar_bar_b.GetTitleTextProperty().SetColor(0, 0, 0)
        self._scalar_bar_b.GetLabelTextProperty().SetColor(0, 0, 0)
        self._scalar_bar_b.SetPosition(0.93, 0.25)
        self._scalar_bar_b.SetWidth(0.06)
        self._scalar_bar_b.SetHeight(0.5)

        plots_lay.addWidget(self.vtk_holder, 1)

        # ---- 右: matplotlib 2D 三角图 ----
        self.matplotlib_holder = QWidget()
        self.matplotlib_holder.setAutoFillBackground(True)
        self.matplotlib_holder.setStyleSheet("background: white;")

        right_lay = QVBoxLayout(self.matplotlib_holder)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        self.fig = Figure(figsize=(1, 1))
        self.fig.patch.set_facecolor("white")
        self.ax2d = self.fig.add_subplot(111)
        self.ax2d.set_facecolor("white")
        self.fig.subplots_adjust(left=0.12, right=0.96, bottom=0.10, top=0.92)

        self.canvas = FigureCanvas(self.fig)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding,
                                  QSizePolicy.Policy.Expanding)
        self.canvas.setMinimumSize(100, 100)
        self.canvas.setAutoFillBackground(True)
        self.canvas.setStyleSheet("background: white;")

        self.nav_toolbar = NavToolbar(self.canvas, self.matplotlib_holder)
        self.nav_toolbar.setSizePolicy(QSizePolicy.Policy.Expanding,
                                       QSizePolicy.Policy.Fixed)

        right_lay.addWidget(self.nav_toolbar)
        right_lay.addWidget(self.canvas, stretch=1)

        plots_lay.addWidget(self.matplotlib_holder, 1)
        plots_lay.setStretch(0, 1)
        plots_lay.setStretch(1, 1)

        # 让 VTK 侧顶部占位栏与实际 NavToolbar 高度一致
        self._sync_vtk_top_spacer_height()

        # 初始化一张空白 2D 图，避免 stale pixel buffer
        self._init_2d_empty()

        # ---- 底部控件行 ----
        self.ctrl_bar = QWidget()
        ctrl_bar = self.ctrl_bar
        ctrl_bar.setAutoFillBackground(True)
        ctrl_bar.setStyleSheet("background: white;")
        ctrl_bar.setSizePolicy(QSizePolicy.Policy.Expanding,
                               QSizePolicy.Policy.Fixed)
        ctrl_row = QHBoxLayout(ctrl_bar)
        ctrl_row.setContentsMargins(0, 0, 0, 0)

        io_group = QGroupBox("Data import")
        io_lay = QHBoxLayout(io_group)
        self.btn_load_a = QPushButton("Import phase α (CSV)")
        self.btn_load_b = QPushButton("Import phase β (CSV)")
        self.btn_load_a.clicked.connect(lambda: self.on_load_csv("alpha"))
        self.btn_load_b.clicked.connect(lambda: self.on_load_csv("beta"))
        self.lbl_src_a = QLabel("α: <i>demo</i>" if self.phase_a else "α: —")
        self.lbl_src_b = QLabel("β: <i>demo</i>" if self.phase_b else "β: —")
        self.lbl_src_a.setWordWrap(True)
        self.lbl_src_b.setWordWrap(True)

        a_lay = QVBoxLayout()
        a_lay.addWidget(self.btn_load_a)
        a_lay.addWidget(self.lbl_src_a)

        b_lay = QVBoxLayout()
        b_lay.addWidget(self.btn_load_b)
        b_lay.addWidget(self.lbl_src_b)

        io_lay.addLayout(a_lay)
        io_lay.addSpacing(10)
        io_lay.addLayout(b_lay)
        io_lay.addStretch(1)
        ctrl_row.addWidget(io_group, stretch=2)

        comp_group = QGroupBox("Compute")
        comp_lay = QHBoxLayout(comp_group)
        comp_lay.addWidget(QLabel("grid n:"))
        self.spin_n = QSpinBox()
        self.spin_n.setRange(10, 400)
        self.spin_n.setValue(n_init)
        comp_lay.addWidget(self.spin_n)
        self.btn_compute = QPushButton("Compute")
        self.btn_compute.clicked.connect(self.on_compute)
        comp_lay.addWidget(self.btn_compute)
        comp_lay.addStretch(1)
        ctrl_row.addWidget(comp_group, stretch=1)

        self.inp_group = QGroupBox("Input composition  (x3 = 1 − x1 − x2)")
        inp_lay = QHBoxLayout(self.inp_group)
        self.lbl_input_a = QLabel("x1:")
        inp_lay.addWidget(self.lbl_input_a)
        self.spin_x1 = QDoubleSpinBox()
        self.spin_x1.setRange(0.0, 1.0)
        self.spin_x1.setSingleStep(0.01)
        self.spin_x1.setDecimals(3)
        self.spin_x1.setValue(0.50)
        inp_lay.addWidget(self.spin_x1)

        self.lbl_input_b = QLabel("x2:")
        inp_lay.addWidget(self.lbl_input_b)
        self.spin_x2 = QDoubleSpinBox()
        self.spin_x2.setRange(0.0, 1.0)
        self.spin_x2.setSingleStep(0.01)
        self.spin_x2.setDecimals(3)
        self.spin_x2.setValue(0.20)
        inp_lay.addWidget(self.spin_x2)

        self.btn_update_pt = QPushButton("Update input point")
        self.btn_update_pt.clicked.connect(self.on_update_point)
        inp_lay.addWidget(self.btn_update_pt)
        inp_lay.addStretch(1)
        ctrl_row.addWidget(self.inp_group, stretch=2)

        root.addWidget(ctrl_bar)

        self.lbl_result = QLabel("Load two phases, then press Compute.")
        self.lbl_result.setStyleSheet(
            "font-weight:bold; font-size:13px; padding:6px;"
            "background:#eef; border:1px solid #99c;")
        self.lbl_result.setWordWrap(True)
        self.lbl_result.setSizePolicy(QSizePolicy.Policy.Expanding,
                                      QSizePolicy.Policy.Fixed)
        root.addWidget(self.lbl_result)

    def _init_2d_empty(self):
        """在 canvas 首次进入布局时绘制一张空白三角底图."""
        self.fig.patch.set_facecolor("white")
        self.ax2d.clear()
        self.ax2d.set_facecolor("white")

        a, b, c = self.active_components
        self.ax2d.plot([0, 1, 0, 0], [0, 0, 1, 0], "k-", lw=1)
        self.ax2d.text(1.02, -0.02, f"{a}=1", fontsize=9)
        self.ax2d.text(-0.05, 1.03, f"{b}=1", fontsize=9)
        self.ax2d.text(-0.08, -0.05, f"{c}=1", fontsize=9)
        self.ax2d.set_xlabel(a)
        self.ax2d.set_ylabel(b)
        self.ax2d.set_aspect("equal")
        self.ax2d.set_xlim(-0.1, 1.15)
        self.ax2d.set_ylim(-0.1, 1.15)
        self.ax2d.set_title(
            f"Tie-lines on constrained {a}-{b}-{c} section\n"
            "(load phases and press Compute)")
        self.canvas.draw()

    def _sync_vtk_top_spacer_height(self):
        """让 VTK 容器顶部的占位栏和对面 NavToolbar 高度保持一致,
        使 3D 视图和 2D 画布的顶边对齐."""
        # NavToolbar 的推荐高度
        h = self.nav_toolbar.sizeHint().height()
        if h <= 0:
            h = 30
        self._vtk_top_spacer.setFixedHeight(h)

    def _safe_render_vtk(self):
        if getattr(self, "_closing", False):
            return
        if not hasattr(self, "vtk_widget") or self.vtk_widget is None:
            return
        try:
            rw = self.vtk_widget.GetRenderWindow()
            if rw is not None:
                rw.Render()
        except Exception:
            pass

    def _schedule_view_refresh(self):
        """Coalesce Qt, Matplotlib and native VTK redraws after layout settles."""
        if not self._closing and hasattr(self, "_layout_refresh_timer"):
            self._layout_refresh_timer.start()

    def _refresh_views_after_layout(self):
        # First erase exposed areas through the normal Qt backing store.  The
        # QVTK widget paints directly to a Win32 DC and therefore must render
        # only after its ordinary Qt containers have reached final geometry.
        self._sync_vtk_top_spacer_height()
        for container in (
                getattr(self, "plots_row", None),
                getattr(self, "vtk_holder", None),
                getattr(self, "matplotlib_holder", None)):
            if container is not None:
                container.repaint()

        if hasattr(self, "canvas") and self.canvas is not None:
            try:
                self.canvas.draw()
            except Exception:
                pass

        self._safe_render_vtk()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_view_refresh()

    def showEvent(self, event):
        super().showEvent(event)

        if not self._vtk_initialized:
            self.iren.Initialize()
            self._vtk_initialized = True

        QTimer.singleShot(0, self._finish_first_show)

    def _finish_first_show(self):
        if self._closing:
            return

        self._sync_vtk_top_spacer_height()

        if self._pending_initial_compute:
            self._pending_initial_compute = False
            self.on_compute()
        self._schedule_view_refresh()

    # --------- 槽 ---------
    def on_load_csv(self, which):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select CSV for phase {which}",
            "", "CSV files (*.csv *.txt);;All files (*)")
        if not path:
            return
        try:
            table = load_csv_phase_table(path, parent=self, label=which)
        except Exception as e:
            QMessageBox.critical(self, "Failed to load CSV", str(e))
            return
        if table is None:
            return
        info = (f"{os.path.basename(path)} (n={len(table.gibbs)}, "
                f"components={', '.join(table.components)}, "
                f"G∈[{table.gibbs.min():.3g},{table.gibbs.max():.3g}])")
        if which == "alpha":
            self.phase_table_a = table
            self.phase_a = None
            self.section_a = None
            self.lbl_src_a.setText(f"α: {info}")
        else:
            self.phase_table_b = table
            self.phase_b = None
            self.section_b = None
            self.lbl_src_b.setText(f"β: {info}")
        if self.phase_table_a is None or self.phase_table_b is None:
            self.lbl_result.setText("Load the second phase table, then configure the constrained section.")
            return
        if set(self.phase_table_a.components) != set(self.phase_table_b.components):
            QMessageBox.critical(
                self, "Incompatible phase tables",
                "The two phases must contain the same component columns.\n"
                f"α: {', '.join(self.phase_table_a.components)}\n"
                f"β: {', '.join(self.phase_table_b.components)}")
            if which == "alpha":
                self.phase_table_a = None
                self.lbl_src_a.setText("α: incompatible table; load another CSV")
            else:
                self.phase_table_b = None
                self.lbl_src_b.setText("β: incompatible table; load another CSV")
            return
        canonical = self.phase_table_a.components
        if self.phase_table_b.components != canonical:
            order = [self.phase_table_b.components.index(name) for name in canonical]
            self.phase_table_b = PhaseTable(
                canonical, self.phase_table_b.compositions[:, order],
                self.phase_table_b.gibbs, self.phase_table_b.label)
        self._configure_component_ui(canonical)
        if len(canonical) == 3:
            self._apply_section()
        else:
            self.lbl_result.setText(
                "Choose three active components, enter every fixed fraction and tolerance, "
                "then press Apply section.")

    def on_compute(self):
        if self.phase_a is None or self.phase_b is None:
            QMessageBox.information(
                self, "Missing data",
                "Please load both phases (α and β) first.")
            return
        n = self.spin_n.value()
        try:
            self.result = compute_common_tangent(
                self.phase_a, self.phase_b, n=n)
        except Exception as e:
            QMessageBox.critical(self, "Compute failed", str(e))
            return
        self.draw_3d()
        self.draw_2d()
        self.on_update_point()

    # --------- 3D 绘制 ---------
    def draw_3d(self):
        self.renderer.RemoveAllViewProps()

        grid = self.result["grid"]
        Ga = np.asarray(self.phase_a(grid[:, 0], grid[:, 1]), float)
        Gb = np.asarray(self.phase_b(grid[:, 0], grid[:, 1]), float)

        g_min = float(min(Ga.min(), Gb.min()))
        g_max = float(max(Ga.max(), Gb.max()))
        g_span = max(g_max - g_min, 1e-9)
        self._zscale = 0.6 / g_span

        # alpha surface, rainbow cmap, 不透明
        surf_a = _build_surface_vtk(grid, Ga, zscale=self._zscale)
        mapper_a = vtk.vtkPolyDataMapper()
        mapper_a.SetInputData(surf_a)
        lut_a = _make_lut("rainbow", (Ga.min(), Ga.max()))
        mapper_a.SetLookupTable(lut_a)
        mapper_a.SetScalarRange(Ga.min(), Ga.max())
        mapper_a.ScalarVisibilityOn()
        actor_a = vtk.vtkActor()
        actor_a.SetMapper(mapper_a)
        actor_a.GetProperty().SetOpacity(0.95)
        self.renderer.AddActor(actor_a)

        # beta surface, jet cmap, 半透明 + 显示三角网格线
        surf_b = _build_surface_vtk(grid, Gb, zscale=self._zscale)
        mapper_b = vtk.vtkPolyDataMapper()
        mapper_b.SetInputData(surf_b)
        lut_b = _make_lut("jet", (Gb.min(), Gb.max()))
        mapper_b.SetLookupTable(lut_b)
        mapper_b.SetScalarRange(Gb.min(), Gb.max())
        mapper_b.ScalarVisibilityOn()
        actor_b = vtk.vtkActor()
        actor_b.SetMapper(mapper_b)
        actor_b.GetProperty().SetOpacity(0.45)
        actor_b.GetProperty().EdgeVisibilityOn()
        actor_b.GetProperty().SetEdgeColor(0, 0, 0)
        actor_b.GetProperty().SetLineWidth(0.5)
        self.renderer.AddActor(actor_b)

        # 混合相三角片(金色)
        mixed_pd = _build_mixed_faces_vtk(
            self.result["mixed_faces_3d"], zscale=self._zscale)
        if mixed_pd is not None:
            m = vtk.vtkPolyDataMapper()
            m.SetInputData(mixed_pd)
            m.ScalarVisibilityOff()
            a = vtk.vtkActor()
            a.SetMapper(m)
            a.GetProperty().SetColor(1.0, 0.84, 0.0)  # gold
            a.GetProperty().EdgeVisibilityOn()
            a.GetProperty().SetEdgeColor(0, 0, 0)
            a.GetProperty().SetLineWidth(1.0)
            self.renderer.AddActor(a)

        # tie lines(黑色细线)
        tie_pd = _build_tie_lines_vtk(
            self.result["tie_segments_3d"], zscale=self._zscale)
        if tie_pd is not None:
            m = vtk.vtkPolyDataMapper()
            m.SetInputData(tie_pd)
            m.ScalarVisibilityOff()
            a = vtk.vtkActor()
            a.SetMapper(m)
            a.GetProperty().SetColor(0, 0, 0)
            a.GetProperty().SetLineWidth(1.5)
            self.renderer.AddActor(a)

        # colorbars
        self._scalar_bar_a.SetLookupTable(lut_a)
        self._scalar_bar_b.SetLookupTable(lut_b)
        self.renderer.AddActor2D(self._scalar_bar_a)
        self.renderer.AddActor2D(self._scalar_bar_b)

        # 坐标轴边界
        x_range = (0.0, 1.0)
        y_range = (0.0, 1.0)
        z_range = (g_min * self._zscale, g_max * self._zscale)
        a_name, b_name, _ = self.active_components
        self.axes.SetXTitle(a_name)
        self.axes.SetYTitle(b_name)
        self.axes.SetZTitle("G (scaled)")
        self.axes.SetBounds(
            x_range[0], x_range[1],
            y_range[0], y_range[1],
            z_range[0], z_range[1],
        )
        self.axes.SetCamera(self.renderer.GetActiveCamera())
        self.renderer.AddActor(self.axes)

        # 等轴测视角
        self.renderer.ResetCamera()
        cam = self.renderer.GetActiveCamera()
        cam.Azimuth(30)
        cam.Elevation(25)
        self.renderer.ResetCameraClippingRange()

    def draw_2d(self):
        self.fig.patch.set_facecolor("white")
        self.ax2d.clear()
        self.ax2d.set_facecolor("white")

        a_name, b_name, c_name = self.active_components
        self.ax2d.plot([0, 1, 0, 0], [0, 0, 1, 0], "k-", lw=1)
        self.ax2d.text(1.02, -0.02, f"{a_name}=1", fontsize=9)
        self.ax2d.text(-0.05, 1.03, f"{b_name}=1", fontsize=9)
        self.ax2d.text(-0.08, -0.05, f"{c_name}=1", fontsize=9)

        tie_xy = self.result["tie_segments_xy"]
        for pa, pb in tie_xy:
            self.ax2d.plot([pa[0], pb[0]], [pa[1], pb[1]],
                           "-", color="gray", alpha=0.35, lw=0.8)

        if tie_xy:
            pa_arr = np.array([s[0] for s in tie_xy])
            pb_arr = np.array([s[1] for s in tie_xy])
            self.ax2d.scatter(pa_arr[:, 0], pa_arr[:, 1], s=12,
                              c="tab:blue", label="α endpoints", zorder=3)
            self.ax2d.scatter(pb_arr[:, 0], pb_arr[:, 1], s=12,
                              c="tab:red", label="β endpoints", zorder=3)

        self._input_scatter = self.ax2d.scatter(
            [], [], s=160, c="black", marker="*",
            label="input composition", zorder=5)

        self._active_tie, = self.ax2d.plot(
            [], [], "-", color="limegreen", lw=2.5,
            label="active tie-line", zorder=4)

        self.ax2d.set_xlabel(a_name)
        self.ax2d.set_ylabel(b_name)
        self.ax2d.set_aspect("equal")
        self.ax2d.set_xlim(-0.1, 1.15)
        self.ax2d.set_ylim(-0.1, 1.15)
        self.ax2d.set_title(
            f"Tie-lines on constrained {a_name}-{b_name}-{c_name} section")
        self.ax2d.legend(loc="upper right", fontsize=8)

    def on_update_point(self):
        if self.result is None:
            return
        x1 = self.spin_x1.value()
        x2 = self.spin_x2.value()
        active_total = self.section_a.active_total if self.section_a is not None else 1.0
        if x1 + x2 > active_total + 1e-9:
            self.lbl_result.setText(
                f"Invalid input: the first two active fractions must sum to at most {active_total:.6g}.")
            self._schedule_view_refresh()
            return
        u1, u2 = x1 / active_total, x2 / active_total
        fr = phase_fraction((u1, u2), self.result["tie_segments_xy"])
        if fr is None:
            self.lbl_result.setText(
                "No tie-line found — composition likely in a single-phase "
                "region.")
            self._schedule_view_refresh()
            return
        pa, pb, fa, fb, _ = fr
        if self.section_a is not None:
            input_full = self.section_a.full_composition(u1, u2)
            alpha_full = self.section_a.full_composition(pa[0], pa[1])
            beta_full = self.section_b.full_composition(pb[0], pb[1])
            names = self.section_a.components
        else:
            input_full = np.asarray([u1, u2, 1.0 - u1 - u2])
            alpha_full = np.asarray([pa[0], pa[1], 1.0 - pa[0] - pa[1]])
            beta_full = np.asarray([pb[0], pb[1], 1.0 - pb[0] - pb[1]])
            names = self.active_components
        projected = fa * alpha_full + fb * beta_full
        distance = float(np.linalg.norm(input_full - projected))
        fmt = lambda values: ", ".join(
            f"{name}={value:.4f}" for name, value in zip(names, values))
        msg = (
            f"Overall: {fmt(input_full)}\n"
            f"α: {fmt(alpha_full)}\n"
            f"β: {fmt(beta_full)}\n"
            f"Phase fractions (lever rule): f_α={fa:.4f}, f_β={fb:.4f}   |   "
            f"nearest tie-line distance={distance:.5g}   |   "
            f"grid n={self.result['grid_n']} (Δu={self.result['grid_resolution']:.5g})"
        )
        self.lbl_result.setText(msg)
        self._input_scatter.set_offsets([[u1, u2]])
        self._active_tie.set_data([pa[0], pb[0]], [pa[1], pb[1]])
        self._schedule_view_refresh()

    def closeEvent(self, event):
        self._closing = True

        try:
            if hasattr(self, "_layout_refresh_timer") and self._layout_refresh_timer is not None:
                self._layout_refresh_timer.stop()
        except Exception:
            pass

        # 彻底释放 VTK 资源, 避免 Qt 关闭时残留 OpenGL 上下文报错
        try:
            if hasattr(self, "vtk_widget") and self.vtk_widget is not None:
                self.vtk_widget.Finalize()
        except Exception:
            pass
        super().closeEvent(event)


# =============================================================
# Demo 函数 (保留, 供独立运行测试)
# =============================================================
def Ga_default(x1, x2):
    return 2.0 * (x1 - 0.2) ** 2 + 2.0 * (x2 - 0.2) ** 2 - 0.5


def Gb_default(x1, x2):
    return 2.0 * (x1 - 0.6) ** 2 + 2.0 * (x2 - 0.2) ** 2 - 0.3


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    dlg = CommonTangentDialog(Ga_default, Gb_default, n_init=60)
    dlg.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
