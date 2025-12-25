# log_statistics_widget.py
import os
import re
from pathlib import Path
from typing import Optional, List, Set

import pandas as pd
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QPlainTextEdit, QComboBox, QListView, 
    QListWidget, QLabel, QPushButton, QFileDialog, QMenu, QMessageBox,
    QGroupBox, QGridLayout, QListWidgetItem, QFormLayout
)
from PySide6.QtCore import Qt, Signal, QFileSystemWatcher
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QStandardItemModel, QStandardItem
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

class CheckableComboBox(QComboBox):
    selectionChanged = Signal()  # 可选：用于外部监听

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(False)
        self.setModel(QStandardItemModel(self))
        view = QListView()
        view.setUniformItemSizes(True)
        self.setView(view)
        self.setMaxVisibleItems(10)  # 👈 控制下拉最多显示10行
        self._placeholder = "Select items..."
        self.setPlaceholderText(self._placeholder)
        self._data_items = []

        # 关键：连接 view 的 pressed 信号
        self.view().pressed.connect(self._on_item_pressed)

    def addItems(self, texts):
        self._data_items = list(texts)
        self._rebuild_model()

    def _rebuild_model(self):
        model = self.model()
        model.clear()

        # 第0项：全选控制项（支持三态）
        select_all_item = QStandardItem("Select All")
        select_all_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        select_all_item.setData(Qt.Unchecked, Qt.CheckStateRole)
        model.appendRow(select_all_item)

        # 数据项
        for text in self._data_items:
            item = QStandardItem(text)
            item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setData(Qt.Unchecked, Qt.CheckStateRole)
            model.appendRow(item)

        self._update_display_text()

    def _on_item_pressed(self, index):
        model = self.model()
        item = model.itemFromIndex(index)
        if not item:
            return

        row = index.row()
        if row == 0:
            # 点击的是“全选”项
            current_state = item.checkState()
            if current_state == Qt.Checked:
                new_state = Qt.Unchecked
            else:
                new_state = Qt.Checked
            # 应用到所有数据项
            for i in range(1, model.rowCount()):
                model.item(i).setCheckState(new_state)
        else:
            # 点击的是普通数据项
            pass  # 状态已由 Qt 自动切换

        # 更新“全选”项状态（根据子项）
        self._update_select_all_state()
        self._update_display_text()
        self.selectionChanged.emit()

    def _update_select_all_state(self):
        """根据子项状态更新‘全选’项的三态"""
        model = self.model()
        if model.rowCount() <= 1:
            return

        checked_count = 0
        total = model.rowCount() - 1  # 排除第0项

        for i in range(1, model.rowCount()):
            if model.item(i).checkState() == Qt.Checked:
                checked_count += 1

        select_all_item = model.item(0)
        if checked_count == 0:
            select_all_item.setCheckState(Qt.Unchecked)
        elif checked_count == total:
            select_all_item.setCheckState(Qt.Checked)
        else:
            select_all_item.setCheckState(Qt.PartiallyChecked)

    def _update_display_text(self):
        checked = self.checked_items()
        if not checked:
            self.setPlaceholderText(self._placeholder)
            self.setCurrentText("")
        else:
            display = ", ".join(checked[:3])
            if len(checked) > 3:
                display += f" (+{len(checked) - 3} more)"
            self.setCurrentText(display)

    def checked_items(self):
        """返回所有被选中的真实数据项（不包括‘Select All’）"""
        model = self.model()
        checked = []
        for i in range(1, model.rowCount()):
            item = model.item(i)
            if item.checkState() == Qt.Checked:
                checked.append(item.text())
        return checked

    def set_checked_items(self, items_to_check):
        """可选：程序化设置选中项"""
        model = self.model()
        item_set = set(items_to_check)
        for i in range(1, model.rowCount()):
            item = model.item(i)
            item.setCheckState(Qt.Checked if item.text() in item_set else Qt.Unchecked)
        self._update_select_all_state()
        self._update_display_text()

