# ui_control_panel.py
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QColorDialog, QComboBox, QFileDialog,
    QLabel, QCheckBox, QDoubleSpinBox, QLineEdit,
    QSlider, QSizePolicy, QScrollArea, QWidget, QFrame
)
from PySide6.QtGui import QDoubleValidator, QPixmap, QPainter, QColor
from PySide6.QtCore import Qt
import vtk
import os

class ControlPanelMixin:
    """
    左侧控制面板 UI
    - 只创建控件 & 连接信号
    - 不包含任何业务逻辑
    """

    def _create_control_panel(self):
        panel = QGroupBox("Data Controls")
        layout = QVBoxLayout()

        # =====================================================
        # Load
        # =====================================================
        self.load_btn = QPushButton("📂 Load .vts Folder")
        self.load_btn.clicked.connect(self._load_vts_interactive)
        layout.addWidget(self.load_btn)

        # =====================================================
        # Background
        # =====================================================
        bg_layout = QHBoxLayout()
        bg_layout.addWidget(QLabel("Background Color:"))
        self.bg_color_combo = QComboBox()
        self.bg_color_combo.addItems(
            ["White", "Light Gray", "Gray", "Dark Gray", "Black"]
        )
        self.bg_color_combo.setCurrentText("Light Gray")
        self.bg_color_combo.currentTextChanged.connect(
            self.update_background_color
        )
        bg_layout.addWidget(self.bg_color_combo)
        layout.addLayout(bg_layout)

        # =====================================================
        # Playback
        # =====================================================
        self.playback_group = QGroupBox("Playback Control")
        playback_layout = QVBoxLayout()

        play_btns = QHBoxLayout()
        self.draw_btns = QPushButton("🧊 Draw")
        self.draw_btns.clicked.connect(self.update_visualization)
        play_btns.addWidget(self.draw_btns)

        self.play_button = QPushButton("▶ Play")
        self.play_button.clicked.connect(self.start_sequential_playback)
        play_btns.addWidget(self.play_button)

        self.stop_button = QPushButton("⏹ Stop")
        self.stop_button.clicked.connect(self.stop_sequential_playback)
        self.stop_button.setEnabled(False)
        play_btns.addWidget(self.stop_button)

        playback_layout.addLayout(play_btns)

        auto_layout = QHBoxLayout()
        self.auto_update_checkbox = QCheckBox("Auto Update")
        self.auto_update_checkbox.stateChanged.connect(
            self.toggle_auto_update
        )
        auto_layout.addWidget(self.auto_update_checkbox)

        auto_layout.addWidget(QLabel("Interval:"))
        self.auto_update_interval_combo = QComboBox()
        self.auto_update_interval_combo.addItems(
            ["0.02s", "0.05s", "0.1s", "0.2s", "0.5s"]
        )
        self.auto_update_interval_combo.setCurrentText("0.5s")
        self.auto_update_interval_combo.setEnabled(True)
        auto_layout.addWidget(self.auto_update_interval_combo)

        playback_layout.addLayout(auto_layout)

        # === 添加分隔线 ===
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)        # 水平线
        separator.setFrameShadow(QFrame.Sunken)      # 凹陷样式（更美观）
        playback_layout.addWidget(separator)
        # =====================================================
        # Field & Colormap
        # =====================================================
        self.playback_status_label = QLabel("No data loaded")
        playback_layout.addWidget(self.playback_status_label)

        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel("VTS Files:"))
        self.file_combo = QComboBox()
        self.file_combo.currentIndexChanged.connect(
            self.on_file_combo_changed
        )
        self.file_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self.file_combo.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred
        )
        file_layout.addWidget(self.file_combo)

        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setMaximumWidth(30)
        self.refresh_btn.setSizePolicy(
            QSizePolicy.Fixed, QSizePolicy.Preferred
        )
        self.refresh_btn.clicked.connect(self.refresh_file_list)
        self.refresh_btn.setToolTip("Reload vts files")
        file_layout.addWidget(self.refresh_btn)
        playback_layout.addLayout(file_layout)

        field_layout = QHBoxLayout()
        field_layout.addWidget(QLabel("Data Fields:"))
        self.field_combo = QComboBox()
        self.field_combo.currentTextChanged.connect(
            self.on_field_selection_changed
        )
        self.field_combo.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred
        )
        field_layout.addWidget(self.field_combo)
        playback_layout.addLayout(field_layout)

        # === 添加分隔线 ===
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)        # 水平线
        separator.setFrameShadow(QFrame.Sunken)      # 凹陷样式（更美观）
        playback_layout.addWidget(separator)
        # =================

        map_layout = QHBoxLayout()
        map_layout.addWidget(QLabel("Colormap:"))
        self.colormap_combo = QComboBox()
        self.colormap_combo.addItems(
            ["Cool-Warm", "Rainbow", "Grayscale", "Viridis", "Plasma"]
        )
        self.colormap_combo.currentIndexChanged.connect(
            self.update_colormap_preview
        )
        self.colormap_combo.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred
        )
        map_layout.addWidget(self.colormap_combo)
        playback_layout.addLayout(map_layout)

        self.auto_range_checkbox = QCheckBox("Auto Data Range")
        self.auto_range_checkbox.setChecked(True)
        self.auto_range_checkbox.toggled.connect(self.toggle_range_edit)
        playback_layout.addWidget(self.auto_range_checkbox)

        range_layout = QHBoxLayout()
        self.min_spin = QDoubleSpinBox()
        self.min_spin.setRange(-1e6, 1e6)
        self.min_spin.setDecimals(4)
        self.min_spin.setEnabled(False)

        self.max_spin = QDoubleSpinBox()
        self.max_spin.setRange(-1e6, 1e6)
        self.max_spin.setDecimals(4)
        self.max_spin.setEnabled(False)

        range_layout.addWidget(QLabel("Min:"))
        range_layout.addWidget(self.min_spin)
        range_layout.addWidget(QLabel("Max:"))
        range_layout.addWidget(self.max_spin)
        playback_layout.addLayout(range_layout)

        playback_layout.addWidget(QLabel("Colormap:"))
        self.colorbar_label = QLabel()
        self.colorbar_label.setFixedHeight(20)
        playback_layout.addWidget(self.colorbar_label)

        # === 添加分隔线 ===
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)        # 水平线
        separator.setFrameShadow(QFrame.Sunken)      # 凹陷样式（更美观）
        playback_layout.addWidget(separator)
        # =================

        # =====================================================
        # Visualization mode
        # =====================================================
        map_layout = QHBoxLayout()
        map_layout.addWidget(QLabel("Draw Mode:"))
        self.vis_mode_combo = QComboBox()
        self.vis_mode_combo.addItems(
            ["Surface", "Surface with Grid", "Clip", "Contour", "Vector Arrows"]
        )
        self.vis_mode_combo.currentTextChanged.connect(
            self.on_vis_mode_changed
        )
        self.vis_mode_combo.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred
        )
        map_layout.addWidget(self.vis_mode_combo)
        playback_layout.addLayout(map_layout)
        
        # =====================================================
        # model controls
        # =====================================================
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
        clip_layout.addWidget(QLabel("Clip Position:"))
        clip_layout.addWidget(self.clip_slider)
        self.clip_group.setLayout(clip_layout)
        self.clip_group.setVisible(False)
        playback_layout.addWidget(self.clip_group)

        # Contour controls
        self.contour_group = QGroupBox("Contour (Isosurface)")
        contour_layout = QVBoxLayout()
        self.contour_levels_edit = QLineEdit()
        self.contour_levels_edit.setPlaceholderText("e.g., 0.5, 1.0, 1.5")
        contour_layout.addWidget(QLabel("Levels (comma-separated):"))
        contour_layout.addWidget(self.contour_levels_edit)
        self.contour_group.setLayout(contour_layout)
        self.contour_group.setVisible(False)
        playback_layout.addWidget(self.contour_group)
        
        # =====================================================
        # Vector Arrows Controls (Glyph)
        # =====================================================
        self.glyph_group = QGroupBox("Vector Arrows")
        glyph_layout = QVBoxLayout()

        # 颜色模式
        color_mode_layout = QHBoxLayout()
        color_mode_layout.addWidget(QLabel("Color Mode:"))
        self.glyph_color_mode_combo = QComboBox()
        self.glyph_color_mode_combo.addItems(["Single Color", "Colormap"])
        self.glyph_color_mode_combo.currentTextChanged.connect(self.on_glyph_color_mode_changed)
        color_mode_layout.addWidget(self.glyph_color_mode_combo)
        glyph_layout.addLayout(color_mode_layout)

        # 设置箭头颜色按钮（仅 Single Color 时可用）
        self.arrow_color_btn = QPushButton("Set Arrow Color")
        self.arrow_color_btn.clicked.connect(self.pick_arrow_color)
        glyph_layout.addWidget(self.arrow_color_btn)

        # 箭头大小模式
        size_mode_layout = QHBoxLayout()
        size_mode_layout.addWidget(QLabel("Size Mode:"))
        self.glyph_size_mode_combo = QComboBox()
        self.glyph_size_mode_combo.addItems(["Magnitude", "Uniform"])
        size_mode_layout.addWidget(self.glyph_size_mode_combo)
        glyph_layout.addLayout(size_mode_layout)

        # 缩放因子
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Scale Factor:"))
        # 创建 QLineEdit 代替 QSlider
        self.glyph_scale_edit = QLineEdit()
        self.glyph_scale_edit.setText("1.0")  # 默认值 1.0
        # 设置数值验证器：只允许正浮点数，范围 0.00001 ~ 100000.0（可调）
        validator = QDoubleValidator(0.00001, 100000.0, 5)  # 5 位小数
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.glyph_scale_edit.setValidator(validator)
        # 连接信号：当用户编辑完成时（回车或焦点离开）更新内部值
        self.glyph_scale_edit.editingFinished.connect(self.on_glyph_scale_edit_finished)
        scale_layout.addWidget(self.glyph_scale_edit)
        glyph_layout.addLayout(scale_layout)

        self.glyph_group.setLayout(glyph_layout)
        self.glyph_group.setVisible(False)  # 初始隐藏
        playback_layout.addWidget(self.glyph_group)

        # === 添加分隔线 ===
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)        # 水平线
        separator.setFrameShadow(QFrame.Sunken)      # 凹陷样式（更美观）
        playback_layout.addWidget(separator)
        # =================

        # =====================================================
        # Opacity
        # =====================================================
        op_layout = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.opacity_slider.setTickInterval(10)
        self.opacity_slider.setMinimumWidth(100)
        self.opacity_slider.valueChanged.connect(
            self.on_opacity_slider_changed
        )
        self.opacity_value_label = QLabel("1.00")
        self.opacity_value_label.setMinimumWidth(40)
        op_layout.addWidget(QLabel("Opacity:"))
        op_layout.addWidget(self.opacity_slider)
        op_layout.addWidget(self.opacity_value_label)
        playback_layout.addLayout(op_layout)

        # With boundary
        self.show_with_boundary_checkbox = QCheckBox("With Boundary")
        self.show_with_boundary_checkbox.setChecked(True)
        playback_layout.addWidget(self.show_with_boundary_checkbox)

        self.playback_group.setLayout(playback_layout)
        self.playback_group.setVisible(False)
        layout.addWidget(self.playback_group)
        # =====================================================
        # Plot Over Line
        # =====================================================
        self.plot_line_checkbox = QCheckBox("📏 Plot Over Line")
        self.plot_line_checkbox.stateChanged.connect(self.toggle_plot_over_line)
        self.plot_line_checkbox.setVisible(False)
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

        self.set_line_btn = QPushButton("Get Data")
        self.set_line_btn.clicked.connect(self.set_line_from_inputs)
        self.set_line_btn.setEnabled(False)
        button_layout.addWidget(self.set_line_btn)

        self.export_excel_btn = QPushButton("📤 Export Data")
        self.export_excel_btn.clicked.connect(self.export_line_data)
        button_layout.addWidget(self.export_excel_btn)

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

        self.y_axis_range_group = QGroupBox("Y Axis Range")
        y_range_layout = QGridLayout()
        self.auto_y_range_checkbox = QCheckBox("Auto Y Range")
        self.auto_y_range_checkbox.setChecked(True)
        self.auto_y_range_checkbox.toggled.connect(self.toggle_y_axis_range)
        y_range_layout.addWidget(self.auto_y_range_checkbox, 0, 0, 1, 4)

        self.y_min_spin = QDoubleSpinBox()
        self.y_max_spin = QDoubleSpinBox()
        for spin in (self.y_min_spin, self.y_max_spin):
            spin.setRange(-1e12, 1e12)
            spin.setDecimals(6)
            spin.setEnabled(False)
            spin.editingFinished.connect(self.apply_manual_y_axis_range)
        self.y_max_spin.setValue(1.0)

        y_range_layout.addWidget(QLabel("Min:"), 1, 0)
        y_range_layout.addWidget(self.y_min_spin, 1, 1)
        y_range_layout.addWidget(QLabel("Max:"), 1, 2)
        y_range_layout.addWidget(self.y_max_spin, 1, 3)
        self.y_axis_range_group.setLayout(y_range_layout)
        self.y_axis_range_group.setVisible(False)
        layout.addWidget(self.y_axis_range_group)

        layout.addStretch()
        # =====================================================
        # Visualization Enhancements
        # =====================================================
        self.display_group = QGroupBox("Display Options:")
        display_layout = QVBoxLayout()

        self.show_axes_checkbox = QCheckBox("Show XYZ Axes")
        self.show_axes_checkbox.setChecked(False)
        self.show_axes_checkbox.stateChanged.connect(self.update_axes_visibility)
        display_layout.addWidget(self.show_axes_checkbox)

        self.show_bounds_checkbox = QCheckBox("Show Domain Bounds")
        self.show_bounds_checkbox.setChecked(False)
        self.show_bounds_checkbox.stateChanged.connect(self.update_bounds_visibility)
        display_layout.addWidget(self.show_bounds_checkbox)

        self.show_colorbar_checkbox = QCheckBox("Show Color Bar")
        self.show_colorbar_checkbox.setChecked(False)
        self.show_colorbar_checkbox.stateChanged.connect(self.update_colorbar_visibility)
        display_layout.addWidget(self.show_colorbar_checkbox)

        # View reset buttons
        view_hbox = QHBoxLayout()
        for axis in ["X", "Y", "Z"]:
            btn = QPushButton(f"View {axis}")
            btn.clicked.connect(lambda _, a=axis: self.reset_view(a))
            view_hbox.addWidget(btn)
        display_layout.addLayout(view_hbox)
        self.display_group.setLayout(display_layout)
        self.display_group.setVisible(False)
        layout.addWidget(self.display_group)

        # Save screenshot
        self.save_btn = QPushButton("💾 Save Screenshot")
        self.save_btn.clicked.connect(self.save_screenshot)
        layout.addWidget(self.save_btn)
        # =====================================================
        # Finalize panel
        # =====================================================
        panel.setLayout(layout)
        # 限制 panel 的最大宽度，防止内部控件撑宽
        panel.setMaximumWidth(self.control_panel_width - 10)  # 略小于 scroll_area 的固定宽度 control_panel_width
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        # === 包装进 QScrollArea ===
        self.scroll = QScrollArea()
        self.scroll.setWidget(panel)
        self.scroll.setWidgetResizable(True) # 让内部 widget 自适应大小
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)  # 可选：去掉边框更美观
        # 禁用水平滚动条（只保留垂直）
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        return self.scroll

    def on_field_selection_changed(self, display_text):
        current_index = self.vis_mode_combo.currentIndex()
        is_vector = display_text.startswith("[V]")
        # 纠偏
        self.vis_mode_combo.blockSignals(True)
        arrow_index = self.vis_mode_combo.findText("Vector Arrows")
        if (arrow_index == current_index and not is_vector) or current_index == -1:
            index = self.vis_mode_combo.findText("Surface")
            self.vis_mode_combo.setCurrentIndex(index)
            self.vis_mode_combo.setCurrentText("Surface")
            self.on_vis_mode_changed("Surface")
        self.vis_mode_combo.blockSignals(False)
        self.update_range_inputs()
    
    def on_glyph_color_mode_changed(self, mode):
        single_color = (mode == "Single Color")
        self.arrow_color_btn.setEnabled(single_color)

    def toggle_range_edit(self, checked):
        enabled = not checked
        self.min_spin.setEnabled(enabled)
        self.max_spin.setEnabled(enabled)
        self.update_range_inputs()

    def pick_arrow_color(self):
        color = QColorDialog.getColor(
            QColor.fromRgbF(*self.arrow_color),
            self,
            "Select Arrow Color"
        )
        if color.isValid():
            self.arrow_color = (color.redF(), color.greenF(), color.blueF())

    def on_vis_mode_changed(self, mode):
        self.current_vis_mode = mode
        self.clip_group.setVisible(mode == "Clip")
        self.contour_group.setVisible(mode == "Contour")
        self.glyph_group.setVisible(mode == "Vector Arrows")

    def on_opacity_slider_changed(self, value):
        """处理透明度滑块值变化"""
        opacity = value / 100.0  # 转换为 0.0-1.0
        self.opacity_value_label.setText(f"{opacity:.2f}")

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

    def _update_arrow_controls_visibility(self):
        is_vector = self.field_combo.currentText().startswith("[V]")
        vsi_mode = self.vis_mode_combo.currentText()
        show_glyph = vsi_mode == "Vector Arrows" and is_vector
        self.arrow_color_btn.setVisible(show_glyph)
        self.color_arrows_by_mag_checkbox.setVisible(show_glyph)
        if not show_glyph:
            self.color_arrows_by_mag_checkbox.setChecked(False)

    def update_range_inputs(self):
        if not self.current_data or not self.auto_range_checkbox.isChecked():
            return
        display_text = self.field_combo.currentText()
        if "(No fields)" in display_text:
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

    def _create_line_style_group(self):
        group = QGroupBox("Line Style")
        self.line_style_layout = QVBoxLayout()
        group.setLayout(self.line_style_layout)
        self.line_style_group = group
        group.setVisible(False)  # 初始隐藏
        return group

    def _disable_all_interactive_controls(self, disable=True):
        widgets = [
            self.load_btn,
            self.file_combo,
            self.field_combo,
            self.colormap_combo,
            self.auto_range_checkbox,
            self.min_spin,
            self.max_spin,
            self.glyph_color_mode_combo,
            self.arrow_color_btn,
            self.glyph_size_mode_combo,
            self.glyph_scale_edit,
            self.vis_mode_combo,
            self.clip_axis_combo,
            self.clip_slider,
            self.contour_levels_edit,
            self.opacity_slider,
            self.plot_line_checkbox,
            self.show_axes_checkbox,
            self.show_bounds_checkbox,
            self.show_colorbar_checkbox,
            self.show_with_boundary_checkbox,
            self.draw_btns,
            self.play_button,
            self.stop_button,                   
            self.auto_update_checkbox,
            self.auto_update_interval_combo,
            self.save_btn,                      
            self.set_line_btn,                 
            self.export_excel_btn,
            self.auto_y_range_checkbox,
            self.y_min_spin,
            self.y_max_spin,
            self.bg_color_combo,
            self.refresh_btn,             
            # 坐标输入框（虽被 group 覆盖，但显式更安全）
            self.p1x, self.p1y, self.p1z,
            self.p2x, self.p2y, self.p2z,
        ]
        for w in widgets:
            if w is not None:
                w.setDisabled(disable)
        if not disable:
            manual_y_range = not self.auto_y_range_checkbox.isChecked()
            self.y_min_spin.setEnabled(manual_y_range)
            self.y_max_spin.setEnabled(manual_y_range)

        # 原有 group 循环保留（作为兜底）
        for group in [self.clip_group, self.contour_group, self.line_endpoint_group]:
            if group and group.layout():
                for i in range(group.layout().count()):
                    item = group.layout().itemAt(i)
                    if item.widget():
                        item.widget().setDisabled(disable)

    # =====================================================
    # Colormap
    # =====================================================

    def update_colormap_preview(self):
        pixmap = QPixmap(self.control_panel_width-60, 20)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        lut = vtk.vtkLookupTable()
        colormap_name = self.colormap_combo.currentText()
        if colormap_name == "Cool-Warm":
            self._setup_coolwarm_lut(lut)
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
        lut.SetTableRange((0.0, 1.0))
        lut.Build()
        width = pixmap.width()
        for i in range(width):
            t = i / max(1, width - 1)
            rgb = [0.0, 0.0, 0.0]
            lut.GetColor(t, rgb)
            color = QColor.fromRgbF(*rgb)
            painter.fillRect(i, 0, 1, 20, color)
        painter.end()
        self.colorbar_label.setPixmap(pixmap)

    def on_glyph_scale_edit_finished(self):
        """当用户在 glyph scale 输入框中完成编辑时调用"""
        text = self.glyph_scale_edit.text().strip()
        if not text:
            self.glyph_scale_edit.setText("1.0")
            return
        try:
            value = float(text)
            if value < 0.001:
                value = 0.001
                self.glyph_scale_edit.setText(f"{value:.3f}")
            elif value > 100.0:
                value = 100.0
                self.glyph_scale_edit.setText(f"{value:.2f}")
        except ValueError:
            self.glyph_scale_edit.setText("1.0")
