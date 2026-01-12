from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QPushButton, QHeaderView, QHBoxLayout, QCheckBox, QComboBox,
    QSizePolicy, QWidget, QColorDialog, QFileDialog
)
import vtk
import os
import math
import pandas as pd
import numpy as np
from vts_viewer.models import PandasModel
from vts_viewer.utils import clean_excel_string

class PlotOverLineMixin:
    """
    左侧控制面板 UI
    - 只创建控件 & 连接信号
    - 不包含任何业务逻辑
    """

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

    def _update_line_input_fields(self, p1, p2):
        self.plot_line_p1 = list(p1)
        self.plot_line_p2 = list(p2)
        self.p1x.setText(f"{p1[0]:.4f}")
        self.p1y.setText(f"{p1[1]:.4f}")
        self.p1z.setText(f"{p1[2]:.4f}")
        self.p2x.setText(f"{p2[0]:.4f}")
        self.p2y.setText(f"{p2[1]:.4f}")
        self.p2z.setText(f"{p2[2]:.4f}")

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

    def _on_line_visible_changed(self, field, state):
        self._line_styles[field]['visible'] = (state == Qt.CheckState.Checked.value)
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

