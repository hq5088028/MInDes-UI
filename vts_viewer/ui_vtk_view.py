# ui_vtk_view.py
import vtk
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget,
    QTableView, QAbstractItemView
)
from PySide6.QtCore import Qt

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor


class VTKViewMixin:
    """
    负责：
    - VTK RenderWindow + Renderer + Interactor
    - TabWidget（3D View / Plot Over Line）
    - Plot Over Line 的 UI 容器（不含逻辑）
    """

    def _create_vtk_and_tabs(self):
        # =========================
        # VTK Render Window
        # =========================
        self.vtk_widget = QVTKRenderWindowInteractor()

        self.renderer = vtk.vtkRenderer()
        self.update_background_color()  # 使用主类已有方法

        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)

        self.iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        self.iren.SetInteractorStyle(
            vtk.vtkInteractorStyleTrackballCamera()
        )
        self.iren.Initialize()

        # =========================
        # Tab Widget
        # =========================
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.vtk_widget, "3D View")

        # =========================
        # Plot Over Line Tab
        # =========================
        self.plot_tab = QWidget()
        plot_layout = QVBoxLayout(self.plot_tab)
        # 上半：Matplotlib 图
        self.plot_figure = Figure()
        self.plot_canvas = FigureCanvas(self.plot_figure)
        plot_layout.addWidget(self.plot_canvas)
        # 下半：表格
        self.line_table_view = QTableView()
        self.line_table_view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.line_table_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.line_table_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.line_table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.line_table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        plot_layout.addWidget(self.line_table_view)
        self.tab_widget.addTab(self.plot_tab, "Plot Over Line")
        # plot lines 初始化
        self._line_styles = {}
        self.active_line_data = None  # 单条线数据 DataFrame
        self.line_widget = None
        self.DEFAULT_COLOR_CYCLE = [
            (0.12156862745098039, 0.4666666666666667, 0.7058823529411765),  # blue
            (1.0, 0.4980392156862745, 0.054901960784313725),                # orange
            (0.17254901960784313, 0.6274509803921569, 0.17254901960784313),  # green
            (0.8392156862745098, 0.15294117647058825, 0.1568627450980392),   # red
            (0.5803921568627451, 0.403921568627451, 0.7411764705882353),     # purple
            (0.5490196078431373, 0.33725490196078434, 0.29411764705882354),  # brown
            (0.8901960784313725, 0.4666666666666667, 0.7607843137254902),   # pink
            (0.4980392156862745, 0.4980392156862745, 0.4980392156862745),   # gray
            (0.7372549019607844, 0.7411764705882353, 0.13333333333333333),  # olive
            (0.09019607843137255, 0.7450980392156863, 0.8117647058823529),  # cyan
        ]
        self.plot_line_p1 = None  # e.g., [x, y, z]
        self.plot_line_p2 = None  # e.g., [x, y, z]
        self.tab_widget.setCurrentIndex(0)  # 默认显示 3D VTS 界面
