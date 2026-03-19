# MInDes-UI.py
import sys, os, subprocess
os.environ["QT_API"] = "pyside6"
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QMessageBox, QDialog, QLabel, QPushButton, QSplashScreen
)
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QAction, QCloseEvent, QFont, QPixmap, QIcon

# 导入组件
from file_browser_widget import FileBrowserWidget
from build_simulation_widget import BuildSimulationWidget  
# 按需导入
# from log_statistics_widget import LogStatisticsWidget
# from vts_viewer_widget import VTSViewerWidget

def resource_path(relative_path):
    """获取应用图标，兼容开发和 PyInstaller 打包"""
    try:
        # PyInstaller 运行时
        base_path = sys._MEIPASS
    except AttributeError:
        # 正常 Python 运行
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def get_app_icon():
    icon_path = resource_path(os.path.join('icon', 'mid.ico'))
    if os.path.exists(icon_path):
        return QIcon(icon_path)
    else:
        # fallback（可选）
        print(f"⚠️ Icon not found: {icon_path}")
        return QIcon()

def make_splash():
    pixmap = QPixmap(420, 220)
    pixmap.fill(Qt.white)
    splash = QSplashScreen(pixmap)
    splash.setWindowFlag(Qt.WindowStaysOnTopHint)
    splash.showMessage(
        "Starting MInDes...\nLoading UI shell...",
        Qt.AlignLeft | Qt.AlignBottom,
        Qt.black,
    )
    return splash

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
        logo_path = resource_path(os.path.join('icon', 'logo.png'))
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
        self.log_stat_widget = None
        self.vts_viewer = None
        self.log_placeholder = None
        self.vts_placeholder = None
        self.log_tab_index = -1
        self.vts_tab_index = -1

        self.settings = QSettings("MInDes", "MInDes-UI")
        last_dir = self.settings.value("last_directory", "", type=str)
        self.last_dir = Path(last_dir) if last_dir else None
        
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
        self.file_browser.set_current_path(
            str(self.last_dir) if self.last_dir and self.last_dir.is_dir() else self.file_browser.default_path
        )
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
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        right_layout.addWidget(self.tab_widget)  # 将 tab widget 放入布局

        splitter.addWidget(right_panel)
        self.create_tabs()

        splitter.setSizes([200, 1000])
        main_layout.addWidget(splitter)

    def on_load_vts_folder_requested(self, folder_path: str):
        """切换到 VTS 页面并加载指定文件夹"""
        self.ensure_vts_tab_loaded()
        self.tab_widget.setCurrentIndex(self.vts_tab_index)
        self.vts_viewer.load_vts(folder_path)

    def on_path_edited(self, new_path: str):
        self.file_browser.set_current_path(new_path)

    def on_folder_double_clicked(self, folder_path: str):
        self.file_browser.set_current_path(folder_path)

    def handle_open_path(self, selected_path: str):
        """统一处理 File->Open 选择结果，自动识别文件夹或 .mindes 文件"""
        if not selected_path:
            return

        selected_path = os.path.normpath(selected_path)

        if os.path.isdir(selected_path):
            self.file_browser.set_current_path(selected_path)
            return

        if os.path.isfile(selected_path) and selected_path.lower().endswith(".mindes"):
            self.load_mindes_file(selected_path)
            return

        QMessageBox.warning(
            self,
            "Unsupported Path",
            "Please select a project folder or a .mindes file."
        )

    def load_mindes_file(self, file_path: str):
        if file_path.endswith('.mindes'):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # 同步左侧文件浏览器到该文件所在目录
                parent_dir = os.path.dirname(file_path)
                if parent_dir and os.path.isdir(parent_dir):
                    self.file_browser.set_current_path(parent_dir)
                
                # 通知 BuildSimulationWidget 加载文件
                if self.build_widget:
                    self.build_widget.set_mindes_content(file_path, content)
                    # 切换到 Build Simulation 标签页
                    self.tab_widget.setCurrentIndex(0)
            except Exception as e:
                QMessageBox.critical(self, "Load Error", f"Failed to load .mindes file:\n{str(e)}")

    def load_log_statistic_file(self, folder_path: str):
        """切换到 LOG 页面并加载指定文件"""
        self.ensure_log_tab_loaded()
        self.tab_widget.setCurrentIndex(self.log_tab_index)
        self.log_stat_widget.set_project_path(folder_path)

    def open_project_or_file(self):
        """通过一个对话框打开项目文件夹或 .mindes 文件"""
        dialog = QFileDialog(self, "Open ...")
        dialog.setOption(QFileDialog.DontUseNativeDialog, False)
        dialog.setFileMode(QFileDialog.AnyFile)
        dialog.setNameFilter("MInDes Project (*.mindes);;All Files (*)")

        if self.last_dir and self.last_dir.exists():
            dialog.setDirectory(str(self.last_dir))
        elif self.file_browser and self.file_browser.current_path:
            dialog.setDirectory(self.file_browser.current_path)

        if dialog.exec():
            selected_files = dialog.selectedFiles()
            if selected_files:
                self.handle_open_path(selected_files[0])

    def create_menu_bar(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")

        open_action = QAction("Open...", self)
        open_action.triggered.connect(self.open_project_or_file)

        file_menu.addAction(open_action)
        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = menubar.addMenu("About")
        about_action = QAction("About MInDes", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        self.license_menu = help_menu.addMenu("License")
        help_menu.aboutToShow.connect(self.refresh_license_menu)
        custom_solver_action = QAction("How to add custom solvers", self)
        custom_solver_action.triggered.connect(self.show_custom_solver_help)
        help_menu.addAction(custom_solver_action)

    def show_about(self):
        """当用户选择 "About MInDes" 菜单项时调用"""
        about_dialog = AboutDialog(self)  # 实例化 AboutDialog
        about_dialog.exec()  # 显示关于对话框

    def refresh_license_menu(self):
        self.license_menu.clear()

        if not self.build_widget:
            action = QAction("Build widget not ready", self)
            action.setEnabled(False)
            self.license_menu.addAction(action)
            return

        combo = self.build_widget.solver_combo
        if combo is None or combo.count() == 0:
            action = QAction("No solver available", self)
            action.setEnabled(False)
            self.license_menu.addAction(action)
            return

        for i in range(combo.count()):
            solver_name = combo.itemText(i)
            solver_path = combo.itemData(i)

            if not solver_path:
                continue

            action = QAction(solver_name, self)
            action.triggered.connect(
                lambda checked=False, path=solver_path, name=solver_name:
                    self.launch_solver_console(path, name)
            )
            self.license_menu.addAction(action)

    def launch_solver_console(self, solver_path: str, solver_name: str):
        if not solver_path or not os.path.exists(solver_path):
            QMessageBox.warning(
                self,
                "Solver Not Found",
                f"Solver executable not found:\n{solver_path}"
            )
            return
    
        try:
            cwd = os.path.dirname(solver_path)
    
            if sys.platform == "win32":
                subprocess.Popen(
                    [solver_path],
                    cwd=cwd,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                subprocess.Popen([solver_path], cwd=cwd)
    
            if self.build_widget:
                self.build_widget.update_status(
                    f"Opened solver console: {solver_name}",
                    success=True
                )
    
        except Exception as e:
            QMessageBox.critical(
                self,
                "Launch Error",
                f"Failed to launch solver console:\n{e}"
            )

    def _make_lazy_placeholder(self, text: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        return widget

    def ensure_log_tab_loaded(self):
        if self.log_stat_widget is not None:
            return

        from log_statistics_widget import LogStatisticsWidget
        self.log_stat_widget = LogStatisticsWidget()
        self.log_stat_widget.statusMessage.connect(self.route_log_stat_status)
        self.tab_widget.removeTab(self.log_tab_index)
        self.tab_widget.insertTab(self.log_tab_index, self.log_stat_widget, "Log && Statistic")

    def ensure_vts_tab_loaded(self):
        if self.vts_viewer is not None:
            return

        from vts_viewer_widget import VTSViewerWidget
        self.vts_viewer = VTSViewerWidget()
        self.tab_widget.removeTab(self.vts_tab_index)
        self.tab_widget.insertTab(self.vts_tab_index, self.vts_viewer, "VTS Data Viewer")

    def on_tab_changed(self, index: int):
        if index == self.log_tab_index:
            self.ensure_log_tab_loaded()
            self.tab_widget.setCurrentIndex(self.log_tab_index)
        elif index == self.vts_tab_index:
            self.ensure_vts_tab_loaded()
            self.tab_widget.setCurrentIndex(self.vts_tab_index)

    def create_tabs(self):
        self.build_widget = BuildSimulationWidget()
        self.tab_widget.addTab(self.build_widget, "Build Simulation")
        self.log_placeholder = self._make_lazy_placeholder("Log && Statistic will load on first open.")
        self.log_tab_index = self.tab_widget.addTab(self.log_placeholder, "Log && Statistic")
        self.vts_placeholder = self._make_lazy_placeholder("VTS Data Viewer will load on first open.")
        self.vts_tab_index = self.tab_widget.addTab(self.vts_placeholder, "VTS Data Viewer")

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
            "└── MInDes-UI.exe\n"
            "└── ..."
        )
        QMessageBox.information(self, "Custom Solver Guide", help_text)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.settings.setValue("last_directory", self.file_browser.current_path)
        
        if self.build_widget and self.build_widget.is_running:
            reply = QMessageBox.question(
                self,
                "Solver Running",
                "A solver is still running. Stop it and exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return

            stopped_cleanly = self.build_widget.shutdown_solver(timeout_ms=5000)
            if not stopped_cleanly:
                QMessageBox.warning(
                    self,
                    "Exit Warning",
                    "Solver did not stop cleanly. The application will still close."
                )

        return super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)

    splash = make_splash()
    splash.show()
    app.processEvents()

    splash.showMessage("Starting MInDes...\nLoading main window...", Qt.AlignLeft | Qt.AlignBottom, Qt.black)
    app.processEvents()
    window = MainWindow()

    splash.showMessage("Starting MInDes...\nPreparing tabs...", Qt.AlignLeft | Qt.AlignBottom, Qt.black)
    app.processEvents()
    window.show()

    splash.finish(window)
    sys.exit(app.exec())