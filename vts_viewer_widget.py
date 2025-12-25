import os
import math
import re
import pandas as pd
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtGui import QPixmap, QPainter, QColor, QDoubleValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QComboBox, QFileDialog,
    QLabel, QGroupBox, QCheckBox, QColorDialog, QDoubleSpinBox, QLineEdit,
    QTabWidget, QTableView, QAbstractItemView, QHeaderView,
    QGridLayout, QScrollArea, QSizePolicy, QInputDialog, QMessageBox
)
from PySide6.QtCore import QAbstractTableModel, Qt, QTimer
import vtk
from vtk.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor


def clean_excel_string(val):
    """
    清洗字符串，移除 openpyxl 不支持的非法字符。
    保留 \t, \n, \r，移除其他控制字符。
    """
    if isinstance(val, str):
        # 只保留合法字符： printable ASCII + tab, newline, return
        return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', val)
    return val

class PandasModel(QAbstractTableModel):
    def __init__(self, data):
        super().__init__()
        self._data = data

    def rowCount(self, parent=None):
        return self._data.shape[0]

    def columnCount(self, parent=None):
        return self._data.shape[1]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return str(self._data.columns[section])
            else:
                return str(self._data.index[section])
        return None

class VTSViewerWidget(QWidget):
    def __init__(self):
        super().__init__()
        # ✅ 只在这里设置主布局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.current_data = None
        self.arrow_color = (1.0, 1.0, 1.0)  # white
        self.current_vis_mode = "Surface"
        self.control_panel_width = 300

        # === Control Panel ===
        control_panel = self._create_control_panel()
        control_panel.setFixedWidth(self.control_panel_width)

        # === VTK + Plot Tabs ===
        self._create_vtk_and_tabs()  # 封装 VTK 和 Tab 创建逻辑

        self.tab_widget.setTabEnabled(1, False)  # 🔑 禁用/启用 tab
        main_layout.addWidget(control_panel)
        main_layout.addWidget(self.tab_widget)
        # vts files
        self.vts_folder = None
        self.vts_prefix = None
        self.vts_file_list = []          # 排序后的完整路径列表
        self.current_file_index = -1     # 当前播放索引
        self.auto_update_timer = None    # QTimer 用于自动刷新
        self.auto_update_enabled = False
        self.sequential_timer = None      # 用于顺序播放的 QTimer
        self.is_sequential_playing = False
        # 3. 重构 UI 设置
        self.update_colormap_preview()

    def _create_vtk_and_tabs(self):
        # === VTK Render Window ===
        self.vtk_widget = QVTKRenderWindowInteractor()
        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(0.15, 0.15, 0.2)
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
        self.iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        self.iren.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())
        self.iren.Initialize()

        # === 替换原 VTK widget 添加逻辑 ===
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.vtk_widget, "3D View")
        # 创建 Plot Over Line Tab
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
        self.tab_widget.setCurrentIndex(0)  # 默认显示 3D
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

    def on_file_combo_changed(self, index):
        if index >= 0 and index < len(self.vts_file_list):
            self.current_file_index = index
            self.load_single_vts_file(self.vts_file_list[index])
            self.update_playback_status()

    def _update_playback_ui_enabled(self, enabled=True):
        """启用/禁用播放相关控件（不包括 Auto Update 复选框）"""
        self.file_combo.setEnabled(enabled)

    def _disable_interactive_controls(self, disable=True):
        """在自动更新模式下禁用用户交互控件"""
        widgets_to_disable = [
            self.field_combo,
            self.colormap_combo,
            self.auto_range_checkbox,
            self.min_spin,
            self.max_spin,
            self.glyph_checkbox,
            self.vis_mode_combo,
            self.clip_axis_combo,
            self.clip_slider,
            self.contour_levels_edit,
            self.plot_line_checkbox,
            self.show_axes_checkbox,
            self.show_bounds_checkbox,
            self.show_colorbar_checkbox,
        ]
        self._update_playback_ui_enabled(not disable)  # 注意逻辑取反
        for w in widgets_to_disable:
            w.setDisabled(disable)

    def toggle_auto_update(self, state):
        self.auto_update_enabled = (state == Qt.CheckState.Checked.value)
        if self.auto_update_enabled:
            self.start_auto_update()
        else:
            self.pause_auto_update()

    def start_auto_update(self):
        if not self.vts_folder or not self.vts_prefix:
            return
        if self.auto_update_timer is None:
            self.auto_update_timer = QTimer(self)
            self.auto_update_timer.timeout.connect(self.check_for_new_vts_files)
        self.auto_update_timer.start(500)  # 0.5 秒
        self._disable_interactive_controls(True)

    def pause_auto_update(self):
        if self.auto_update_timer:
            self.auto_update_timer.stop()
        self._disable_interactive_controls(False)

    def check_for_new_vts_files(self):
        """检查是否有更新的 .vts 文件"""
        if not self.vts_folder or not self.vts_prefix:
            return

        import glob
        pattern = os.path.join(self.vts_folder, f"{self.vts_prefix}*.vts")
        current_files = glob.glob(pattern)

        if not current_files:
            return

        # 找出最新修改的文件
        latest_file = max(current_files, key=os.path.getmtime)

        # 如果当前已加载的不是这个最新文件，则加载它
        current_loaded = self.vts_file_list[self.current_file_index] if self.vts_file_list else None
        if latest_file != current_loaded:
            # 更新文件列表（重新排序）
            def extract_number(f):
                base = os.path.basename(f)
                num_str = base[len(self.vts_prefix):].split('.')[0]
                try:
                    return int(''.join(filter(str.isdigit, num_str)))
                except:
                    return float('inf')
            current_files.sort(key=extract_number)
            self.vts_file_list = current_files
            try:
                new_index = current_files.index(latest_file)
                self.current_file_index = new_index
                self.load_single_vts_file(latest_file)
                self.update_playback_status()
            except ValueError:
                pass  # 不应发生

    def _create_control_panel(self):
        panel = QGroupBox("Data Controls")
        layout = QVBoxLayout()

        # === 加载按钮（始终显示）===
        self.load_btn = QPushButton("📂 Load .vts Folder")
        self.load_btn.clicked.connect(self.load_vts)
        layout.addWidget(self.load_btn)

        # Show with boundary checkbox
        self.show_with_boundary_checkbox = QCheckBox("Show with boundary")
        self.show_with_boundary_checkbox.setChecked(False)  # 默认取消勾选
        self.show_with_boundary_checkbox.stateChanged.connect(self.update_visualization)
        layout.addWidget(self.show_with_boundary_checkbox)

        # === 新的播放控制区域 ===
        playback_group = QGroupBox("Playback Control")
        playback_layout = QVBoxLayout()

        self.playback_status_label = QLabel("No data loaded")

        # Current: [下拉框]
        current_hbox = QHBoxLayout()
        current_hbox.addWidget(QLabel("Current:"))
        self.file_combo = QComboBox()
        self.file_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.file_combo.currentIndexChanged.connect(self.on_file_combo_changed)
        current_hbox.addWidget(self.file_combo)
        current_hbox.addStretch()
        playback_layout.addWidget(self.playback_status_label)
        playback_layout.addLayout(current_hbox)

        # 自动更新复选框
        self.auto_update_checkbox = QCheckBox("Auto Update (0.5s)")
        self.auto_update_checkbox.stateChanged.connect(self.toggle_auto_update)

        playback_layout.addWidget(self.auto_update_checkbox)
        playback_group.setLayout(playback_layout)

        # 保存引用
        self.playback_group = playback_group
        self.playback_group.setVisible(False)
        layout.addWidget(self.playback_group)

        layout.addWidget(QLabel("Field to Visualize:"))
        self.field_combo = QComboBox()
        self.field_combo.currentTextChanged.connect(self.on_field_selection_changed)
        layout.addWidget(self.field_combo)

        layout.addWidget(QLabel("Colormap:"))
        self.colormap_combo = QComboBox()
        self.colormap_combo.addItems([
            "Blue-Red (Cool-Warm)", "Rainbow", "Grayscale", "Viridis", "Plasma"
        ])
        self.colormap_combo.currentIndexChanged.connect(self.update_visualization)
        layout.addWidget(self.colormap_combo)

        self.auto_range_checkbox = QCheckBox("Auto Range")
        self.auto_range_checkbox.setChecked(True)
        self.auto_range_checkbox.toggled.connect(self.toggle_range_edit)
        layout.addWidget(self.auto_range_checkbox)

        range_hbox = QHBoxLayout()
        range_hbox.addWidget(QLabel("Min:"))
        self.min_spin = QDoubleSpinBox()
        self.min_spin.setRange(-1e6, 1e6)
        self.min_spin.setDecimals(4)
        self.min_spin.setEnabled(False)
        self.min_spin.valueChanged.connect(self.update_visualization)
        range_hbox.addWidget(self.min_spin)

        range_hbox.addWidget(QLabel("Max:"))
        self.max_spin = QDoubleSpinBox()
        self.max_spin.setRange(-1e6, 1e6)
        self.max_spin.setDecimals(4)
        self.max_spin.setEnabled(False)
        self.max_spin.valueChanged.connect(self.update_visualization)
        range_hbox.addWidget(self.max_spin)
        layout.addLayout(range_hbox)

        layout.addWidget(QLabel("Colormap Preview:"))
        self.colorbar_label = QLabel()
        self.colorbar_label.setFixedHeight(20)
        layout.addWidget(self.colorbar_label)

        self.glyph_checkbox = QCheckBox("Show Vector Arrows")
        self.glyph_checkbox.setChecked(False)
        self.glyph_checkbox.setEnabled(False)
        self.glyph_checkbox.stateChanged.connect(self.on_glyph_checkbox_changed)
        layout.addWidget(self.glyph_checkbox)

        self.arrow_color_btn = QPushButton("Set Arrow Color")
        self.arrow_color_btn.clicked.connect(self.pick_arrow_color)
        self.arrow_color_btn.setVisible(False)
        layout.addWidget(self.arrow_color_btn)

        self.color_arrows_by_mag_checkbox = QCheckBox("Color arrows by magnitude")
        self.color_arrows_by_mag_checkbox.setChecked(False)
        self.color_arrows_by_mag_checkbox.setVisible(False)
        self.color_arrows_by_mag_checkbox.stateChanged.connect(self.update_visualization)
        layout.addWidget(self.color_arrows_by_mag_checkbox)

        # === Visualization Mode ===
        layout.addWidget(QLabel("Visualization Mode:"))
        self.vis_mode_combo = QComboBox()
        self.vis_mode_combo.addItems(["Surface", "Clip", "Contour"])
        self.vis_mode_combo.currentTextChanged.connect(self.on_vis_mode_changed)
        layout.addWidget(self.vis_mode_combo)
        
        # Clip controls
        self.clip_group = QGroupBox("Clip Plane")
        clip_layout = QVBoxLayout()

        self.clip_axis_combo = QComboBox()
        self.clip_axis_combo.addItems(["X", "Y", "Z"])
        self.clip_axis_combo.currentTextChanged.connect(self.on_clip_axis_changed)
        clip_layout.addWidget(QLabel("Clip Axis:"))
        clip_layout.addWidget(self.clip_axis_combo)

        self.clip_slider = QDoubleSpinBox()
        self.clip_slider.setRange(-1e6, 1e6)
        self.clip_slider.setDecimals(4)
        self.clip_slider.setValue(0.0)
        self.clip_slider.valueChanged.connect(self.update_visualization)
        clip_layout.addWidget(QLabel("Clip Position:"))
        clip_layout.addWidget(self.clip_slider)
        self.clip_group.setLayout(clip_layout)
        self.clip_group.setVisible(False)
        layout.addWidget(self.clip_group)

        # Contour controls
        self.contour_group = QGroupBox("Contour (Isosurface)")
        contour_layout = QVBoxLayout()
        self.contour_levels_edit = QLineEdit()
        self.contour_levels_edit.setPlaceholderText("e.g., 0.5, 1.0, 1.5")
        self.contour_levels_edit.textChanged.connect(self.update_visualization)
        contour_layout.addWidget(QLabel("Levels (comma-separated):"))
        contour_layout.addWidget(self.contour_levels_edit)
        self.contour_group.setLayout(contour_layout)
        self.contour_group.setVisible(False)
        layout.addWidget(self.contour_group)

        # === Simplified Plot Over Line as Checkbox ===
        self.plot_line_checkbox = QCheckBox("📏 Plot Over Line")
        self.plot_line_checkbox.stateChanged.connect(self.toggle_plot_over_line)
        layout.addWidget(self.plot_line_checkbox)

        self.line_endpoint_group = QGroupBox("Line Manual")
        line_grid = QGridLayout()
        line_grid.setSpacing(6)  # 控件之间留点空隙
        line_grid.setContentsMargins(10, 10, 10, 10)  # 可选：内边距更美观

        # 创建 QLineEdit 并设置验证器
        self.p1x = QLineEdit(); self.p1y = QLineEdit(); self.p1z = QLineEdit()
        self.p2x = QLineEdit(); self.p2y = QLineEdit(); self.p2z = QLineEdit()
        coords = [self.p1x, self.p1y, self.p1z, self.p2x, self.p2y, self.p2z]
        for w in coords:
            w.setValidator(QDoubleValidator())
            w.setEnabled(False)
            # 可选：让 QLineEdit 在垂直方向也居中/填满
            # w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # 辅助：右对齐标签（需 from PyQt5.QtCore import Qt）
        def right_label(text):
            label = QLabel(text)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return label

        # P1 列
        line_grid.addWidget(right_label("P1 X:"), 0, 0)
        line_grid.addWidget(self.p1x, 0, 1)
        line_grid.addWidget(right_label("P1 Y:"), 1, 0)
        line_grid.addWidget(self.p1y, 1, 1)
        line_grid.addWidget(right_label("P1 Z:"), 2, 0)
        line_grid.addWidget(self.p1z, 2, 1)

        # P2 列
        line_grid.addWidget(right_label("P2 X:"), 0, 2)
        line_grid.addWidget(self.p2x, 0, 3)
        line_grid.addWidget(right_label("P2 Y:"), 1, 2)
        line_grid.addWidget(self.p2y, 1, 3)
        line_grid.addWidget(right_label("P2 Z:"), 2, 2)
        line_grid.addWidget(self.p2z, 2, 3)

        # 设置列行为：标签列窄，输入列可伸展
        line_grid.setColumnMinimumWidth(0, 45)
        line_grid.setColumnMinimumWidth(2, 45)
        line_grid.setColumnStretch(1, 1)
        line_grid.setColumnStretch(3, 1)

        # === 按钮区域：并排放置 ===
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)

        set_line_btn = QPushButton("Get Data")
        set_line_btn.clicked.connect(self.set_line_from_inputs)
        set_line_btn.setEnabled(False)
        button_layout.addWidget(set_line_btn)

        export_excel_btn = QPushButton("📤 Export Excel")
        export_excel_btn.clicked.connect(self.export_line_data)
        button_layout.addWidget(export_excel_btn)

        # 将按钮容器加入网格（第3行，跨全部4列）
        button_container = QWidget()
        button_container.setLayout(button_layout)
        line_grid.addWidget(button_container, 3, 0, 1, 4)

        # 应用布局
        self.line_endpoint_group.setLayout(line_grid)
        self.line_endpoint_group.setVisible(False)
        layout.addWidget(self.line_endpoint_group)

        # Single line style controls
        self.line_style_group = self._create_line_style_group()
        layout.addWidget(self.line_style_group)

        layout.addStretch()

        # === Visualization Enhancements ===
        layout.addWidget(QLabel("Display Options:"))

        self.show_axes_checkbox = QCheckBox("Show XYZ Axes")
        self.show_axes_checkbox.setChecked(False)
        self.show_axes_checkbox.stateChanged.connect(self.update_visualization)
        layout.addWidget(self.show_axes_checkbox)

        self.show_bounds_checkbox = QCheckBox("Show Domain Bounds")
        self.show_bounds_checkbox.setChecked(False)
        self.show_bounds_checkbox.stateChanged.connect(self.update_visualization)
        layout.addWidget(self.show_bounds_checkbox)

        self.show_colorbar_checkbox = QCheckBox("Show Color Bar")
        self.show_colorbar_checkbox.setChecked(False)
        self.show_colorbar_checkbox.stateChanged.connect(self.update_visualization)
        layout.addWidget(self.show_colorbar_checkbox)

        # View reset buttons
        view_hbox = QHBoxLayout()
        for axis in ["X", "Y", "Z"]:
            btn = QPushButton(f"View {axis}")
            btn.clicked.connect(lambda _, a=axis: self.reset_view(a))
            view_hbox.addWidget(btn)
        layout.addLayout(view_hbox)

        # Save screenshot
        self.save_btn = QPushButton("💾 Save Screenshot")
        self.save_btn.clicked.connect(self.save_screenshot)
        layout.addWidget(self.save_btn)

        panel.setLayout(layout)
        # 🔑 关键：限制 panel 的最大宽度，防止内部控件撑宽
        panel.setMaximumWidth(self.control_panel_width - 10)  # 略小于 scroll_area 的固定宽度 control_panel_width
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
         # === 包装进 QScrollArea ===
        scroll_area = QScrollArea()
        scroll_area.setWidget(panel)
        scroll_area.setWidgetResizable(True)  # 关键：让内部 widget 自适应大小
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)  # 可选：去掉边框更美观
        # 🔑 禁用水平滚动条（只保留垂直）
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        return scroll_area

    def _create_line_style_group(self):
        group = QGroupBox("Line Style")
        self.line_style_layout = QVBoxLayout()
        group.setLayout(self.line_style_layout)
        self.line_style_group = group
        group.setVisible(False)  # 初始隐藏
        return group

    def _rebuild_line_style_controls(self):
        # 清空旧控件
        while self.line_style_layout.count():
            child = self.line_style_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if self.active_line_data is None:
            return

        fields = [col for col in self.active_line_data.columns if col != 'arc_length' and col != 'vtkValidPointMask']
        for field in list(self._line_styles.keys()):
            if field not in fields:
                del self._line_styles[field]
        for i, field in enumerate(fields):
            if field not in list(self._line_styles.keys()):
                color = self.DEFAULT_COLOR_CYCLE[i % len(self.DEFAULT_COLOR_CYCLE)]
                self._line_styles[field] = {
                    'visible': True,
                    'color': color,  # default blue
                    'linestyle': '-'
                }

            hbox = QHBoxLayout()
            visible_cb = QCheckBox(field)
            visible_cb.setChecked(self._line_styles[field]['visible'])
            visible_cb.stateChanged.connect(lambda state, f=field: self._on_line_visible_changed(f, state))

            color_btn = QPushButton("Color")
            color_btn.clicked.connect(lambda _, f=field: self._pick_field_color(f))

            linestyle_combo = QComboBox()
            linestyle_combo.addItems(["-", "--", "-.", ":"])
            linestyle_combo.setCurrentText(self._line_styles[field]['linestyle'])
            linestyle_combo.currentTextChanged.connect(lambda style, f=field: self._on_linestyle_changed(f, style))

            visible_cb.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            hbox.addWidget(visible_cb)
            color_btn.setFixedWidth(int((self.control_panel_width - 10) / 6))
            hbox.addWidget(color_btn)
            linestyle_combo.setFixedWidth(int((self.control_panel_width - 10) / 6))
            hbox.addWidget(linestyle_combo)

            widget = QWidget()
            widget.setLayout(hbox)
            self.line_style_layout.addWidget(widget)

    def _on_line_visible_changed(self, field, state):
        self._line_styles[field]['visible'] = (state == Qt.CheckState.Checked.value)
        self.update_plot_and_table()

    def _on_linestyle_changed(self, field, style):
        self._line_styles[field]['linestyle'] = style
        self.update_plot_and_table()

    def _pick_field_color(self, field):
        current = self._line_styles[field]['color']
        qcolor = QColor.fromRgbF(*current)
        new_color = QColorDialog.getColor(qcolor, self, f"Color for {field}")
        if new_color.isValid():
            rgb = (new_color.redF(), new_color.greenF(), new_color.blueF())
            self._line_styles[field]['color'] = rgb
            self.update_plot_and_table()

    def update_plot_and_table(self):
        if self.active_line_data is None:
            return

        # 更新表格（不 stretch）
        model = PandasModel(self.active_line_data)
        self.line_table_view.setModel(model)
        header = self.line_table_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)

        # 重建样式控件（仅当字段变化时才需，可加缓存判断）
        self._rebuild_line_style_controls()

        # 绘图
        self.plot_figure.clear()
        ax = self.plot_figure.add_subplot(111)
        x = self.active_line_data['arc_length']

        for col in self.active_line_data.columns:
            if col == 'arc_length' or col == 'vtkValidPointMask':
                continue
            style = self._line_styles.get(col, {
                'visible': True,
                'color': (0, 0, 1),
                'linestyle': '-'
            })
            if style['visible']:
                ax.plot(x, self.active_line_data[col],
                        color=style['color'],
                        linestyle=style['linestyle'],
                        label=col)

        # === X 轴刻度 ===
        x_min, x_max = x.min(), x.max()
        if x_max > x_min:
            x_ticks = np.linspace(x_min, x_max, num=8)
            ax.set_xticks(x_ticks)
        else:
            ax.set_xticks([x_min])

        # === Y 轴刻度 ===
        numeric_data = self.active_line_data.select_dtypes(include=[np.number])
        y_cols = [col for col in numeric_data.columns if col != 'arc_length' and col != 'vtkValidPointMask']
        if y_cols:
            y_vals = numeric_data[y_cols]
            y_min, y_max = y_vals.min().min(), y_vals.max().max()
            y_range = y_max - y_min
            margin = y_range * 0.05 if y_range > 0 else abs(y_min) * 0.1 or 0.1
            y_ticks = np.linspace(y_min - margin, y_max + margin, num=8)
            ax.set_yticks(y_ticks)
        else:
            ax.set_yticks([])

        ax.set_xlabel("Arc Length")
        ax.set_ylabel("Value")
        ax.grid(True)
        ax.legend(fontsize=8)
        self.plot_canvas.draw()

    def on_vis_mode_changed(self, mode):
        self.current_vis_mode = mode
        is_vector = self.field_combo.currentText().startswith("[V]")
        # Only scalar fields support contour/slice/clip coloring
        if mode in ["Contour", "Clip"] and is_vector:
            # Force switch to magnitude for these modes
            pass  # Handled in update_visualization via mag_arr

        self.clip_group.setVisible(mode == "Clip")
        self.contour_group.setVisible(mode == "Contour")
        self.update_visualization()

    def toggle_plot_over_line(self, state):
        checked = (state == Qt.CheckState.Checked.value)
        if not self.current_data:
            self.plot_line_checkbox.setChecked(False)
            return
        self.tab_widget.setTabEnabled(1, checked)  # 🔑 禁用/启用 tab
        if checked:
            self.start_plot_over_line()
            self.line_endpoint_group.setVisible(True)
            self.line_style_group.setVisible(True)  # 🔑 显示样式组
            for w in [self.p1x, self.p1y, self.p1z, self.p2x, self.p2y, self.p2z]:
                w.setEnabled(True)
            self.line_endpoint_group.findChild(QPushButton).setEnabled(True)
            self.tab_widget.setCurrentIndex(1)
            # 初始化样式
            # self.line_visible_checkbox.setChecked(True)
        else:
            self.end_plot_over_line()
            self.line_endpoint_group.setVisible(False)
            self.line_style_group.setVisible(False)  # 🔑 隐藏
            self.tab_widget.setCurrentIndex(0)
    
    def start_plot_over_line(self):
        self.end_plot_over_line()  # 清理旧的 widget，但 NOT the endpoint variables

        self.line_widget = vtk.vtkLineWidget()
        self.line_widget.SetInteractor(self.iren)

        # Use saved endpoints if available, otherwise use default bounds diagonal
        if self.plot_line_p1 is not None and self.plot_line_p2 is not None:
            p1 = self.plot_line_p1
            p2 = self.plot_line_p2
        else:
            bounds = self.current_data.GetBounds()
            p1 = [bounds[0], bounds[2], bounds[4]]
            p2 = [bounds[1], bounds[3], bounds[5]]
            # Save these as initial defaults
            self.plot_line_p1 = list(p1)
            self.plot_line_p2 = list(p2)

        self.line_widget.SetPoint1(p1)
        self.line_widget.SetPoint2(p2)
        self.line_widget.SetResolution(100)
        self.line_end_observer_tag = self.line_widget.AddObserver("EndInteractionEvent", self.on_line_changed)
        self.line_widget.On()
        self._update_line_input_fields(p1, p2)

    def _update_line_input_fields(self, p1, p2):
        self.plot_line_p1 = list(p1)
        self.plot_line_p2 = list(p2)
        self.p1x.setText(f"{p1[0]:.4f}")
        self.p1y.setText(f"{p1[1]:.4f}")
        self.p1z.setText(f"{p1[2]:.4f}")
        self.p2x.setText(f"{p2[0]:.4f}")
        self.p2y.setText(f"{p2[1]:.4f}")
        self.p2z.setText(f"{p2[2]:.4f}")

    def set_line_from_inputs(self):
        try:
            p1 = [float(self.p1x.text()), float(self.p1y.text()), float(self.p1z.text())]
            p2 = [float(self.p2x.text()), float(self.p2y.text()), float(self.p2z.text())]
        except ValueError:
            return

        if self.line_widget:
            # ✅ 直接设置端点（vtkLineWidget 的 API）
            self.line_widget.SetPoint1(p1)
            self.line_widget.SetPoint2(p2)
            self.line_widget.On()  # 确保可见
            self.on_line_changed(None, None)  # 触发重新采样
            self._update_line_input_fields(p1, p2)  # 同步输入框（可选）

    def on_line_changed(self, obj, event):
        if not self.current_data or not self.line_widget:
            return

        p1 = self.line_widget.GetPoint1()
        p2 = self.line_widget.GetPoint2()
        self._update_line_input_fields(p1, p2)

        line_source = vtk.vtkLineSource()
        line_source.SetPoint1(p1)
        line_source.SetPoint2(p2)
        line_source.SetResolution(100)
        line_source.Update()

        probe = vtk.vtkProbeFilter()
        probe.SetInputConnection(line_source.GetOutputPort())
        probe.SetSourceData(self.current_data)
        probe.Update()

        poly = probe.GetOutput()
        point_data = poly.GetPointData()
        n_pts = poly.GetNumberOfPoints()

        arc_len = [0.0]
        total = 0.0
        for i in range(1, n_pts):
            a = np.array(poly.GetPoint(i-1))
            b = np.array(poly.GetPoint(i))
            total += np.linalg.norm(b - a)
            arc_len.append(total)

        data_dict = {"arc_length": arc_len}
        for i in range(point_data.GetNumberOfArrays()):
            arr = point_data.GetArray(i)
            name = arr.GetName() or f"Array_{i}"
            comps = arr.GetNumberOfComponents()
            if comps == 1:
                data_dict[name] = [arr.GetValue(j) for j in range(n_pts)]
            elif comps == 3:
                vx = [arr.GetComponent(j,0) for j in range(n_pts)]
                vy = [arr.GetComponent(j,1) for j in range(n_pts)]
                vz = [arr.GetComponent(j,2) for j in range(n_pts)]
                mag = [math.sqrt(vx[j]**2 + vy[j]**2 + vz[j]**2) for j in range(n_pts)]
                data_dict[f"{name}_X"] = vx
                data_dict[f"{name}_Y"] = vy
                data_dict[f"{name}_Z"] = vz
                data_dict[f"{name}_Magnitude"] = mag

        self.active_line_data = pd.DataFrame(data_dict)
        self.update_plot_and_table()

    def export_line_data(self):
        if self.active_line_data is None:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Line Data", "", "Excel Files (*.xlsx);;All Files (*)"
        )
        if not path:
            return
        if not path.endswith(".xlsx"):
            path += ".xlsx"

        df = self.active_line_data.copy()
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].apply(clean_excel_string)
        df = df.fillna('')

        df.to_excel(path, index=False)
        self.playback_status_label.setText(f"✅ Exported to {os.path.basename(path)}")

    def end_plot_over_line(self):
        if hasattr(self, 'line_end_observer_tag'):
            self.line_widget.Off()
            self.line_widget.RemoveObserver(self.line_end_observer_tag)
            self.line_widget = None
            del self.line_end_observer_tag
        self.active_line_data = None
        self.plot_figure.clear()
        self.plot_canvas.draw()
        self.line_table_view.setModel(None)

    def on_clip_axis_changed(self, axis):
        if not self.current_data:
            return
        bounds = self.current_data.GetBounds()
        if axis == "X":
            rmin, rmax = bounds[0], bounds[1]
        elif axis == "Y":
            rmin, rmax = bounds[2], bounds[3]
        else:  # Z
            rmin, rmax = bounds[4], bounds[5]
        self.clip_slider.setRange(rmin, rmax)
        self.clip_slider.setValue((rmin + rmax) / 2.0)
        self.update_visualization()

    def reset_view(self, axis):
        if not self.current_data:
            return
        camera = self.renderer.GetActiveCamera()
        bounds = self.current_data.GetBounds()
        center = [(bounds[0]+bounds[1])/2, (bounds[2]+bounds[3])/2, (bounds[4]+bounds[5])/2]
        dist = max(bounds[1]-bounds[0], bounds[3]-bounds[2], bounds[5]-bounds[4]) * 3

        if axis == "X":
            camera.SetPosition(center[0] + dist, center[1], center[2])
            camera.SetFocalPoint(*center)
            camera.SetViewUp(0, 0, 1)
        elif axis == "Y":
            camera.SetPosition(center[0], center[1] + dist, center[2])
            camera.SetFocalPoint(*center)
            camera.SetViewUp(0, 0, 1)
        elif axis == "Z":
            camera.SetPosition(center[0], center[1], center[2] + dist)
            camera.SetFocalPoint(*center)
            camera.SetViewUp(0, 1, 0)

        self.renderer.ResetCameraClippingRange()
        self.vtk_widget.GetRenderWindow().Render()

    def _update_arrow_controls_visibility(self):
        is_vector = self.field_combo.currentText().startswith("[V]")
        show_glyph = self.glyph_checkbox.isChecked() and is_vector
        self.arrow_color_btn.setVisible(show_glyph)
        self.color_arrows_by_mag_checkbox.setVisible(show_glyph)
        if not show_glyph:
            self.color_arrows_by_mag_checkbox.setChecked(False)

    def on_glyph_checkbox_changed(self, state):
        is_checked = (state == Qt.CheckState.Checked.value)
        is_vector = self.field_combo.currentText().startswith("[V]")
        if not is_vector:
            self.glyph_checkbox.setChecked(False)
            return
        self._update_arrow_controls_visibility()
        self.update_visualization()

    def toggle_range_edit(self, checked):
        enabled = not checked
        self.min_spin.setEnabled(enabled)
        self.max_spin.setEnabled(enabled)
        self.update_visualization()

    def pick_arrow_color(self):
        color = QColorDialog.getColor(
            QColor.fromRgbF(*self.arrow_color),
            self,
            "Select Arrow Color"
        )
        if color.isValid():
            self.arrow_color = (color.redF(), color.greenF(), color.blueF())
            self.update_visualization()

    def load_vts(self):
        """用户点击按钮：选择文件夹 + 输入前缀"""
        folder = QFileDialog.getExistingDirectory(self, "Select VTS Output Folder")
        if not folder:
            return
        prefix, ok = QInputDialog.getText(
            self,
            "VTS File Prefix",
            "Enter common filename prefix (e.g., MeshData_step):",
            text="MeshData_step"
        )
        if not ok or not prefix.strip():
            return
        self.load_vts_from_folder(folder, prefix.strip())

    def _update_file_combo(self):
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        self.file_combo.addItems([os.path.basename(f) for f in self.vts_file_list])
        if 0 <= self.current_file_index < len(self.vts_file_list):
            self.file_combo.setCurrentIndex(self.current_file_index)
        self.file_combo.blockSignals(False)

    def load_vts_from_folder(self, folder, prefix):
        import glob, os
        pattern = os.path.join(folder, f"{prefix}*.vts")
        files = glob.glob(pattern)
        def extract_number(f):
            base = os.path.basename(f)
            num_str = base[len(prefix):].split('.')[0]
            return int(''.join(filter(str.isdigit, num_str))) if any(c.isdigit() for c in num_str) else float('inf')
        files.sort(key=extract_number)
        if not files:
            QMessageBox.warning(self, "No Files", "No matching .vts files found.")
            return
        self.vts_folder = folder
        self.vts_prefix = prefix
        self.vts_file_list = files
        self.current_file_index = 0
        # 加载第一个文件
        try:
            self.load_single_vts_file(files[0])
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load file:\n{str(e)}")
            return
        # ✅ 关键：显示 playback 控制区域
        self.playback_group.setVisible(True)
        self._update_file_combo()
        self._update_playback_ui_enabled(True)

    def _enable_playback_controls(self, enable=True):
        """显示或隐藏播放控制面板"""
        if hasattr(self, 'playback_group'):
            self.playback_group.setVisible(enable)
        else:
            # 安全兜底：如果 UI 尚未创建，可延迟或报错（正常流程不应发生）
            print("Warning: playback_group not initialized yet.")

    def load_single_vts_file(self, file_path):
        try:
            reader = vtk.vtkXMLStructuredGridReader()
            reader.SetFileName(file_path)
            reader.Update()
            output = reader.GetOutput()
            if not output or output.GetNumberOfPoints() == 0:
                self.playback_status_label.setText("❌ Empty dataset")
                self.current_data = None
                return
            self.current_data = output
            self.populate_field_combos()
            self.playback_status_label.setText(f"✅ Loaded: {os.path.basename(file_path)}")
            self.update_visualization()
        except Exception as e:
            self.playback_status_label.setText(f"❌ Error: {str(e)}")
            self.current_data = None
        # Initialize clip slider range
        if self.current_vis_mode == "Clip":
            self.on_clip_axis_changed(self.clip_axis_combo.currentText())
        self.playback_group.setVisible(True)
        # 启用字段选择等控件
        self.field_combo.setEnabled(True)
        self.colormap_combo.setEnabled(True)

    def update_playback_status(self):
        if self.vts_file_list and 0 <= self.current_file_index < len(self.vts_file_list):
            fname = os.path.basename(self.vts_file_list[self.current_file_index])
            self.playback_status_label.setText("✅ Loaded")
            # 下拉框已在 _update_file_combo 中同步，此处可不再设置
        else:
            self.playback_status_label.setText("⚠️ No file")

    def compute_magnitude_array(self, vector_array_name, grid=None):
        if grid is None:
            grid = self.current_data
        if not grid:
            return None
        vectors = grid.GetPointData().GetArray(vector_array_name)
        if not vectors or vectors.GetNumberOfComponents() != 3:
            return None
        n_points = vectors.GetNumberOfTuples()
        magnitude = vtk.vtkFloatArray()
        magnitude.SetName(f"{vector_array_name}_magnitude")
        magnitude.SetNumberOfValues(n_points)
        for i in range(n_points):
            vx, vy, vz = vectors.GetTuple3(i)
            mag = math.sqrt(vx*vx + vy*vy + vz*vz)
            magnitude.SetValue(i, mag)
        return magnitude

    def populate_field_combos(self):
        self.field_combo.clear()
        if not self.current_data:
            return
        point_data = self.current_data.GetPointData()
        fields = []
        for i in range(point_data.GetNumberOfArrays()):
            arr = point_data.GetArray(i)
            name = arr.GetName()
            if not name:
                continue
            comps = arr.GetNumberOfComponents()
            if comps == 1:
                fields.append((f"[S] {name}", name, 'scalar'))
            elif comps == 3:
                fields.append((f"[V] {name}", name, 'vector'))
        fields.sort(key=lambda x: (x[2] != 'scalar', x[1]))
        for display_name, _, _ in fields:
            self.field_combo.addItem(display_name)
        if fields:
            self.field_combo.setCurrentIndex(0)
            self.update_range_inputs()
        else:
            self.field_combo.addItem("(No fields)")
            self.glyph_checkbox.setEnabled(False)

    def update_range_inputs(self):
        display_text = self.field_combo.currentText()
        if "(No fields)" in display_text or not self.current_data:
            return
        field_name = display_text[4:]
        if display_text.startswith("[S]"):
            array = self.current_data.GetPointData().GetArray(field_name)
        else:
            array = self.compute_magnitude_array(field_name)
        if array:
            rmin, rmax = array.GetRange()
            self.min_spin.blockSignals(True)
            self.max_spin.blockSignals(True)
            self.min_spin.setValue(rmin)
            self.max_spin.setValue(rmax)
            self.min_spin.blockSignals(False)
            self.max_spin.blockSignals(False)

    def on_field_selection_changed(self, display_text):
        is_vector = display_text.startswith("[V]")
        if not is_vector:
            self.glyph_checkbox.setChecked(False)
        self.glyph_checkbox.setEnabled(is_vector)
        self._update_arrow_controls_visibility()
        self.auto_range_checkbox.setChecked(True)
        self.update_range_inputs()
        self.update_visualization()

    def _create_lookup_table(self, colormap_name, table_range):
        lut = vtk.vtkLookupTable()
        if colormap_name == "Blue-Red (Cool-Warm)":
            lut.SetHueRange(0.667, 0.0)
        elif colormap_name == "Rainbow":
            lut.SetHueRange(0.0, 0.667)
        elif colormap_name == "Grayscale":
            lut.SetHueRange(0, 0)
            lut.SetSaturationRange(0, 0)
            lut.SetValueRange(0, 1)
        elif colormap_name == "Viridis":
            self._setup_viridis_lut(lut)
        elif colormap_name == "Plasma":
            self._setup_plasma_lut(lut)
        lut.SetTableRange(*table_range)
        lut.Build()
        return lut

    def _setup_viridis_lut(self, lut):
        lut.SetNumberOfColors(256)
        lut.Build()
        viridis_colors = [
            (0.267, 0.005, 0.329), (0.282, 0.140, 0.450), (0.251, 0.280, 0.528),
            (0.200, 0.410, 0.538), (0.151, 0.520, 0.520), (0.122, 0.610, 0.470),
            (0.208, 0.690, 0.388), (0.380, 0.750, 0.280), (0.600, 0.800, 0.150),
            (0.993, 0.906, 0.145)
        ]
        for i in range(256):
            t = i / 255.0
            idx = min(int(t * (len(viridis_colors) - 1)), len(viridis_colors) - 2)
            a = viridis_colors[idx]
            b = viridis_colors[idx + 1]
            f = (t * (len(viridis_colors) - 1)) - idx
            r = a[0] + f * (b[0] - a[0])
            g = a[1] + f * (b[1] - a[1])
            b_ = a[2] + f * (b[2] - a[2])
            lut.SetTableValue(i, r, g, b_, 1.0)

    def _setup_plasma_lut(self, lut):
        lut.SetNumberOfColors(256)
        lut.Build()
        plasma_colors = [
            (0.050, 0.030, 0.500), (0.150, 0.080, 0.600), (0.300, 0.120, 0.650),
            (0.500, 0.200, 0.600), (0.700, 0.300, 0.500), (0.850, 0.450, 0.350),
            (0.950, 0.700, 0.200), (0.990, 0.900, 0.150)
        ]
        for i in range(256):
            t = i / 255.0
            idx = min(int(t * (len(plasma_colors) - 1)), len(plasma_colors) - 2)
            a = plasma_colors[idx]
            b = plasma_colors[idx + 1]
            f = (t * (len(plasma_colors) - 1)) - idx
            r = a[0] + f * (b[0] - a[0])
            g = a[1] + f * (b[1] - a[1])
            b_ = a[2] + f * (b[2] - a[2])
            lut.SetTableValue(i, r, g, b_, 1.0)

    def update_colormap_preview(self):
        pixmap = QPixmap(200, 20)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        lut = self._create_lookup_table(self.colormap_combo.currentText(), (0.0, 1.0))
        width = pixmap.width()
        for i in range(width):
            t = i / max(1, width - 1)
            rgb = [0.0, 0.0, 0.0]
            lut.GetColor(t, rgb)
            color = QColor.fromRgbF(*rgb)
            painter.fillRect(i, 0, 1, 20, color)
        painter.end()
        self.colorbar_label.setPixmap(pixmap)

    def update_visualization(self):
        self.renderer.RemoveAllViewProps()
        if not self.current_data:
            return
        # === 新增：根据 "Show with boundary" 决定是否裁剪 ===
        grid_to_render = self.current_data

        if not self.show_with_boundary_checkbox.isChecked():
            # 需要去掉最外层（边界层）
            dims = [0, 0, 0]
            self.current_data.GetDimensions(dims)  # [nx, ny, nz]
            nx, ny, nz = dims[0], dims[1], dims[2]

            # 安全检查：至少要有 3 层才能裁剪（0,1,2 → 保留 1）
            if nx >= 3 and ny >= 3 and nz >= 3:
                extract = vtk.vtkExtractGrid()
                extract.SetInputData(self.current_data)
                # VOI: (imin, imax, jmin, jmax, kmin, kmax) —— inclusive
                extract.SetVOI(1, nx - 2, 1, ny - 2, 1, nz - 2)
                extract.Update()
                grid_to_render = extract.GetOutput()
            # else: 无法裁剪，保持原网格（如 2x2x2 网格）
        
        # === 后续使用 grid_to_render 进行可视化 ===
        display_text = self.field_combo.currentText()
        if "(No fields)" in display_text:
            return

        is_vector = display_text.startswith("[V]")
        field_name = display_text[4:]

        # Always compute magnitude if needed
        mag_arr = None
        scalar_arr = None
        if is_vector:
            mag_arr = self.compute_magnitude_array(field_name, grid_to_render)
            if not mag_arr:
                return
            scalar_arr = mag_arr
            scalar_name = mag_arr.GetName()
        else:
            scalar_arr = grid_to_render.GetPointData().GetArray(field_name)
            scalar_name = field_name
        if not scalar_arr:
            return

        # Update range
        if self.auto_range_checkbox.isChecked():
            rmin, rmax = scalar_arr.GetRange()
            self.min_spin.blockSignals(True)
            self.max_spin.blockSignals(True)
            self.min_spin.setValue(rmin)
            self.max_spin.setValue(rmax)
            self.min_spin.blockSignals(False)
            self.max_spin.blockSignals(False)
        else:
            rmin = self.min_spin.value()
            rmax = self.max_spin.value()
            if rmin >= rmax:
                rmin, rmax = scalar_arr.GetRange()

        lut = self._create_lookup_table(self.colormap_combo.currentText(), (rmin, rmax))

        # Prepare data with scalar active
        grid = vtk.vtkStructuredGrid()
        grid.DeepCopy(grid_to_render)
        if is_vector:
            if mag_arr:
                grid.GetPointData().AddArray(mag_arr)
            grid.GetPointData().SetActiveScalars(scalar_name)
            grid.GetPointData().SetActiveVectors(field_name)
        else:
            grid.GetPointData().SetActiveScalars(scalar_name)

        mode = self.current_vis_mode

        if mode == "Surface":
            self._render_surface_actor(grid, scalar_name, lut)
        elif mode == "Clip":
            self._render_clip_actor(grid, scalar_name, lut)
        elif mode == "Contour":
            self._render_contour_actor(grid, scalar_name, lut)

        # === Add optional visual aids ===
        if hasattr(self, 'orientation_marker'):
            self.orientation_marker.Off()
            del self.orientation_marker

        if self.show_axes_checkbox.isChecked():
            axes = vtk.vtkAxesActor()
            axes.SetTotalLength(1.0, 1.0, 1.0)
            axes.SetShaftTypeToCylinder()
            axes.SetCylinderRadius(0.02)
            axes.SetAxisLabels(True)

            widget = vtk.vtkOrientationMarkerWidget()
            widget.SetOutlineColor(0.93, 0.57, 0.13)
            widget.SetOrientationMarker(axes)
            widget.SetInteractor(self.iren)
            widget.SetViewport(0.0, 0.0, 0.2, 0.2)  # 左下角小窗口
            widget.EnabledOn()
            widget.InteractiveOff()
            self.orientation_marker = widget  # Keep alive

        if hasattr(self, '_cube_axes_actor'):
            self.renderer.RemoveActor(self._cube_axes_actor)
            del self._cube_axes_actor

        if self.show_bounds_checkbox.isChecked() and grid_to_render:
            bounds = grid.GetBounds()
            cube_axes = vtk.vtkCubeAxesActor()
            cube_axes.SetBounds(bounds)
            cube_axes.SetCamera(self.renderer.GetActiveCamera())

            # 设置刻度样式
            cube_axes.SetXLabelFormat("%.2g")
            cube_axes.SetYLabelFormat("%.2g")
            cube_axes.SetZLabelFormat("%.2g")
            cube_axes.SetFlyModeToOuterEdges()  # 刻度在外边
            cube_axes.SetTickLocationToInside()
            # cube_axes.SetGridLineLocationToAll()
            # cube_axes.DrawGridOn()  # 显示网格线（可选）
            cube_axes.XAxisMinorTickVisibilityOff()
            cube_axes.YAxisMinorTickVisibilityOff()
            cube_axes.ZAxisMinorTickVisibilityOff()

            # 颜色和字体
            # cube_axes.GetTitleTextProperty(vtk.vtkCubeAxesActor.).SetColor(1, 1, 1)
            # cube_axes.GetLabelTextProperty().SetColor(1, 1, 1)
            # cube_axes.GetProperty().SetColor(1, 1, 1)

            self.renderer.AddActor(cube_axes)
            self._cube_axes_actor = cube_axes  # Keep reference

        if self.show_colorbar_checkbox.isChecked():
            scalar_bar = vtk.vtkScalarBarActor()
            scalar_bar.SetLookupTable(lut)
            scalar_bar.SetTitle(scalar_name)
            scalar_bar.SetNumberOfLabels(5)
            scalar_bar.SetLabelFormat("%.3g")

            # 🔑 关键：设置为水平方向
            scalar_bar.SetOrientationToHorizontal()

            # 位置：通常放在底部或顶部（归一化坐标）
            scalar_bar.SetPosition(0.2, 0.02)   # x=30%, y=2%（靠近底部）

            # 尺寸：宽而矮
            scalar_bar.SetWidth(0.5)            # 宽度占窗口 40%
            scalar_bar.SetHeight(0.05)          # 高度约 8%

            # 标题文本属性
            title_prop = scalar_bar.GetTitleTextProperty()
            title_prop.SetFontFamilyToArial()
            title_prop.SetFontSize(14)
            title_prop.SetColor(1, 1, 1)
            title_prop.SetBold(0)
            title_prop.SetItalic(0)

            # 标签文本属性
            label_prop = scalar_bar.GetLabelTextProperty()
            label_prop.SetFontFamilyToArial()
            label_prop.SetFontSize(10)
            label_prop.SetColor(1, 1, 1)
            label_prop.SetBold(0)
            label_prop.SetItalic(0)

            self.renderer.AddActor2D(scalar_bar)

        self.renderer.ResetCamera()
        self.vtk_widget.GetRenderWindow().Render()
        self.update_colormap_preview()

    def _render_surface_actor(self, grid, scalar_name, lut):
        mapper = vtk.vtkDataSetMapper()
        mapper.SetInputData(grid)
        mapper.SetScalarModeToUsePointFieldData()
        mapper.SelectColorArray(scalar_name)
        mapper.SetLookupTable(lut)
        mapper.UseLookupTableScalarRangeOn()
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        self.renderer.AddActor(actor)

    def _render_clip_actor(self, grid, scalar_name, lut):
        plane = vtk.vtkPlane()
        bounds = grid.GetBounds()
        pos = self.clip_slider.value()
        axis = self.clip_axis_combo.currentText()

        if axis == "X":
            center = [pos, (bounds[2]+bounds[3])/2, (bounds[4]+bounds[5])/2]
            normal = (1, 0, 0)
        elif axis == "Y":
            center = [(bounds[0]+bounds[1])/2, pos, (bounds[4]+bounds[5])/2]
            normal = (0, 1, 0)
        else:  # Z
            center = [(bounds[0]+bounds[1])/2, (bounds[2]+bounds[3])/2, pos]
            normal = (0, 0, 1)

        plane.SetOrigin(*center)
        plane.SetNormal(*normal)

        clipper = vtk.vtkClipDataSet()
        clipper.SetInputData(grid)
        clipper.SetClipFunction(plane)
        clipper.GenerateClipScalarsOff()
        clipper.GenerateClippedOutputOff()
        clipper.Update()

        mapper = vtk.vtkDataSetMapper()
        mapper.SetInputConnection(clipper.GetOutputPort())
        mapper.SetScalarModeToUsePointFieldData()
        mapper.SelectColorArray(scalar_name)
        mapper.SetLookupTable(lut)
        mapper.UseLookupTableScalarRangeOn()

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        self.renderer.AddActor(actor)

    def _render_contour_actor(self, grid, scalar_name, lut):
        text = self.contour_levels_edit.text().strip()
        if not text:
            return

        try:
            levels = [float(x.strip()) for x in text.split(",") if x.strip()]
        except ValueError:
            return

        if not levels:
            return

        contour = vtk.vtkContourFilter()
        contour.SetInputData(grid)
        contour.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, scalar_name)
        for i, level in enumerate(levels):
            contour.SetValue(i, level)
        contour.Update()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(contour.GetOutputPort())
        mapper.SetScalarModeToUsePointFieldData()
        mapper.SelectColorArray(scalar_name)
        mapper.SetLookupTable(lut)
        mapper.UseLookupTableScalarRangeOn()

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        self.renderer.AddActor(actor)

    def save_screenshot(self):
        # 定义支持的格式
        file_filter = (
            "PNG Files (*.png);;"
            "JPEG Files (*.jpg *.jpeg);;"
            "TIFF Files (*.tiff *.tif);;"
            "BMP Files (*.bmp);;"
            "All Files (*)"
        )
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save Screenshot", "", file_filter
        )
        if not file_path:
            return  # 用户取消

        # 自动补全扩展名（如果缺失）
        lower_path = file_path.lower()
        if not (lower_path.endswith('.png') or lower_path.endswith('.jpg') or
                lower_path.endswith('.jpeg') or lower_path.endswith('.tiff') or
                lower_path.endswith('.tif') or lower_path.endswith('.bmp')):
            # 根据选中的 filter 添加默认扩展名
            if "PNG" in selected_filter:
                file_path += ".png"
            elif "JPEG" in selected_filter:
                file_path += ".jpg"
            elif "TIFF" in selected_filter:
                file_path += ".tiff"
            elif "BMP" in selected_filter:
                file_path += ".bmp"
            else:
                file_path += ".png"  # 默认

        # 创建 WindowToImageFilter（必须 Update 才能获取图像）
        w2if = vtk.vtkWindowToImageFilter()
        w2if.SetInput(self.vtk_widget.GetRenderWindow())
        w2if.SetScale(1)  # 可设为 2 以保存高分辨率图
        w2if.ReadFrontBufferOff()  # 更可靠地捕获渲染内容
        w2if.Update()

        # 根据扩展名选择写入器
        ext = file_path.lower()
        writer = None
        if ext.endswith('.png'):
            writer = vtk.vtkPNGWriter()
        elif ext.endswith('.jpg') or ext.endswith('.jpeg'):
            writer = vtk.vtkJPEGWriter()
            writer.SetQuality(95)  # 可选：设置 JPEG 质量 (1-100)
        elif ext.endswith('.tiff') or ext.endswith('.tif'):
            writer = vtk.vtkTIFFWriter()
        elif ext.endswith('.bmp'):
            writer = vtk.vtkBMPWriter()
        else:
            self.playback_status_label.setText("❌ Unsupported image format.")
            return

        writer.SetFileName(file_path)
        writer.SetInputConnection(w2if.GetOutputPort())
        writer.Write()

        self.playback_status_label.setText(f"✅ Screenshot saved: {os.path.basename(file_path)}")
