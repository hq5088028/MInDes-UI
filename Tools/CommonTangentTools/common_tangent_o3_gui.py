# Tools/CommonTangentTools/common_tangent_o3_gui.py
"""
两相吉布斯自由能公切面: VTK + PySide6 交互 GUI (重构版, 无 PyVista 依赖).

三元体系 A-B-C (x1 + x2 + x3 = 1), 两相 alpha 和 beta,
固定温度下的两个吉布斯自由能曲面 G_alpha(x1,x2), G_beta(x1,x2).

用法:
  1) 独立运行:  python common_tangent_o3_gui.py
  2) 作为子对话框: CommonTangentDialog(parent).exec()

CSV 文件格式: 三列 x1, x2, G (表头可有可无), 要求 x1>=0, x2>=0, x1+x2<=1.

依赖: PySide6, vtk, numpy, pandas, scipy, matplotlib (均已在 MInDes-UI 中).
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd
from scipy.spatial import ConvexHull
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator

from PySide6.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QDoubleSpinBox, QSpinBox, QPushButton, QSplitter,
    QFileDialog, QMessageBox, QGroupBox,
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
        pts = np.column_stack([x1, x2])
        lin = LinearNDInterpolator(pts, G)
        nn = NearestNDInterpolator(pts, G)

        def _f(a, b):
            a = np.atleast_1d(a).astype(float)
            b = np.atleast_1d(b).astype(float)
            val = lin(a, b)
            mask = np.isnan(val)
            if mask.any():
                val[mask] = nn(a[mask], b[mask])
            return val

        meta = {"source": "table", "n_points": int(len(x1)),
                "x1_range": (float(x1.min()), float(x1.max())),
                "x2_range": (float(x2.min()), float(x2.max())),
                "G_range":  (float(G.min()),  float(G.max()))}
        return cls(_f, label=label, meta=meta)


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
    pts = []
    for i in range(n + 1):
        for j in range(n + 1 - i):
            pts.append((i / n, j / n))
    return np.array(pts)


def lower_hull_simplices(points3d):
    hull = ConvexHull(points3d)
    simplices = []
    for simplex, eq in zip(hull.simplices, hull.equations):
        if eq[2] < -1e-12:
            simplices.append(simplex)
    return np.array(simplices)


def compute_common_tangent(Ga_func, Gb_func, n=60):
    grid = triangle_grid(n)
    Ga = np.asarray(Ga_func(grid[:, 0], grid[:, 1]), float)
    Gb = np.asarray(Gb_func(grid[:, 0], grid[:, 1]), float)
    big = np.nanmax([np.nanmax(Ga), np.nanmax(Gb)]) + 1e3
    Ga = np.where(np.isnan(Ga), big, Ga)
    Gb = np.where(np.isnan(Gb), big, Gb)

    pts_a = np.column_stack([grid, Ga])
    pts_b = np.column_stack([grid, Gb])
    all_points = np.vstack([pts_a, pts_b])
    M = len(grid)
    label = np.concatenate([np.zeros(M, int), np.ones(M, int)])

    simplices = lower_hull_simplices(all_points)

    tie_segments_xy = []
    tie_segments_3d = []
    mixed_faces_3d = []
    for s in simplices:
        ls = label[s]
        if ls.min() == 0 and ls.max() == 1:
            mixed_faces_3d.append(all_points[s])
            for i in range(3):
                for j in range(i + 1, 3):
                    if label[s[i]] != label[s[j]]:
                        a_idx = s[i] if label[s[i]] == 0 else s[j]
                        b_idx = s[j] if label[s[j]] == 1 else s[i]
                        tie_segments_xy.append(
                            (all_points[a_idx, :2], all_points[b_idx, :2])
                        )
                        tie_segments_3d.append(
                            (all_points[a_idx], all_points[b_idx])
                        )
    return dict(
        grid=grid, all_points=all_points, phase_label=label,
        simplices=simplices,
        tie_segments_xy=tie_segments_xy,
        tie_segments_3d=tie_segments_3d,
        mixed_faces_3d=mixed_faces_3d,
    )


def phase_fraction(x_total, tie_segments_xy):
    x_total = np.array(x_total, float)
    best = None
    best_d = np.inf
    for pa, pb in tie_segments_xy:
        pa = np.asarray(pa, float)
        pb = np.asarray(pb, float)
        v = pb - pa
        L2 = v @ v
        if L2 < 1e-14:
            continue
        t = np.clip((x_total - pa) @ v / L2, 0.0, 1.0)
        d = np.linalg.norm(x_total - (pa + t * v))
        if d < best_d:
            best_d = d
            best = (pa, pb, 1.0 - t, t, d)
    return best


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

    # --------- UI ---------
    def _build_ui(self, n_init):
        from PySide6.QtWidgets import QSizePolicy

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        banner = QLabel(
            "<b>Ternary system</b> (x1 + x2 + x3 = 1). "
            "Both phases must be at the <b>same temperature</b>, "
            "with consistent reference state and units. "
            "CSV columns: <b>x1, x2, G</b> (header optional)."
        )
        banner.setStyleSheet(
            "background:#fff8dc; padding:6px; border:1px solid #d2b48c;"
            "font-size:12px;")
        banner.setWordWrap(True)
        banner.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Fixed)
        root.addWidget(banner)

        # -------------------------
        # 顶部双图区域：固定 1:1 等宽，不再使用 splitter
        # 这样既满足左右固定等宽，也可显著减少拖动 splitter 时的残影问题
        # -------------------------
        self._layout_refresh_timer = QTimer(self)
        self._layout_refresh_timer.setSingleShot(True)
        self._layout_refresh_timer.timeout.connect(self._refresh_views_after_layout)

        plots_row = QWidget()
        plots_row.setAutoFillBackground(True)
        plots_row.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        plots_row.setStyleSheet("background: white;")
        plots_lay = QHBoxLayout(plots_row)
        plots_lay.setContentsMargins(0, 0, 0, 0)
        plots_lay.setSpacing(0)
        root.addWidget(plots_row, stretch=1)

        # ---- 左: VTK 3D 视图 ----
        vtk_holder = QWidget()
        vtk_holder.setAutoFillBackground(True)
        vtk_holder.setStyleSheet("background: white;")
        vtk_lay = QVBoxLayout(vtk_holder)
        vtk_lay.setContentsMargins(0, 0, 0, 0)
        vtk_lay.setSpacing(0)

        # 顶部占位栏, 与右侧 matplotlib NavToolbar 等高, 保证两侧作图区对齐
        self._vtk_top_spacer = QWidget()
        self._vtk_top_spacer.setFixedHeight(1)
        self._vtk_top_spacer.setSizePolicy(QSizePolicy.Policy.Expanding,
                                           QSizePolicy.Policy.Fixed)
        self._vtk_top_spacer.setStyleSheet("background: white;")
        vtk_lay.addWidget(self._vtk_top_spacer)

        self.vtk_widget = QVTKRenderWindowInteractor(vtk_holder)
        self.vtk_widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.vtk_widget.setAutoFillBackground(True)
        self.vtk_widget.setStyleSheet("background: white;")
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

        plots_lay.addWidget(vtk_holder, 1)

        # ---- 右: matplotlib 2D 三角图 ----
        right = QWidget()
        right.setAutoFillBackground(True)
        right.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        right.setStyleSheet("background: white;")

        right_lay = QVBoxLayout(right)
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
        self.canvas.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.canvas.setAutoFillBackground(True)
        self.canvas.setStyleSheet("background: white;")

        self.nav_toolbar = NavToolbar(self.canvas, right)
        self.nav_toolbar.setSizePolicy(QSizePolicy.Policy.Expanding,
                                       QSizePolicy.Policy.Fixed)

        right_lay.addWidget(self.nav_toolbar)
        right_lay.addWidget(self.canvas, stretch=1)

        plots_lay.addWidget(right, 1)
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

        inp_group = QGroupBox("Input composition  (x3 = 1 − x1 − x2)")
        inp_lay = QHBoxLayout(inp_group)
        inp_lay.addWidget(QLabel("x1:"))
        self.spin_x1 = QDoubleSpinBox()
        self.spin_x1.setRange(0.0, 1.0)
        self.spin_x1.setSingleStep(0.01)
        self.spin_x1.setDecimals(3)
        self.spin_x1.setValue(0.50)
        inp_lay.addWidget(self.spin_x1)

        inp_lay.addWidget(QLabel("x2:"))
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
        ctrl_row.addWidget(inp_group, stretch=2)

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

        self.ax2d.plot([0, 1, 0, 0], [0, 0, 1, 0], "k-", lw=1)
        self.ax2d.text(1.02, -0.02, "A  (x1=1)", fontsize=9)
        self.ax2d.text(-0.05, 1.03, "B  (x2=1)", fontsize=9)
        self.ax2d.text(-0.08, -0.05, "C  (x3=1)", fontsize=9)
        self.ax2d.set_xlabel("x1")
        self.ax2d.set_ylabel("x2")
        self.ax2d.set_aspect("equal")
        self.ax2d.set_xlim(-0.1, 1.15)
        self.ax2d.set_ylim(-0.1, 1.15)
        self.ax2d.set_title(
            "Tie-lines on composition triangle (A-B-C)\n"
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

    def _refresh_views_after_layout(self):
        # 保证左右顶部对齐
        self._sync_vtk_top_spacer_height()

        # Matplotlib 做一次完整重绘，清掉 stale buffer
        if hasattr(self, "canvas") and self.canvas is not None:
            try:
                self.canvas.draw()
            except Exception:
                pass

        # VTK 在布局稳定后再渲染一次
        self._safe_render_vtk()

        # 强制底部控件重新盖住上方绘图区，进一步抑制虚影
        try:
            if hasattr(self, "ctrl_bar") and self.ctrl_bar is not None:
                self.ctrl_bar.update()
                self.ctrl_bar.raise_()
            if hasattr(self, "lbl_result") and self.lbl_result is not None:
                self.lbl_result.update()
                self.lbl_result.raise_()
            self.update()
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if hasattr(self, "_vtk_top_spacer") and hasattr(self, "nav_toolbar"):
            self._sync_vtk_top_spacer_height()

        # 统一在布局稳定后刷新两侧视图，避免 resize 过程中产生重复虚影
        if hasattr(self, "_layout_refresh_timer") and not self._closing:
            self._layout_refresh_timer.start(0)

    def showEvent(self, event):
        super().showEvent(event)

        if not self._vtk_initialized:
            self.iren.Initialize()
            self._vtk_initialized = True

        QTimer.singleShot(0, self._finish_first_show)

    def _finish_first_show(self):
        if self._closing:
            return
    
        # 重新按父窗口/屏幕再校正一次大小，确保是最终几何
        self._set_adaptive_dialog_size(self.parentWidget())
    
        self._sync_vtk_top_spacer_height()
    
        if self._pending_initial_compute:
            self._pending_initial_compute = False
            self.on_compute()
        else:
            try:
                self.canvas.draw()
            except Exception:
                pass
            self._safe_render_vtk()
    
        # 让底部控件最后再刷一遍，覆盖掉旧残影
        try:
            self.ctrl_bar.update()
            self.ctrl_bar.raise_()
            self.lbl_result.update()
            self.lbl_result.raise_()
            self.update()
        except Exception:
            pass

    # --------- 槽 ---------
    def on_load_csv(self, which):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select CSV for phase {which}",
            "", "CSV files (*.csv *.txt);;All files (*)")
        if not path:
            return
        try:
            phase = load_csv_phase(path, label=which)
        except Exception as e:
            QMessageBox.critical(self, "Failed to load CSV", str(e))
            return
        m = phase.meta
        info = (f"{os.path.basename(path)} "
                f"(n={m['n_points']}, "
                f"G∈[{m['G_range'][0]:.3g},{m['G_range'][1]:.3g}])")
        if which == "alpha":
            self.phase_a = phase
            self.lbl_src_a.setText(f"α: {info}")
        else:
            self.phase_b = phase
            self.lbl_src_b.setText(f"β: {info}")
        if self.phase_a is not None and self.phase_b is not None:
            self.on_compute()

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
        self._safe_render_vtk()

    def draw_2d(self):
        self.fig.patch.set_facecolor("white")
        self.ax2d.clear()
        self.ax2d.set_facecolor("white")

        self.ax2d.plot([0, 1, 0, 0], [0, 0, 1, 0], "k-", lw=1)
        self.ax2d.text(1.02, -0.02, "A  (x1=1)", fontsize=9)
        self.ax2d.text(-0.05, 1.03, "B  (x2=1)", fontsize=9)
        self.ax2d.text(-0.08, -0.05, "C  (x3=1)", fontsize=9)

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

        self.ax2d.set_xlabel("x1")
        self.ax2d.set_ylabel("x2")
        self.ax2d.set_aspect("equal")
        self.ax2d.set_xlim(-0.1, 1.15)
        self.ax2d.set_ylim(-0.1, 1.15)
        self.ax2d.set_title("Tie-lines on composition triangle (A-B-C)")
        self.ax2d.legend(loc="upper right", fontsize=8)

        # 这里用 draw()，比 draw_idle() 更强，优先消除 splitter 拖动后的残影
        self.canvas.draw()

    def on_update_point(self):
        if self.result is None:
            return
        x1 = self.spin_x1.value()
        x2 = self.spin_x2.value()
        if x1 + x2 > 1.0 + 1e-9:
            self.lbl_result.setText(
                "⚠ Invalid input: x1 + x2 must be ≤ 1 (ternary constraint).")
            return
        fr = phase_fraction((x1, x2), self.result["tie_segments_xy"])
        if fr is None:
            self.lbl_result.setText(
                "No tie-line found — composition likely in a single-phase "
                "region.")
            return
        pa, pb, fa, fb, d = fr
        x3 = 1.0 - x1 - x2
        pa3 = 1.0 - pa[0] - pa[1]
        pb3 = 1.0 - pb[0] - pb[1]
        msg = (
            f"Input  (x1,x2,x3) = ({x1:.3f}, {x2:.3f}, {x3:.3f})   "
            f"| dist to nearest tie-line = {d:.4f}\n"
            f"α composition  (x1,x2,x3) = ({pa[0]:.3f}, {pa[1]:.3f}, {pa3:.3f})\n"
            f"β composition  (x1,x2,x3) = ({pb[0]:.3f}, {pb[1]:.3f}, {pb3:.3f})\n"
            f"Phase fractions (lever rule, molar basis): "
            f"f_α = {fa:.4f},  f_β = {fb:.4f}"
        )
        self.lbl_result.setText(msg)
        self._input_scatter.set_offsets([[x1, x2]])
        self._active_tie.set_data([pa[0], pb[0]], [pa[1], pb[1]])
        self.canvas.draw()

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