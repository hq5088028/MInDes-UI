# MInDes-UI.py
import sys, os
os.environ["QT_API"] = "pyside6"
import matplotlib
matplotlib.use("QtAgg")
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QMessageBox, QDialog, QLabel, QPushButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QPixmap, QIcon

# 导入组件
from vts_viewer_widget import VTSViewerWidget
from file_browser_widget import FileBrowserWidget
from build_simulation_widget import BuildSimulationWidget  
from log_statistics_widget import LogStatisticsWidget

script_dir = os.path.dirname(os.path.abspath(__file__))
def get_app_icon():
    """获取应用图标，兼容开发和 PyInstaller 打包"""
    try:
        # PyInstaller 运行时
        base_path = sys._MEIPASS
    except AttributeError:
        # 正常 Python 运行
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    icon_path = os.path.join(base_path, "icon", "mid.ico")
    if os.path.exists(icon_path):
        return QIcon(icon_path)
    else:
        # fallback（可选）
        print(f"⚠️ Icon not found: {icon_path}")
        return QIcon()

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About MInDes")
        self.setFixedSize(400, 450)
        self.setWindowModality(Qt.ApplicationModal)

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        # 使用图标（无外部依赖）
        logo_label = QLabel()
        logo_path = os.path.join(script_dir, "icon", "logo.png")
        pixmap = QPixmap(logo_path).scaled(
            256, 173, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        logo_label.setPixmap(pixmap)
        logo_label.setFixedSize(300, 200)
        logo_label.setAlignment(Qt.AlignCenter)

        # --- 标题 ---
        title_label = QLabel("Microstructure Intelligent Design")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFont(QFont("Arial", 14, QFont.Bold))

        # --- 版本和版权信息（多行居中）---
        info_text = """Version: 0.5
Copyright © Qi Huang"""
        info_label = QLabel(info_text)
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setFont(QFont("Arial", 10))

        # --- 链接（可点击）---
        home_text = """<a href='https://github.com/hq5088028/MInDes-UI' style='color:#0078d7;'>MInDes-UI (GitHub)</a><br>
<a href='https://github.com/Microstructure-Intelligent-Design/MInDes' style='color:#0078d7;'>MInDes-Solver (GitHub)</a>"""
        home_label = QLabel(home_text)
        home_label.setAlignment(Qt.AlignCenter)
        home_label.setOpenExternalLinks(True)  # 允许点击跳转

        # --- 邮箱 ---
        email_label = QLabel("Email: <a href='mailto:qihuang0908@163.com' style='color:#0078d7;'>qihuang0908@163.com</a>")
        email_label.setAlignment(Qt.AlignCenter)
        email_label.setOpenExternalLinks(True)

        # --- 关闭按钮 ---
        button_layout = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        button_layout.setAlignment(Qt.AlignCenter)

        # --- 添加到布局 ---
        layout.addWidget(logo_label)
        layout.addSpacing(10)
        layout.addWidget(title_label)
        layout.addSpacing(5)
        layout.addWidget(info_label)
        layout.addSpacing(10)
        layout.addWidget(home_label)
        layout.addWidget(email_label)
        layout.addSpacing(20)
        layout.addLayout(button_layout)

        self.setLayout(layout)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MInDes - Microstructure Intelligent Design")
        self.resize(1200, 800)
        self.setWindowIcon(get_app_icon())
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
        self.file_browser.loadVtsFolderRequested.connect(self.on_load_vts_folder_requested)
        self.file_browser.loadLogStatisticFolderRequested.connect(self.load_log_statistic_file)
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

    def on_load_vts_folder_requested(self, folder_path: str):
        """切换到 VTS 页面并加载指定文件夹"""
        # 1. 切换到 VTS Viewer 页面（假设你在 QTabWidget 或 QStackedWidget 中）
        # 示例：如果你用 QTabWidget
        self.tab_widget.setCurrentWidget(self.vts_viewer)  # 替换为你的实际引用
        # 2. 调用 VTS Viewer 的 load_vts 并传入路径
        self.vts_viewer.load_vts(folder_path)

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
                    # 切换到 Build Simulation 标签页
                    self.tab_widget.setCurrentIndex(0)
            except Exception as e:
                QMessageBox.critical(self, "Load Error", f"Failed to load .mindes file:\n{str(e)}")

    def load_log_statistic_file(self, folder_path: str):
            """切换到 LOG 页面并加载指定文件"""
            # 1. 切换到 LOG 页面（假设你在 QTabWidget 或 QStackedWidget 中）
            # 示例：如果你用 QTabWidget
            self.tab_widget.setCurrentWidget(self.log_stat_widget)  # 替换为你的实际引用
            # 2. 调用 LOG 的 set_project_path 并传入路径
            self.log_stat_widget.set_project_path(folder_path)

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

    def show_about(self):
        """当用户选择 "About MInDes" 菜单项时调用"""
        about_dialog = AboutDialog(self)  # 实例化 AboutDialog
        about_dialog.exec()  # 显示关于对话框

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