class LogStatisticsWidget(QWidget):
    """
    升级版 Log & Statistics Widget
    - 支持外部设置项目路径（.mindes 同名目录）
    - 自动监听 Log.txt / Statistics.txt 文件变化
    - 多Y轴多曲线选择（左/右Y轴为多选列表）
    - 状态消息通过信号发出，供主窗口状态栏显示
    """

    # 状态信号：(message, level) 其中 level in {"info", "warning", "error"}
    statusMessage = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_path: Optional[Path] = None  # .mindes 同名结果目录
        self.data_df: Optional[pd.DataFrame] = None
        self.log_content = ""
        self.stat_content = ""

        # 文件监听器
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._on_file_changed)

        self.setup_ui()
        self.setup_shortcuts()

    def set_project_path(self, mindes_file: str):
        """由主窗口调用：设置当前 .mindes 文件路径，自动推导结果目录"""
        if not mindes_file:
            self._project_path = None
            self.statusMessage.emit("Project path cleared.", "info")
            return

        mindes_path = Path(mindes_file).resolve()
        self._project_path = mindes_path.with_suffix("")  # 去掉 .mindes，得到同名目录

        # 如果目录不存在，不报错，等运行后生成
        if not self._project_path.exists():
            self.log_edit.setPlainText("(Result directory not created yet)")
            self.stat_edit.setPlainText("(Result directory not created yet)")
            self.data_df = None
            self.update_combo_boxes()
            self.statusMessage.emit(f"Waiting for result dir: {self._project_path.name}", "info")
            return

        # 尝试加载
        self.load_log_and_statistics()

    def setup_shortcuts(self):
        self.load_log_stat_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        self.load_log_stat_shortcut.activated.connect(self.load_log_and_statistics)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # === 使用 QTabWidget 管理三个页面 ===
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # --- Tab 1: Log ---
        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(0, 0, 0, 0)  # 关键：去除容器边距
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(self._get_monospace_font())
        self.log_edit.setStyleSheet("background-color: #f0f0f0; color: black;")
        self.log_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        log_layout.addWidget(self.log_edit)
        self.tab_widget.addTab(log_container, "Log")

        # --- Tab 2: Statistic ---
        stat_container = QWidget()
        stat_layout = QVBoxLayout(stat_container)
        stat_layout.setContentsMargins(0, 0, 0, 0)  # 关键：去除容器边距
        self.stat_edit = QPlainTextEdit()
        self.stat_edit.setReadOnly(True)
        self.stat_edit.setFont(self._get_monospace_font())
        self.stat_edit.setStyleSheet("background-color: #f0f0f0; color: black;")
        self.stat_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        stat_layout.addWidget(self.stat_edit)
        self.tab_widget.addTab(stat_container, "Statistic")

        # --- Tab 3: Plot ---
        plot_page = QWidget()
        plot_layout = QVBoxLayout(plot_page)
        plot_layout.setContentsMargins(10, 5, 10, 5)

        # 控制面板：改用 QFormLayout（更紧凑）
        control_group = QGroupBox("Data Selection")
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)  # 让下拉框撑满
        form_layout.setSpacing(6)  # 减小行间距
        form_layout.setLabelAlignment(Qt.AlignRight)  # 标签右对齐，更整齐

        font = self.font()
        font.setPointSize(9)
        # X 轴
        self.x_combo = QComboBox()
        self.x_combo.currentIndexChanged.connect(self.update_plot)
        self.x_combo.setMinimumWidth(150)
        self.x_combo.setFont(font)
        form_layout.addRow("X Axis:", self.x_combo)

        # 左 Y 轴
        self.y1_combo = CheckableComboBox()
        self.y1_combo.selectionChanged.connect(self.update_plot)
        self.y1_combo.setMinimumWidth(150)
        self.y1_combo.setFont(font)
        form_layout.addRow("Left Y Axis:", self.y1_combo)

        # 右 Y 轴
        self.y2_combo = CheckableComboBox()
        self.y2_combo.selectionChanged.connect(self.update_plot)
        self.y2_combo.setMinimumWidth(150)
        self.y2_combo.setFont(font)
        form_layout.addRow("Right Y Axis:", self.y2_combo)

        control_group.setLayout(form_layout)
        plot_layout.addWidget(control_group)

        # Matplotlib 画布
        self.plot_figure = Figure(figsize=(6, 4), dpi=100)
        self.plot_canvas = FigureCanvas(self.plot_figure)
        plot_layout.addWidget(self.plot_canvas)

        # 保存按钮
        save_btn = QPushButton("💾 Save Plot")
        save_btn.clicked.connect(self.save_plot)
        plot_layout.addWidget(save_btn)

        self.tab_widget.addTab(plot_page, "Plot")

        # 初始化空图
        self.plot_figure.clear()
        self.plot_canvas.draw()

        # 右键菜单（可作用于整个 widget）
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def _get_monospace_font(self):
        font = QFont()
        families = ["Consolas", "Courier New", "Monaco", "DejaVu Sans Mono", "monospace"]
        for family in families:
            font.setFamily(family)
            if font.family() == family:
                break
        font.setPointSize(9)
        return font

    def show_context_menu(self, pos):
        menu = QMenu(self)
        load_log_stat_action = menu.addAction("Load data from MInDes")
        load_excel_action = menu.addAction("Load data from Excel")

        action = menu.exec(self.mapToGlobal(pos))
        if action == load_log_stat_action:
            self.load_log_and_statistics()
        elif action == load_excel_action:
            self.load_from_excel()

    def _clear_watcher(self):
        files = self.watcher.files()
        if files:
            self.watcher.removePaths(files)

    def load_log_and_statistics(self):
        """从 self._project_path 加载 Log.txt 和 Statistics.txt"""
        if not self._project_path or not self._project_path.exists():
            self.log_edit.setPlainText("(No valid project path)")
            self.stat_edit.setPlainText("(No valid project path)")
            self.data_df = None
            self.update_combo_boxes()
            return

        log_path = self._project_path / "Log.txt"
        stat_path = self._project_path / "Statistics.txt"

        # 清除旧监听
        self._clear_watcher()

        # 加载 Log.txt
        if log_path.exists():
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    self.log_content = f.read()
                self.log_edit.setPlainText(self.log_content)
                self.watcher.addPath(str(log_path))
            except Exception as e:
                self.log_edit.setPlainText(f"(Error reading Log.txt: {e})")
                self.statusMessage.emit(f"Failed to read Log.txt: {e}", "error")
        else:
            self.log_edit.setPlainText("(Log.txt not found)")

        # 加载 Statistics.txt 并解析为 DataFrame
        if stat_path.exists():
            try:
                with open(stat_path, 'r', encoding='utf-8') as f:
                    self.stat_content = f.read()
                self.stat_edit.setPlainText(self.stat_content)
                self.parse_statistics_to_dataframe(stat_path)
                self.watcher.addPath(str(stat_path))
            except Exception as e:
                self.stat_edit.setPlainText(f"(Error reading Statistics.txt: {e})")
                self.statusMessage.emit(f"Failed to read Statistics.txt: {e}", "error")
                self.data_df = None
        else:
            self.stat_edit.setPlainText("(Statistics.txt not found)")
            self.data_df = None

        self.update_combo_boxes()
        self.statusMessage.emit(f"Data loaded from: {self._project_path.name}", "info")

    def parse_statistics_to_dataframe(self, stat_file: Path):
        """尝试将 Statistics.txt 解析为结构化 DataFrame"""
        try:
            # 尝试直接读取表格（跳过注释和非表格行）
            df = pd.read_csv(
                stat_file,
                comment='#',
                delim_whitespace=True,
                skip_blank_lines=True,
                on_bad_lines='skip'
            )
            if not df.empty and len(df.columns) > 1:
                self.data_df = df
                return
        except:
            pass

        # 备用：逐行解析参数（适用于 input_report 风格）
        data_dict = {}
        current_step = 0
        step_data = {}

        with open(stat_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # 检测是否为新时间步分隔（如 "STEP 10"）
            if line.upper().startswith("STEP ") or re.match(r'^\s*\d+\s*$', line):
                if step_data:
                    for k, v in step_data.items():
                        if k not in data_dict:
                            data_dict[k] = []
                        data_dict[k].append(v)
                    step_data = {}
                    current_step += 1
                continue

            # 匹配 > [TAG] name = value
            match = re.match(r'^>\s*\[.*?\]\s*(\S+)\s*=\s*(.+)$', line)
            if match:
                key, val_str = match.groups()
                try:
                    val = float(val_str)
                    step_data[key] = val
                except ValueError:
                    continue  # 非数值跳过

        # 添加最后一组
        if step_data:
            for k, v in step_data.items():
                if k not in data_dict:
                    data_dict[k] = []
                data_dict[k].append(v)

        if data_dict:
            # 补齐长度（以防某些变量缺失）
            max_len = max(len(v) for v in data_dict.values())
            for k in data_dict:
                if len(data_dict[k]) < max_len:
                    data_dict[k].extend([float('nan')] * (max_len - len(data_dict[k])))
            self.data_df = pd.DataFrame(data_dict)
        else:
            self.data_df = None

    def load_from_excel(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Excel File", "", "Excel Files (*.xlsx *.xls);;All Files (*)"
        )
        if not file_path:
            return

        try:
            self.data_df = pd.read_excel(file_path)
            self.log_edit.setPlainText(f"(Data loaded from: {os.path.basename(file_path)})")
            self.stat_edit.setPlainText("(Excel mode – no text display)")
            self.update_combo_boxes()
            self.statusMessage.emit(f"Loaded Excel: {os.path.basename(file_path)}", "info")
        except Exception as e:
            self.statusMessage.emit(f"Failed to load Excel: {e}", "error")
            QMessageBox.critical(self, "Load Error", f"Failed to load Excel:\n{e}")

    def update_combo_boxes(self):
        """更新 X、Y1、Y2 下拉框"""
        self.x_combo.clear()
        self.y1_combo.clear()
        self.y2_combo.clear()

        if self.data_df is not None and not self.data_df.empty:
            columns = list(self.data_df.columns)
            self.x_combo.addItems(columns)
            self.y1_combo.addItems(columns)
            self.y2_combo.addItems(columns)
            if columns:
                self.x_combo.setCurrentIndex(0)  # 默认选第一列作为 X

    def _on_file_changed(self, path: str):
        """文件变化时自动重载（防抖可后续加）"""
        self.statusMessage.emit(f"Detected change in: {Path(path).name}, reloading...", "info")
        self.load_log_and_statistics()

    def update_plot(self):
        self.plot_figure.clear()
        if self.data_df is None or self.data_df.empty:
            self.plot_canvas.draw()
            return

        x_col = self.x_combo.currentText()
        if not x_col or x_col not in self.data_df.columns:
            self.plot_canvas.draw()
            return

        x = self.data_df[x_col]
        y1_cols = self.y1_combo.checked_items()  # ← 关键：使用新方法
        y2_cols = self.y2_combo.checked_items()  # ← 关键：使用新方法

        ax1 = self.plot_figure.add_subplot(111)
        ax2 = None

        # 左Y轴
        plotted_left = False
        for col in y1_cols:
            if col in self.data_df.columns:
                ax1.plot(x, self.data_df[col], '-', label=col)
                plotted_left = True
        if plotted_left:
            ax1.set_ylabel("Left Y", color='tab:blue')
            ax1.tick_params(axis='y', labelcolor='tab:blue')

        # 右Y轴
        if y2_cols:
            ax2 = ax1.twinx()
            for col in y2_cols:
                if col in self.data_df.columns:
                    ax2.plot(x, self.data_df[col], '--', label=col)
            ax2.set_ylabel("Right Y", color='tab:red')
            ax2.tick_params(axis='y', labelcolor='tab:red')

        ax1.set_xlabel(x_col)
        ax1.grid(True, linestyle='--', alpha=0.5)

        # 合并图例
        handles1, labels1 = ax1.get_legend_handles_labels()
        handles2, labels2 = (ax2.get_legend_handles_labels() if ax2 else ([], []))
        if handles1 or handles2:
            ax1.legend(handles1 + handles2, labels1 + labels2, loc='upper right')

        self.plot_figure.tight_layout()
        self.plot_canvas.draw()

    def save_plot(self):
        if not hasattr(self, 'plot_figure') or not self.plot_figure.axes:
            self.statusMessage.emit("No plot to save.", "warning")
            return

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save Plot", "",
            "PNG (*.png);;JPEG (*.jpg);;PDF (*.pdf);;SVG (*.svg);;All Files (*)"
        )
        if not file_path:
            return

        ext_map = {
            "PNG (*.png)": ".png",
            "JPEG (*.jpg)": ".jpg",
            "PDF (*.pdf)": ".pdf",
            "SVG (*.svg)": ".svg"
        }
        lower_path = file_path.lower()
        valid_exts = ['.png', '.jpg', '.jpeg', '.pdf', '.svg']
        if not any(lower_path.endswith(ext) for ext in valid_exts):
            ext = ext_map.get(selected_filter, ".png")
            file_path += ext

        try:
            self.plot_figure.savefig(file_path, dpi=300, bbox_inches='tight')
            self.statusMessage.emit(f"Plot saved: {os.path.basename(file_path)}", "info")
        except Exception as e:
            self.statusMessage.emit(f"Failed to save plot: {e}", "error")
            QMessageBox.critical(self, "Save Error", f"Failed to save plot:\n{e}")