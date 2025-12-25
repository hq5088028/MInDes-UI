# MInDes-UI.py
import sys, os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QLabel, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

# 导入组件
from vts_viewer_widget import VTSViewerWidget
from file_browser_widget import FileBrowserWidget
from build_simulation_widget import BuildSimulationWidget  
from log_statistics_widget import LogStatisticsWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MInDes - Microstructure Intelligent Design")
        self.resize(1200, 800)
        self.current_project_path = None
        self.build_widget = None
        self.setup_ui()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧面板
        left_panel = QWidget()
        left_panel.setFixedWidth(200)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 0, 2, 5)

        self.create_menu_bar()

        self.file_browser = FileBrowserWidget()
        self.file_browser.pathEdited.connect(self.on_path_edited)
        self.file_browser.folderDoubleClicked.connect(self.on_folder_double_clicked)
        self.file_browser.fileDoubleClicked.connect(self.load_mindes_file)

        left_layout.addWidget(self.file_browser)
        splitter.addWidget(left_panel)

        # 右侧面板
        right_panel = QWidget() 
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(2, 0, 5, 5) 
        right_layout.setSpacing(0)  # 可选：控件间距

        self.tab_widget = QTabWidget()
        right_layout.addWidget(self.tab_widget)  # 将 tab widget 放入布局

        splitter.addWidget(right_panel) 
        self.create_tabs()

        splitter.setSizes([200, 1000])
        main_layout.addWidget(splitter)

    def on_path_edited(self, new_path: str):
        self.file_browser.set_current_path(new_path)

    def on_folder_double_clicked(self, folder_path: str):
        self.file_browser.set_current_path(folder_path)

    def load_mindes_file(self, file_path: str):
        if file_path.endswith('.mindes'):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # 通知 BuildSimulationWidget 加载文件
                if self.build_widget:
                    self.build_widget.set_mindes_content(file_path, content)
                    # 通知 Log&Stat widget
                    self.log_stat_widget.set_project_path(file_path)
                    # 切换到 Build Simulation 标签页
                    self.tab_widget.setCurrentIndex(0)
            except Exception as e:
                QMessageBox.critical(self, "Load Error", f"Failed to load .mindes file:\n{str(e)}")

    def create_menu_bar(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")

        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = menubar.addMenu("About")
        about_action = QAction("About MInDes", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        custom_solver_action = QAction("How to add custom solvers", self)
        custom_solver_action.triggered.connect(self.show_custom_solver_help)
        help_menu.addAction(custom_solver_action)

    def create_tabs(self):
        self.build_widget = BuildSimulationWidget()
        self.tab_widget.addTab(self.build_widget, "Build Simulation")

        self.log_stat_widget = LogStatisticsWidget()
        # 将 Log&Stat 的状态信号转发给 build_widget 的状态栏
        self.log_stat_widget.statusMessage.connect(self.route_log_stat_status)
        self.tab_widget.addTab(self.log_stat_widget, "Log && Statistic")

        self.vts_viewer = VTSViewerWidget()
        self.tab_widget.addTab(self.vts_viewer, "VTS Data Viewer")

    def route_log_stat_status(self, message: str, level: str):
        """
        将 (message, level) 转换为 update_status(error=..., warning=...) 形式
        """
        kwargs = {
            'error': level == "error",
            'warning': level == "warning",
            'success': level == "success",
            'info': level in ("info", "")  # 默认 info 
        }
        self.build_widget.update_status(message, **kwargs)

    def show_about(self):
        QMessageBox.about(
            self,
            "About MInDes",
            "MInDes - Microstructure Intelligent Design\nVersion: 0.5\nCopyright © Qi Huang\nHome: https://github.com/hq5088028\nEmail: qihuang0908@163.com"
        )

    def show_custom_solver_help(self):
        """显示自定义求解器帮助信息"""
        help_text = (
            "How to add custom solvers:\n\n"
            "MInDes-UI/\n"
            "├── solver/\n"
            "│   ├── Solver_v1.0/\n"
            "│   │   └── MInDes.exe\n"
            "│   │   └── ...\n"
            "│   └── Solver_v2.0/\n"
            "│   │   └── MInDes.exe\n"
            "│   │   └── ...\n"
            "│   └── Custom Solver/\n"
            "│   │   └── MInDes.exe\n"
            "│   │   └── ...\n"
            "│   └── .../\n"
            "└── MInDes-UI.py\n"
            "└── ..."
        )
        QMessageBox.information(self, "Custom Solver Guide", help_text)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())