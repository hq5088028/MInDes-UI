# log_statistics_widget.py
import os
import re
from pathlib import Path
from typing import Optional

import pandas as pd
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QPlainTextEdit, QComboBox, QFrame, 
    QLabel, QPushButton, QFileDialog, QMenu, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QFileSystemWatcher
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# === 定义候选文件名（按优先级排序，高 → 低）===
LOG_CANDIDATES = ["Log.txt", "log.txt"]
STAT_CANDIDATES = ["Statistics.txt", "data_statistics.txt"]

def get_existing_candidates_by_mtime(base_dir: Path, candidates: list[str]) -> list[Path]:
    """
    返回 base_dir 下所有命中的候选文件，按“最后写入时间”从新到旧排序。
    若写入时间相同，则按 candidates 中的先后顺序决定优先级。
    """
    ranked = []

    for priority, name in enumerate(candidates):
        path = base_dir / name
        if not (path.exists() and path.is_file()):
            continue
        try:
            ranked.append((path.stat().st_mtime_ns, -priority, path))
        except OSError:
            continue

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in ranked]

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

    def __init__(self, parent=None, progress_callback=None):
        super().__init__(parent)
        self.progress_callback = progress_callback
        self._project_path: Optional[Path] = None  # .mindes 同名结果目录
        self.data_df: Optional[pd.DataFrame] = None
        self.log_content = ""
        self.stat_content = ""
        # 绘图监控
        self.is_drawing = False

        # 文件监听器
        self._report_progress("   Creating Log widget watcher...")
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._on_file_changed)

        self.setup_ui()

        self._report_progress("Binding shortcuts...")
        self.setup_shortcuts()

        # === 缓存自定义绘图参数 ===
        self.plot_config = {
            "title": "",
            "xlabel": "",
            "ylabel1": "",
            "ylabel2": "",
            "show_box": True,
            "show_grid": True,
            # 可扩展：line_color, line_width 等
        }

    def _report_progress(self, detail: str):
        if self.progress_callback:
            self.progress_callback(detail)

    def set_project_path(self, project_folder: str):
        """由主窗口调用：设置当前 .mindes 文件路径，自动推导结果目录"""
        if not project_folder:
            self._project_path = None
            self.statusMessage.emit("Project path cleared.", "info")
            # 可选：清空 UI
            self.log_edit.setPlainText("(No valid project path)")
            self.stat_edit.setPlainText("(No valid project path)")
            self.data_df = None
            self.update_combo_boxes()
            return

        # 将传入的 project_folder 视为 _project_path（无后缀的基础路径）
        base_path = Path(project_folder).resolve()
        self._project_path = base_path  # 这就是结果目录路径

        # 推导对应的 .mindes 文件路径
        mindes_path = base_path.with_suffix(".mindes")

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
        self._report_progress("   Creating Log/Statistic tabs...")
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
        self._report_progress("   Creating Figure tab controls...")
        plot_page = QWidget()
        plot_layout = QVBoxLayout(plot_page)
        plot_layout.setContentsMargins(10, 5, 10, 5)

        # === 控制面板：X, Y1, Y2 单选 + Plot + Property ===
        control_hbox = QHBoxLayout()
        control_hbox.setSpacing(8)

        # X Axis
        x_label = QLabel("X Axis:")
        self.x_combo = QComboBox()
        self.x_combo.setFixedWidth(120)  # ← 改为 120px
        control_hbox.addWidget(x_label)
        control_hbox.addWidget(self.x_combo)

        # Left Y Axis
        y1_label = QLabel("Left Y:")
        self.y1_combo = QComboBox()
        self.y1_combo.setFixedWidth(120)
        control_hbox.addWidget(y1_label)
        control_hbox.addWidget(self.y1_combo)

        # Right Y Axis
        y2_label = QLabel("Right Y:")
        self.y2_combo = QComboBox()
        self.y2_combo.setFixedWidth(120)
        control_hbox.addWidget(y2_label)
        control_hbox.addWidget(self.y2_combo)

        control_hbox.addStretch()
        plot_layout.addLayout(control_hbox)

        # >>> 横线 <<<
        top_line = QFrame()
        top_line.setFrameShape(QFrame.Shape.HLine)
        top_line.setFrameShadow(QFrame.Shadow.Sunken)
        plot_layout.addWidget(top_line)

        # Matplotlib 画布
        self._report_progress("   Creating plot canvas...")
        self.plot_figure = Figure(figsize=(6, 4), dpi=100)
        self.plot_canvas = FigureCanvas(self.plot_figure)
        plot_layout.addWidget(self.plot_canvas)

        # >>> 横线 <<<
        bottom_line = QFrame()
        bottom_line.setFrameShape(QFrame.Shape.HLine)
        bottom_line.setFrameShadow(QFrame.Shadow.Sunken)
        plot_layout.addWidget(bottom_line)

        # === 操作按钮：Draw / Property / Save ===
        self._report_progress("   Creating plot actions...")
        button_hbox = QHBoxLayout()
        button_hbox.setSpacing(8)

        self.plot_btn = QPushButton("📊 Draw")
        self.plot_btn.setShortcut(QKeySequence("Ctrl+D"))
        self.plot_btn.clicked.connect(self.update_plot)
        button_hbox.addWidget(self.plot_btn)

        self.property_btn = QPushButton("⚙️ Property")
        self.property_btn.setShortcut(QKeySequence("Ctrl+P"))
        self.property_btn.clicked.connect(self.open_plot_customization_dialog)
        button_hbox.addWidget(self.property_btn)

        self.export_btn = QPushButton("📤 Export")
        self.export_btn.setShortcut(QKeySequence("Ctrl+E"))
        self.export_btn.clicked.connect(self.export_to_excel)
        button_hbox.addWidget(self.export_btn)

        self.save_btn = QPushButton("💾 Save")
        self.save_btn.setShortcut(QKeySequence("Ctrl+S"))
        self.save_btn.clicked.connect(self.save_plot)
        button_hbox.addWidget(self.save_btn)

        plot_layout.addLayout(button_hbox)

        self.tab_widget.addTab(plot_page, "Figure")

        # 初始化空图
        self.plot_figure.clear()
        self.plot_canvas.draw()

        # 右键菜单（用于图形调整）
        self.plot_canvas.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.plot_canvas.customContextMenuRequested.connect(self.show_plot_context_menu)

    def export_to_excel(self):
        """将当前 data_df 导出为 Excel 文件"""
        if self.data_df is None or self.data_df.empty:
            self.statusMessage.emit("No data to export.", "warning")
            QMessageBox.warning(self, "Export Error", "No data available to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Data to Excel",
            "",
            "Excel Files (*.xlsx);;CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        try:
            if file_path.lower().endswith('.csv'):
                self.data_df.to_csv(file_path, index=False)
            else:
                # Ensure .xlsx extension
                if not file_path.lower().endswith('.xlsx'):
                    file_path += '.xlsx'
                self.data_df.to_excel(file_path, index=False, engine='openpyxl')
            self.statusMessage.emit(f"Data exported: {os.path.basename(file_path)}", "info")
        except Exception as e:
            self.statusMessage.emit(f"Export failed: {e}", "error")
            QMessageBox.critical(self, "Export Error", f"Failed to export data:\n{e}")

    def _get_monospace_font(self):
        font = QFont()
        families = ["Consolas", "Courier New", "Monaco", "DejaVu Sans Mono", "monospace"]
        for family in families:
            font.setFamily(family)
            if font.family() == family:
                break
        font.setPointSize(9)
        return font

    def _clear_watcher(self):
        files = self.watcher.files()
        if files:
            self.watcher.removePaths(files)

    def load_log_and_statistics(self):
        """从 self._project_path 加载日志和统计文件（支持多版本命名）"""
        if not self._project_path or not self._project_path.exists():
            self.log_edit.setPlainText("(No valid project path)")
            self.stat_edit.setPlainText("(No valid project path)")
            self.data_df = None
            self.update_combo_boxes()
            return
        # 清除旧监听
        self._clear_watcher()
        # --- 加载 Log 文件 ---
        log_content = "(Log file not found)"
        loaded_log_path = None
        log_candidates = get_existing_candidates_by_mtime(self._project_path, LOG_CANDIDATES)
        for path in log_candidates:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    log_content = f.read()
                loaded_log_path = path
                break
            except Exception as e:
                self.statusMessage.emit(f"Failed to read {path.name}: {e}", "error")
                continue

        self.log_edit.setPlainText(log_content)
        # 滚动到底部
        self.log_edit.verticalScrollBar().setValue(
            self.log_edit.verticalScrollBar().maximum()
        )
        for path in log_candidates:
            self.watcher.addPath(str(path))
        # --- 加载 Statistics 文件 ---
        stat_content = "(Statistics file not found)"
        loaded_stat_path = None
        self.data_df = None  # 默认无数据
        stat_candidates = get_existing_candidates_by_mtime(self._project_path, STAT_CANDIDATES)
        for path in stat_candidates:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    stat_content = f.read()
                loaded_stat_path = path
                # 尝试解析为 DataFrame
                self.parse_statistics_to_dataframe(path)
                break
            except Exception as e:
                self.statusMessage.emit(f"Failed to read or parse {path.name}: {e}", "error")
                continue

        self.stat_edit.setPlainText(stat_content)
        # >>> 滚动到底部 <<<
        self.stat_edit.verticalScrollBar().setValue(
            self.stat_edit.verticalScrollBar().maximum()
        )
        for path in stat_candidates:
            self.watcher.addPath(str(path))
        # --- 更新 UI 控件 ---
        self.update_combo_boxes()
        # === 自动重绘（如果用户之前绘制过）===
        if self.is_drawing:
            self.update_plot()
        # --- 发送状态消息 ---
        msg_parts = []
        if loaded_log_path:
            if loaded_log_path.name != "Log.txt":
                msg_parts.append(f"legacy log: {loaded_log_path.name}")
        if loaded_stat_path:
            if loaded_stat_path.name != "Statistics.txt":
                msg_parts.append(f"legacy stats: {loaded_stat_path.name}")
        if loaded_log_path or loaded_stat_path:
            base_msg = f"Data loaded from: {self._project_path.name}"
            if msg_parts:
                base_msg += " (" + ", ".join(msg_parts) + ")"
            self.statusMessage.emit(base_msg, "info")
        else:
            self.statusMessage.emit(f"No output files found in: {self._project_path.name}", "warning")

    def _on_file_changed(self, path: str):
        """当被监视的文件（Log.txt / Statistics.txt）发生变化时触发"""
        from pathlib import Path
        file_name = Path(path).name
        self.statusMessage.emit(f"Detected change in {file_name}, reloading...", "info")
        self.load_log_and_statistics()

    def parse_statistics_to_dataframe(self, stat_file: Path):
        """尝试将 Statistics.txt 解析为结构化 DataFrame"""
        try:
            # 主路径：标准表格格式（支持空格、制表符分隔）
            df = pd.read_csv(
                stat_handled := str(stat_file),
                comment='#',
                sep=r'\s+',
                skip_blank_lines=True,
                on_bad_lines='warn',  # 改为 warn，便于调试
                engine='python'       # 更容错（可选）
            )
            if not df.empty and len(df.columns) >= 1:
                self.data_df = df
                return
        except Exception as e:
            self.statusMessage.emit(f"Primary parsing failed: {e}", "warning")

        # === Fallback: only if main fails ===
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
        """更新 X、Y1、Y2 下拉框选项，并尽可能保留用户已有选择"""
        # === 1. 保存当前用户选择 ===
        current_x = self.x_combo.currentText()
        current_y1 = self.y1_combo.currentText()
        current_y2 = self.y2_combo.currentText()

        # === 2. 清空现有选项 ===
        self.x_combo.clear()
        self.y1_combo.clear()
        self.y2_combo.clear()

        # === 3. 填充新选项 ===
        if self.data_df is not None and not self.data_df.empty:
            columns = list(self.data_df.columns)
            self.x_combo.addItems(columns)
            y_items = ["-"] + columns
            self.y1_combo.addItems(y_items)
            self.y2_combo.addItems(y_items)

            # === 4. 恢复 X 选择（必须是有效列）===
            if current_x in columns:
                idx = self.x_combo.findText(current_x)
                if idx != -1:
                    self.x_combo.setCurrentIndex(idx)
                else:
                    self.x_combo.setCurrentIndex(0)  # fallback
            elif columns:
                self.x_combo.setCurrentIndex(0)  # 默认第一列

            # === 5. 恢复 Y1 选择（可以是 "-" 或有效列）===
            if current_y1 == "-" or current_y1 in columns:
                idx = self.y1_combo.findText(current_y1)
                if idx != -1:
                    self.y1_combo.setCurrentIndex(idx)
                else:
                    self.y1_combo.setCurrentIndex(0)  # "-"
            else:
                self.y1_combo.setCurrentIndex(0)  # 默认 "-"

            # === 6. 恢复 Y2 选择（可以是 "-" 或有效列）===
            if current_y2 == "-" or current_y2 in columns:
                idx = self.y2_combo.findText(current_y2)
                if idx != -1:
                    self.y2_combo.setCurrentIndex(idx)
                else:
                    self.y2_combo.setCurrentIndex(0)  # "-"
            else:
                self.y2_combo.setCurrentIndex(0)  # 默认 "-"
        else:
            # 无数据：只显示 "-" 选项
            self.y1_combo.addItem("-")
            self.y2_combo.addItem("-")
            self.y1_combo.setCurrentIndex(0)
            self.y2_combo.setCurrentIndex(0)
            # X 轴留空（无选项）

    def update_plot(self):
        self.plot_figure.clear()
        if self.data_df is None or self.data_df.empty:
            self.plot_canvas.draw()
            self.is_drawing = False
            return

        x_col = self.x_combo.currentText()
        y1_col = self.y1_combo.currentText()
        y2_col = self.y2_combo.currentText()

        if not x_col or x_col not in self.data_df.columns:
            self.plot_canvas.draw()
            self.is_drawing = False
            return

        x = self.data_df[x_col]
        ax1 = self.plot_figure.add_subplot(111)
        ax2 = None

        # 左 Y 轴（跳过 "-"）
        if y1_col != "-" and y1_col in self.data_df.columns:
            ax1.plot(x, self.data_df[y1_col], 'k-', label=y1_col)
            default_ylabel1 = y1_col
        else:
            default_ylabel1 = ""

        # 右 Y 轴（跳过 "-" 且不与左轴重复）
        if y2_col != "-" and y2_col in self.data_df.columns and y2_col != y1_col:
            ax2 = ax1.twinx()
            ax2.plot(x, self.data_df[y2_col], 'r--', label=y2_col)
            default_ylabel2 = y2_col
        else:
            default_ylabel2 = ""

        # 应用缓存的自定义参数（若未设置，则用默认列名）
        title = self.plot_config["title"]
        xlabel = self.plot_config["xlabel"] or x_col
        ylabel1 = self.plot_config["ylabel1"] or default_ylabel1
        ylabel2 = self.plot_config["ylabel2"] or default_ylabel2
        show_box = self.plot_config.get("show_box", True)
        show_grid = self.plot_config.get("show_grid", True)

        ax1.set_title(title, color='black', fontweight='bold')
        ax1.set_xlabel(xlabel, color='black', fontweight='bold')
        # 设置左Y轴标签和其属性
        if ylabel1:
            ax1.set_ylabel(ylabel1, color='black', fontweight='bold')  # 字体颜色设为黑色，字号加大，加粗
            ax1.tick_params(axis='y', labelcolor='black')  # 刻度标签颜色设为黑色，字号加大
        # 设置右Y轴标签及其属性
        if ax2 and ylabel2:
            ax2.set_ylabel(ylabel2, color='tab:red', fontweight='bold')  # 右侧保持红色但字号加大，加粗
            ax2.tick_params(axis='y', labelcolor='tab:red')  # 刻度标签颜色设为红色，字号加大

        # 边框
        for spine in ax1.spines.values():
            spine.set_visible(show_box)
        if ax2:
            for spine in ax2.spines.values():
                spine.set_visible(show_box)

        # 网格
        ax1.grid(show_grid, linestyle='--', alpha=0.5)

        # 图例
        handles1, labels1 = ax1.get_legend_handles_labels()
        handles2, labels2 = (ax2.get_legend_handles_labels() if ax2 else ([], []))
        if handles1 or handles2:
            ax1.legend(handles1 + handles2, labels1 + labels2, loc='upper left')

        self.plot_figure.tight_layout()
        self.plot_canvas.draw()
        self.is_drawing = True

    def save_plot(self):
        if not hasattr(self, 'plot_figure') or not self.plot_figure.axes:
            self.statusMessage.emit("No figure to save.", "warning")
            return

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save Figure", "",
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
            self.statusMessage.emit(f"Figure saved: {os.path.basename(file_path)}", "info")
        except Exception as e:
            self.statusMessage.emit(f"Failed to save figure: {e}", "error")
            QMessageBox.critical(self, "Save Error", f"Failed to save figure:\n{e}")

    def show_plot_context_menu(self, pos):
        menu = QMenu(self)
        draw_action = menu.addAction("Draw (Ctrl+D)")
        customize_action = menu.addAction("Property (Ctrl+P)")
        save_action = menu.addAction("Save (Ctrl+S)")
        action = menu.exec(self.plot_canvas.mapToGlobal(pos))
        if action == draw_action:
            self.update_plot()
        elif action == customize_action:
            self.open_plot_customization_dialog()
        elif action == save_action:
            self.save_plot()

    def open_plot_customization_dialog(self):
        from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QCheckBox, QPushButton, QMessageBox

        dialog = QDialog(self)
        dialog.setWindowTitle("Figure Properties")
        layout = QFormLayout(dialog)

        if not self.plot_figure.axes:
            QMessageBox.warning(self, "No Figure", "Please draw a figure first.")
            return

        ax1 = self.plot_figure.axes[0]
        # ax2 = ax1.right_ax if hasattr(ax1, 'right_ax') else None
        if len(self.plot_figure.axes)>1:
            ax2 = self.plot_figure.axes[1]
        else:
            ax2 = None

        # 创建控件并加载缓存值
        title_edit = QLineEdit(self.plot_config["title"])
        xlabel_edit = QLineEdit(self.plot_config["xlabel"])
        ylabel1_edit = QLineEdit(self.plot_config["ylabel1"])
        ylabel2_edit = QLineEdit(self.plot_config["ylabel2"]) if ax2 else None

        box_checkbox = QCheckBox()
        box_checkbox.setChecked(self.plot_config["show_box"])
        grid_checkbox = QCheckBox()
        grid_checkbox.setChecked(self.plot_config["show_grid"])

        layout.addRow("Title:", title_edit)
        layout.addRow("X Label:", xlabel_edit)
        layout.addRow("Y1 Label:", ylabel1_edit)
        if ax2 and ylabel2_edit:
            layout.addRow("Y2 Label:", ylabel2_edit)
        layout.addRow("Show Box Frame:", box_checkbox)
        layout.addRow("Show Grid:", grid_checkbox)

        apply_btn = QPushButton("Apply")
        layout.addRow(apply_btn)

        def apply_changes():
            # 更新缓存
            self.plot_config["title"] = title_edit.text().strip()
            self.plot_config["xlabel"] = xlabel_edit.text().strip()
            self.plot_config["ylabel1"] = ylabel1_edit.text().strip()
            if ax2 and ylabel2_edit:
                self.plot_config["ylabel2"] = ylabel2_edit.text().strip()
            self.plot_config["show_box"] = box_checkbox.isChecked()
            self.plot_config["show_grid"] = grid_checkbox.isChecked()

            # 刷新图表（应用新配置）
            self.update_plot()
            dialog.accept()

        apply_btn.clicked.connect(apply_changes)
        dialog.exec()