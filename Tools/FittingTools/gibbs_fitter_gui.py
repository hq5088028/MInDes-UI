# Tools/FittingTools/gibbs_fitter_gui.py
"""
Ternary Gibbs free energy polynomial fitting — PySide6 GUI (重构版, 去 Tkinter).

Features 完全保留:
* Load CSV (columns x1, x2, G).
* bivariate 或 ternary 拟合, 每变量独立阶数.
* 显示拟合质量 (RMSE, max|err|, R^2) 和系数表.
* 三个对比视图:
    - 3D scatter + fitted surface
    - Contour comparison (raw vs fitted)
    - Residual map
* 导出系数表 CSV 和原始-拟合 CSV.

依赖: PySide6, numpy, pandas, matplotlib (均已在 MInDes-UI 中).
"""
from __future__ import annotations

import os
import sys
import traceback

import numpy as np
import pandas as pd

from PySide6.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSpinBox, QComboBox, QSplitter,
    QFileDialog, QMessageBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QGroupBox, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

import matplotlib
matplotlib.use("QtAgg")  # 显式指定, 避免误拉 TkAgg
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavToolbar
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

try:
    # 作为 Tools.FittingTools 包的子模块被 import 时
    from . import fitter_core as fc
except ImportError:
    # 独立脚本运行 (python gibbs_fitter_gui.py) 时的 fallback
    import fitter_core as fc

APP_TITLE = "Ternary Gibbs Free Energy Polynomial Fitter"
DEFAULT_GRID_N = 80


class FitterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_TITLE)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self._set_adaptive_dialog_size(parent)

        # state
        self.df: pd.DataFrame | None = None
        self.csv_path: str | None = None
        self.result: fc.FitResult | None = None

        self._build_ui()

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

    # -- UI construction ----------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)

        # --- 顶部控制栏 ---
        top = QHBoxLayout()
        root.addLayout(top)

        self.btn_load = QPushButton("Load CSV...")
        self.btn_load.clicked.connect(self.on_load_csv)
        top.addWidget(self.btn_load)

        self.lbl_file = QLabel("(no file)")
        self.lbl_file.setStyleSheet("color:#555;")
        top.addWidget(self.lbl_file, stretch=1)

        top.addWidget(QLabel("Mode:"))
        self.cbo_mode = QComboBox()
        self.cbo_mode.addItems(["bivariate", "ternary"])
        self.cbo_mode.setCurrentText("ternary")
        self.cbo_mode.currentTextChanged.connect(self._update_degree_widgets)
        top.addWidget(self.cbo_mode)

        # degree spinboxes
        self.lbl_d1 = QLabel("deg x1:")
        self.spn_d1 = QSpinBox()
        self.spn_d1.setRange(0, 12)
        self.spn_d1.setValue(4)
        self.lbl_d2 = QLabel("deg x2:")
        self.spn_d2 = QSpinBox()
        self.spn_d2.setRange(0, 12)
        self.spn_d2.setValue(4)
        self.lbl_d3 = QLabel("deg x3:")
        self.spn_d3 = QSpinBox()
        self.spn_d3.setRange(0, 12)
        self.spn_d3.setValue(4)
        for w in (self.lbl_d1, self.spn_d1, self.lbl_d2, self.spn_d2,
                  self.lbl_d3, self.spn_d3):
            top.addWidget(w)

        self.btn_fit = QPushButton("Fit")
        self.btn_fit.clicked.connect(self.on_fit)
        top.addWidget(self.btn_fit)

        self.btn_export_coef = QPushButton("Export coefficients...")
        self.btn_export_coef.clicked.connect(self.on_export_coeffs)
        top.addWidget(self.btn_export_coef)

        self.btn_export_data = QPushButton("Export data+fit...")
        self.btn_export_data.clicked.connect(self.on_export_data)
        top.addWidget(self.btn_export_data)

        self._update_degree_widgets()

        # --- 主体: 左右分栏 ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, stretch=1)

        # 左: 摘要 + 系数表
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)

        gb_stats = QGroupBox("Fit summary")
        stats_lay = QVBoxLayout(gb_stats)
        self.lbl_summary = QLabel("(no fit yet)")
        self.lbl_summary.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px;")
        stats_lay.addWidget(self.lbl_summary)
        left_lay.addWidget(gb_stats)

        gb_coef = QGroupBox("Coefficients")
        coef_lay = QVBoxLayout(gb_coef)
        self.tbl_coef = QTableWidget(0, 4)
        self.tbl_coef.setHorizontalHeaderLabels(
            ["i (x1)", "j (x2)", "k (x3)", "coefficient"])
        self.tbl_coef.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_coef.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_coef.verticalHeader().setVisible(False)
        hh = self.tbl_coef.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        coef_lay.addWidget(self.tbl_coef)
        left_lay.addWidget(gb_coef, stretch=1)

        splitter.addWidget(left)

        # 右: 三个 tab
        right = QTabWidget()
        self.tab_3d = self._make_plot_tab()
        self.tab_ct = self._make_plot_tab()
        self.tab_res = self._make_plot_tab()
        right.addTab(self.tab_3d["widget"], "3D surface")
        right.addTab(self.tab_ct["widget"], "Contours (raw vs fit)")
        right.addTab(self.tab_res["widget"], "Residuals")
        splitter.addWidget(right)
        splitter.setSizes([340, 620])

        # --- 状态栏 ---
        self.lbl_status = QLabel("Load a CSV to begin.")
        self.lbl_status.setStyleSheet(
            "background:#f0f0f0; padding:3px; border-top:1px solid #aaa;")
        root.addWidget(self.lbl_status)

    def _make_plot_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        fig = Figure(figsize=(6, 5))
        canvas = FigureCanvas(fig)
        lay.addWidget(NavToolbar(canvas, w))
        lay.addWidget(canvas)
        return {"widget": w, "fig": fig, "canvas": canvas}

    def _update_degree_widgets(self):
        is_ternary = (self.cbo_mode.currentText() == "ternary")
        self.lbl_d3.setVisible(is_ternary)
        self.spn_d3.setVisible(is_ternary)

    # -- actions ------------------------------------------------------------
    def on_load_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV file", "",
            "CSV files (*.csv);;All files (*.*)")
        if not path:
            return
        try:
            df = fc.load_csv(path)
        except Exception as e:
            QMessageBox.critical(self, "Failed to load CSV", str(e))
            return
        self.df = df
        self.csv_path = path
        self.lbl_file.setText(os.path.basename(path))
        self.lbl_status.setText(
            f"Loaded {len(df)} rows from {os.path.basename(path)}. "
            f"x1 in [{df['x1'].min():.3g}, {df['x1'].max():.3g}], "
            f"x2 in [{df['x2'].min():.3g}, {df['x2'].max():.3g}], "
            f"G in [{df['G'].min():.4g}, {df['G'].max():.4g}]."
        )
        self.result = None
        self._render_raw_only()

    def on_fit(self):
        if self.df is None:
            QMessageBox.information(self, "No data", "Please load a CSV first.")
            return
        mode = self.cbo_mode.currentText()
        try:
            if mode == "bivariate":
                degrees = (self.spn_d1.value(), self.spn_d2.value())
            else:
                degrees = (self.spn_d1.value(),
                           self.spn_d2.value(),
                           self.spn_d3.value())
            result = fc.fit(self.df, mode, degrees)
        except Exception as e:
            QMessageBox.critical(
                self, "Fit failed", f"{e}\n\n{traceback.format_exc()}")
            return
        self.result = result
        self._refresh_summary()
        self._refresh_coeff_table()
        self._refresh_plots()
        self.lbl_status.setText(
            f"Fit OK | mode={result.mode} degrees={result.degrees} "
            f"params={result.n_params} RMSE={result.rmse:.4g} "
            f"max|err|={result.max_abs_err:.4g} R^2={result.r2:.6f}"
        )

    def on_export_coeffs(self):
        if self.result is None:
            QMessageBox.information(self, "No fit", "Run a fit first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save coefficient table", "coefficients.csv",
            "CSV (*.csv)")
        if not path:
            return
        try:
            table = fc.coeff_table(self.result)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(f"# mode,{self.result.mode}\n")
                f.write(f"# degrees,{','.join(map(str, self.result.degrees))}\n")
                f.write(f"# n_points,{self.result.n_points}\n")
                f.write(f"# n_params,{self.result.n_params}\n")
                f.write(f"# rmse,{self.result.rmse}\n")
                f.write(f"# max_abs_err,{self.result.max_abs_err}\n")
                f.write(f"# r2,{self.result.r2}\n")
                table.to_csv(f, index=False)
            QMessageBox.information(self, "Saved", f"Wrote {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def on_export_data(self):
        if self.result is None or self.df is None:
            QMessageBox.information(self, "No fit", "Run a fit first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save data + fit", "data_vs_fit.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            x1 = self.df["x1"].to_numpy()
            x2 = self.df["x2"].to_numpy()
            G_true = self.df["G"].to_numpy()
            G_fit = fc.predict(self.result, x1, x2)
            out = pd.DataFrame({
                "x1": x1, "x2": x2, "x3": 1 - x1 - x2,
                "G_data": G_true, "G_fit": G_fit,
                "residual": G_true - G_fit,
            })
            out.to_csv(path, index=False)
            QMessageBox.information(self, "Saved", f"Wrote {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    # -- rendering ----------------------------------------------------------
    def _refresh_summary(self):
        r = self.result
        if r is None:
            self.lbl_summary.setText("(no fit yet)")
            return
        lines = [
            f"Mode:       {r.mode}",
            f"Degrees:    {r.degrees}",
            f"# points:   {r.n_points}",
            f"# params:   {r.n_params}",
            f"RMSE:       {r.rmse:.6g}",
            f"max |err|:  {r.max_abs_err:.6g}",
            f"R^2:        {r.r2:.8f}",
        ]
        self.lbl_summary.setText("\n".join(lines))

    def _refresh_coeff_table(self):
        self.tbl_coef.setRowCount(0)
        if self.result is None:
            return
        is_bivar = (self.result.mode == "bivariate")
        # 第 3 列的显示/隐藏由 setColumnHidden 控制, 比改 header 稳
        self.tbl_coef.setColumnHidden(2, is_bivar)

        for exps, c in zip(self.result.terms, self.result.coeffs):
            row = self.tbl_coef.rowCount()
            self.tbl_coef.insertRow(row)
            self.tbl_coef.setItem(row, 0, QTableWidgetItem(str(exps[0])))
            self.tbl_coef.setItem(row, 1, QTableWidgetItem(str(exps[1])))
            if is_bivar:
                self.tbl_coef.setItem(row, 2, QTableWidgetItem(""))
            else:
                self.tbl_coef.setItem(row, 2, QTableWidgetItem(str(exps[2])))
            item = QTableWidgetItem(f"{c:+.6e}")
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_coef.setItem(row, 3, item)

    def _render_raw_only(self):
        """仅绘制原始散点, 清空其他两个 tab."""
        fig = self.tab_3d["fig"]
        fig.clf()
        ax = fig.add_subplot(111, projection="3d")
        if self.df is not None:
            ax.scatter(self.df["x1"], self.df["x2"], self.df["G"],
                       s=4, c=self.df["G"], cmap="viridis")
            ax.set_xlabel("x1")
            ax.set_ylabel("x2")
            ax.set_zlabel("G")
            ax.set_title("Raw data (no fit)")
        self.tab_3d["canvas"].draw_idle()

        self.tab_ct["fig"].clf()
        self.tab_ct["canvas"].draw_idle()
        self.tab_res["fig"].clf()
        self.tab_res["canvas"].draw_idle()

    def _refresh_plots(self):
        if self.df is None or self.result is None:
            return
        self._plot_3d()
        self._plot_contours()
        self._plot_residuals()

    def _grid_over_simplex(self, n=DEFAULT_GRID_N):
        g = np.linspace(0.0, 1.0, n)
        X1, X2 = np.meshgrid(g, g)
        mask = (X1 + X2) <= 1.0 + 1e-9
        return X1, X2, mask

    def _plot_3d(self):
        fig = self.tab_3d["fig"]
        fig.clf()
        ax = fig.add_subplot(111, projection="3d")
        df = self.df
        ax.scatter(df["x1"], df["x2"], df["G"],
                   s=5, c="k", alpha=0.25, label="data")
        X1, X2, mask = self._grid_over_simplex()
        Z = fc.predict(self.result, X1, X2)
        Zm = np.where(mask, Z, np.nan)
        ax.plot_surface(X1, X2, Zm, cmap="viridis", alpha=0.75,
                        linewidth=0, antialiased=True)
        ax.set_xlabel("x1")
        ax.set_ylabel("x2")
        ax.set_zlabel("G")
        ax.set_title(
            f"Data (black dots) vs fitted surface — "
            f"mode={self.result.mode}, degrees={self.result.degrees}"
        )
        self.tab_3d["canvas"].draw_idle()

    def _plot_contours(self):
        fig = self.tab_ct["fig"]
        fig.clf()
        df = self.df

        from matplotlib.tri import Triangulation
        tri = Triangulation(df["x1"].values, df["x2"].values)

        ax1 = fig.add_subplot(1, 2, 1)
        tcf1 = ax1.tricontourf(tri, df["G"].values, levels=20, cmap="viridis")
        ax1.set_title("Raw G")
        ax1.set_xlabel("x1")
        ax1.set_ylabel("x2")
        ax1.set_aspect("equal")
        ax1.plot([0, 1, 0, 0], [0, 0, 1, 0], "k-", lw=1)
        fig.colorbar(tcf1, ax=ax1, shrink=0.8)

        ax2 = fig.add_subplot(1, 2, 2)
        X1, X2, mask = self._grid_over_simplex()
        Z = fc.predict(self.result, X1, X2)
        Zm = np.where(mask, Z, np.nan)
        levels = tcf1.levels
        cf2 = ax2.contourf(X1, X2, Zm, levels=levels, cmap="viridis")
        ax2.set_title(f"Fitted G ({self.result.mode}, {self.result.degrees})")
        ax2.set_xlabel("x1")
        ax2.set_ylabel("x2")
        ax2.set_aspect("equal")
        ax2.plot([0, 1, 0, 0], [0, 0, 1, 0], "k-", lw=1)
        fig.colorbar(cf2, ax=ax2, shrink=0.8)

        fig.tight_layout()
        self.tab_ct["canvas"].draw_idle()

    def _plot_residuals(self):
        fig = self.tab_res["fig"]
        fig.clf()
        df = self.df
        G_fit = fc.predict(self.result, df["x1"].values, df["x2"].values)
        resid = df["G"].values - G_fit

        ax1 = fig.add_subplot(1, 2, 1)
        vmax = float(np.max(np.abs(resid))) if len(resid) else 1.0
        sc = ax1.scatter(df["x1"], df["x2"], c=resid, cmap="RdBu_r",
                         s=10, vmin=-vmax, vmax=vmax)
        ax1.plot([0, 1, 0, 0], [0, 0, 1, 0], "k-", lw=1)
        ax1.set_aspect("equal")
        ax1.set_xlabel("x1")
        ax1.set_ylabel("x2")
        ax1.set_title("Residual (data - fit) over composition")
        fig.colorbar(sc, ax=ax1, shrink=0.8)

        ax2 = fig.add_subplot(1, 2, 2)
        ax2.hist(resid, bins=50, color="#6a8caf", edgecolor="k")
        ax2.set_xlabel("residual")
        ax2.set_ylabel("count")
        ax2.set_title(
            f"Residual histogram\nRMSE={self.result.rmse:.4g}, "
            f"max|err|={self.result.max_abs_err:.4g}"
        )

        fig.tight_layout()
        self.tab_res["canvas"].draw_idle()


# ---------------------------------------------------------------------------
def main():
    app = QApplication.instance() or QApplication(sys.argv)
    dlg = FitterDialog()
    dlg.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()