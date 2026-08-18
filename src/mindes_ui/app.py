# MInDes-UI.py
from __future__ import annotations

import sys
import os
import subprocess
from functools import partial
from pathlib import Path
from typing import Callable, cast

os.environ["QT_API"] = "pyside6"
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTabWidget,
    QMessageBox,
    QDialog,
    QLabel,
    QPushButton,
    QSplashScreen,
    QSpinBox,
    QWidgetAction,
)
from PySide6.QtCore import Qt, QSettings, QTimer, QProcess
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QFont,
    QPixmap,
    QIcon,
    QGuiApplication,
)

from .i18n import (
    LANGUAGE_SPECS,
    active_language,
    initialize as initialize_i18n,
    preferred_language,
    set_preferred_language,
    tr,
)


def resource_path(relative_path: str) -> str:
    """获取应用图标，兼容开发和 PyInstaller 打包"""
    try:
        # PyInstaller 运行时
        base_path: str = getattr(sys, "_MEIPASS", "")
        if not base_path:
            raise AttributeError
    except AttributeError:
        # 正常 Python 运行
        base_path = str(Path(__file__).resolve().parents[2])
    return os.path.join(base_path, relative_path)


def get_app_icon() -> QIcon:
    icon_path = resource_path(os.path.join("icon", "mid.ico"))
    if os.path.exists(icon_path):
        return QIcon(icon_path)
    else:
        # fallback（可选）
        print(f"⚠️ Icon not found: {icon_path}")
        return QIcon()


def make_splash() -> QSplashScreen:
    splash_path = resource_path(os.path.join("icon", "splash.png"))
    pixmap = QPixmap(splash_path)
    splash = QSplashScreen(pixmap)
    _progress_lines = [tr("startup.starting")]
    setattr(splash, "_progress_lines", _progress_lines)
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    splash.showMessage(
        "\n".join(_progress_lines),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
        Qt.GlobalColor.black,
    )
    return splash


def update_splash_progress(
    splash: QSplashScreen, current: int, total: int, detail: str
) -> None:
    percent = int(current * 100 / total)
    line = tr(
        "startup.progress",
        current=current,
        total=total,
        detail=detail,
        percent=percent,
    )

    _progress_lines: list[str] = getattr(
        splash, "_progress_lines", [tr("startup.starting")]
    )
    if not _progress_lines or _progress_lines[-1] != line:
        _progress_lines.append(line)
    setattr(splash, "_progress_lines", _progress_lines)

    max_visible_lines = 6
    visible_lines = _progress_lines[-max_visible_lines:]

    splash.showMessage(
        "\n".join(visible_lines),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
        Qt.GlobalColor.black,
    )
    QApplication.processEvents()


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("about.title"))
        self.setFixedSize(400, 450)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 使用图标（无外部依赖）
        logo_label = QLabel()
        logo_path = resource_path(os.path.join("icon", "logo.png"))
        pixmap = QPixmap(logo_path).scaled(
            256,
            173,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        logo_label.setPixmap(pixmap)
        logo_label.setFixedSize(300, 200)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # --- 标题 ---
        title_label = QLabel(tr("app.product_name"))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))

        # --- 版本和版权信息（多行居中）---
        info_text = "\n".join(
            (tr("about.version", version="1.0"), tr("about.copyright_owner"))
        )
        info_label = QLabel(info_text)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setFont(QFont("Arial", 10))

        # --- 链接（可点击）---
        home_text = tr("about.links")
        home_label = QLabel(home_text)
        home_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        home_label.setOpenExternalLinks(True)  # 允许点击跳转

        # --- 邮箱 ---
        email_label = QLabel(tr("about.email_link"))
        email_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        email_label.setOpenExternalLinks(True)

        # --- 关闭按钮 ---
        button_layout = QHBoxLayout()
        close_btn = QPushButton(tr("common.close"))
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

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
    _tool_windows: list[QDialog]
    startup_progress: Callable[[int, int, str], None] | None

    def __init__(
        self, startup_progress: Callable[[int, int, str], None] | None = None
    ) -> None:
        super().__init__()
        self.startup_progress = startup_progress
        self.setWindowTitle(tr("app.title"))
        screen = QGuiApplication.primaryScreen().availableGeometry()
        w = int(screen.width() * 0.8)
        h = int(screen.height() * 0.8)
        x = screen.x() + (screen.width() - w) // 2
        y = screen.y() + (screen.height() - h) // 2
        self.setGeometry(x, y, w, h)
        self.setWindowIcon(get_app_icon())
        self.current_project_path = None
        self.build_widget = None
        self.log_stat_widget = None
        self.vts_viewer = None
        self.log_placeholder = None
        self.vts_placeholder = None
        self.log_tab_index = -1
        self.vts_tab_index = -1
        self._restart_requested = False

        self.settings = QSettings("MInDes", "MInDes-UI")
        last_dir = self.settings.value("last_directory", "", type=str)
        self.last_dir = Path(str(last_dir)) if last_dir else None

        def _load_font_scale(key: str) -> int:
            FONT_SCALE_MIN = 20
            FONT_SCALE_MAX = 300
            FONT_SCALE_DEFAULT = 100
            value = self.settings.value(
                f"font_scale/{key}", FONT_SCALE_DEFAULT, type=int
            )
            return max(FONT_SCALE_MIN, min(FONT_SCALE_MAX, cast(int, value)))

        self.font_scales = {
            key: _load_font_scale(key)
            for key in ("navigation", "edit", "debug", "log", "statistic")
        }
        self.font_scale_spins = {}

        self.setup_ui()

    def _remove_tool_window(
        self, dialog: QDialog, _destroyed_obj: object | None = None
    ) -> None:
        """Remove a tool dialog from the tracking list when it is destroyed."""
        if dialog in self._tool_windows:
            self._tool_windows.remove(dialog)

    def report_startup_progress(self, current: int, total: int, text: str) -> None:
        if self.startup_progress:
            self.startup_progress(current, total, text)

    def setup_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setOpaqueResize(False)

        # 左侧面板
        left_panel = QWidget()
        left_panel.setMinimumWidth(200)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 0, 2, 5)

        self.create_menu_bar()

        from .file_browser_widget import FileBrowserWidget

        self.file_browser = FileBrowserWidget()
        self.file_browser.set_current_path(
            str(self.last_dir)
            if self.last_dir and self.last_dir.is_dir()
            else self.file_browser.default_path
        )
        self.file_browser.pathEdited.connect(self.on_path_edited)
        self.file_browser.loadVtsFolderRequested.connect(
            self.on_load_vts_folder_requested
        )
        self.file_browser.loadLogStatisticFolderRequested.connect(
            self.load_log_statistic_file
        )
        self.file_browser.folderDoubleClicked.connect(self.on_folder_double_clicked)
        self.file_browser.fileDoubleClicked.connect(self.load_mindes_file)

        left_layout.addWidget(self.file_browser)
        splitter.addWidget(left_panel)

        # 右侧面板
        right_panel = QWidget()
        right_panel.setMinimumWidth(200)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(2, 0, 5, 5)
        right_layout.setSpacing(0)  # 可选：控件间距

        self.tab_widget = QTabWidget()
        right_layout.addWidget(self.tab_widget)  # 将 tab widget 放入布局
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        splitter.addWidget(right_panel)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        self.create_tabs()

        splitter.setSizes([200, 1000])
        main_layout.addWidget(splitter)

    def on_load_vts_folder_requested(self, folder_path: str):
        """切换到 VTS 页面并加载指定文件夹"""
        # 切换到 VTS 页面
        self.tab_widget.setCurrentIndex(self.vts_tab_index)
        # 加载文件夹
        if self.vts_viewer is not None:
            self.vts_viewer.load_vts(folder_path)
        else:
            print("vts_viewer is not exist!")
            return

    def on_tab_changed(self, index: int) -> None:
        if index == self.vts_tab_index and self.vts_viewer is not None:
            self.vts_viewer.schedule_render_refresh()
            QTimer.singleShot(0, self.vts_viewer.activate_pending_vts_load)

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
            tr("dialog.unsupported_path.title"),
            tr("dialog.unsupported_path.body"),
        )

    def load_mindes_file(self, file_path: str):
        if file_path.endswith(".mindes"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
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
                QMessageBox.critical(
                    self,
                    tr("dialog.load_error.title"),
                    tr("dialog.load_mindes_failed", error=e),
                )

    def load_log_statistic_file(self, folder_path: str):
        """切换到 LOG 页面并加载指定文件"""
        self.tab_widget.setCurrentIndex(self.log_tab_index)
        if self.log_stat_widget is not None:
            self.log_stat_widget.set_project_path(folder_path)
        else:
            print("log_stat_widget is None")
            return

    def prepare_output_targets(self, folder_path: str) -> None:
        if self.log_stat_widget is not None:
            self.log_stat_widget.set_project_path(folder_path)
        if self.vts_viewer is not None:
            self.vts_viewer.prepare_vts_folder(folder_path)

    def open_project_or_file(self):
        """通过一个对话框打开项目文件夹或 .mindes 文件"""
        dialog = QFileDialog(self, tr("dialog.open.title"))
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setNameFilter(tr("dialog.filter.mindes"))
        if self.last_dir and self.last_dir.exists():
            dialog.setDirectory(str(self.last_dir))
        elif self.file_browser and self.file_browser.current_path:
            dialog.setDirectory(self.file_browser.current_path)
        if dialog.exec():
            selected_files = dialog.selectedFiles()
            if selected_files:
                self.handle_open_path(selected_files[0])

    def open_project_folder(self):
        """通过对话框打开文件夹到导航栏"""
        dialog = QFileDialog(self, tr("dialog.open_folder.title"))
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        if self.last_dir and self.last_dir.exists():
            dialog.setDirectory(str(self.last_dir))
        elif self.file_browser and self.file_browser.current_path:
            dialog.setDirectory(self.file_browser.current_path)
        if dialog.exec():
            selected_folder = dialog.selectedFiles()
            if selected_folder:
                self.handle_open_path(selected_folder[0])

    def create_menu_bar(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu(tr("menu.file"))

        # Open file or folder
        open_action = QAction(tr("menu.file.open"), self)
        open_action.triggered.connect(self.open_project_or_file)
        file_menu.addAction(open_action)

        open_folder_action = QAction(tr("menu.file.open_folder"), self)
        open_folder_action.triggered.connect(self.open_project_folder)
        file_menu.addAction(open_folder_action)

        # Add seperator
        file_menu.addSeparator()

        # Exit
        exit_action = QAction(tr("menu.file.exit"), self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # --- Tools menu (inserted between File and About) ---
        tools_menu = menubar.addMenu(tr("menu.tools"))
        csv_plotter_action = QAction(tr("menu.tools.csv_plotter"), self)
        csv_plotter_action.triggered.connect(self.open_csv_plotter)
        tools_menu.addAction(csv_plotter_action)
        vts_plotter_action = QAction(tr("menu.tools.vts_plotter"), self)
        vts_plotter_action.triggered.connect(self.open_vts_plotter)
        tools_menu.addAction(vts_plotter_action)

        thermo_calc_menu = tools_menu.addMenu(tr("menu.tools.thermo_calc"))

        common_tangent_menu = thermo_calc_menu.addMenu(tr("menu.tools.common_tangent"))
        phase2_comp3_action = QAction(tr("menu.tools.phase2_comp3"), self)
        phase2_comp3_action.triggered.connect(self.open_common_tangent_phase2_comp3)
        common_tangent_menu.addAction(phase2_comp3_action)

        fitting_menu = thermo_calc_menu.addMenu(tr("menu.tools.fitting"))
        comp3_action = QAction(tr("menu.tools.comp3"), self)
        comp3_action.triggered.connect(self.open_fitting_comp3)
        fitting_menu.addAction(comp3_action)

        view_menu = menubar.addMenu(tr("menu.view"))
        font_size_menu = view_menu.addMenu(tr("menu.view.font_size"))
        font_targets = (
            ("navigation", tr("font.navigation")),
            ("edit", tr("font.edit")),
            ("debug", tr("font.debug")),
            ("log", tr("font.log")),
            ("statistic", tr("font.statistic")),
        )
        for key, label_text in font_targets:
            row = QWidget(font_size_menu)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 2, 8, 2)
            label = QLabel(label_text, row)
            spin = QSpinBox(row)
            spin.setRange(20, 300)
            spin.setSingleStep(10)
            spin.setSuffix("%")
            spin.setValue(self.font_scales[key])
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(
                lambda value, target=key: self.set_font_scale(target, value)
            )
            row_layout.addWidget(label)
            row_layout.addStretch()
            row_layout.addWidget(spin)
            widget_action = QWidgetAction(font_size_menu)
            widget_action.setDefaultWidget(row)
            font_size_menu.addAction(widget_action)
            self.font_scale_spins[key] = spin

        language_menu = view_menu.addMenu(tr("menu.view.language"))
        self.language_action_group = QActionGroup(self)
        self.language_action_group.setExclusive(True)
        pending_language = preferred_language()
        for spec in LANGUAGE_SPECS:
            language = spec.code
            action = QAction(spec.native_name, self)
            action.setCheckable(True)
            action.setData(language)
            action.setChecked(language == pending_language)
            action.triggered.connect(
                lambda _checked=False, code=language: self.request_language(code)
            )
            self.language_action_group.addAction(action)
            language_menu.addAction(action)

        help_menu = menubar.addMenu(tr("menu.about"))
        about_action = QAction(tr("menu.about.app"), self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        self.license_menu = help_menu.addMenu(tr("menu.about.license"))
        help_menu.aboutToShow.connect(self.refresh_license_menu)
        custom_solver_action = QAction(tr("menu.about.custom_solver"), self)
        custom_solver_action.triggered.connect(self.show_custom_solver_help)
        help_menu.addAction(custom_solver_action)

    def request_language(self, language: str) -> None:
        set_preferred_language(language)
        if language == active_language():
            return

        reply = QMessageBox.question(
            self,
            tr("language.restart.title"),
            tr("language.restart.question"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            if self.build_widget is not None:
                self.build_widget.update_status(tr("language.restart.later"), info=True)
            return

        reasons: list[str] = []
        if self.build_widget is not None:
            if self.build_widget.is_running:
                reasons.append(tr("language.blocker.solver"))
            if self.build_widget.has_unsaved_changes():
                reasons.append(tr("language.blocker.unsaved"))
        if getattr(self, "_tool_windows", []):
            reasons.append(tr("language.blocker.tools"))
        if reasons:
            QMessageBox.warning(
                self,
                tr("language.restart.blocked.title"),
                tr("language.restart.blocked", reasons="\n".join(reasons)),
            )
            return

        self._restart_requested = True
        if not self.close():
            self._restart_requested = False

    @property
    def restart_requested(self) -> bool:
        return self._restart_requested

    def show_about(self) -> None:
        """当用户选择 "About MInDes" 菜单项时调用"""
        about_dialog = AboutDialog(self)  # 实例化 AboutDialog
        about_dialog.exec()  # 显示关于对话框

    def open_csv_plotter(self) -> None:
        """Open the standalone multi-file CSV plotting tool."""
        try:
            from .tools.csv_plotter.csv_plotter_gui import CSVPlotterDialog

            dialog = CSVPlotterDialog(parent=self)
            dialog.setWindowIcon(get_app_icon())
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            dialog.show()
            if not hasattr(self, "_tool_windows"):
                self._tool_windows = []
            self._tool_windows.append(dialog)
            dialog.destroyed.connect(partial(self._remove_tool_window, dialog))
        except Exception as exc:
            QMessageBox.critical(
                self,
                tr("dialog.launch_error.title"),
                tr("status.launch_tool_failed", tool="CSV Plotter", error=exc),
            )

    def open_vts_plotter(self) -> None:
        """Open the standalone multi-file VTS plotting tool."""
        try:
            from .tools.vts_plotter.vts_plotter_gui import VTSPlotterDialog

            dialog = VTSPlotterDialog(parent=self)
            dialog.setWindowIcon(get_app_icon())
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            dialog.show()
            if not hasattr(self, "_tool_windows"):
                self._tool_windows = []
            self._tool_windows.append(dialog)
            dialog.destroyed.connect(partial(self._remove_tool_window, dialog))
        except Exception as exc:
            QMessageBox.critical(
                self,
                tr("dialog.launch_error.title"),
                tr("status.launch_tool_failed", tool="VTS Plotter", error=exc),
            )

    def open_common_tangent_phase2_comp3(self) -> None:
        """打开 CommonTangent Phase2Comp3 子对话框 (非模态, 不阻塞主界面)."""
        try:
            from .tools.common_tangent.common_tangent_o3_gui import (
                CommonTangentDialog,
                Ga_default,
                Gb_default,
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("dialog.import_error.title"),
                tr("status.import_tool_failed", tool="Common Tangent", error=e),
            )
            return
        try:
            dlg = CommonTangentDialog(Ga_default, Gb_default, parent=self, n_init=60)
            dlg.setWindowIcon(get_app_icon())
            dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            dlg.show()  # 非模态
            if not hasattr(self, "_tool_windows"):
                self._tool_windows = []
            self._tool_windows.append(dlg)
            dlg.destroyed.connect(partial(self._remove_tool_window, dlg))
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("dialog.launch_error.title"),
                tr("status.launch_tool_failed", tool="Common Tangent", error=e),
            )

    def open_fitting_comp3(self) -> None:
        """打开 Fitting Comp3 子对话框 (非模态, 不阻塞主界面)."""
        try:
            from .tools.fitting.gibbs_fitter_gui import FitterDialog
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("dialog.import_error.title"),
                tr("status.import_tool_failed", tool="Fitting", error=e),
            )
            return
        try:
            dlg = FitterDialog(parent=self)
            dlg.setWindowIcon(get_app_icon())
            dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            dlg.show()
            if not hasattr(self, "_tool_windows"):
                self._tool_windows = []
            self._tool_windows.append(dlg)
            dlg.destroyed.connect(partial(self._remove_tool_window, dlg))
        except Exception as e:
            QMessageBox.critical(
                self,
                tr("dialog.launch_error.title"),
                tr("status.launch_tool_failed", tool="Fitting", error=e),
            )

    def refresh_license_menu(self) -> None:
        self.license_menu.clear()

        if not self.build_widget:
            action = QAction(tr("license.build_not_ready"), self)
            action.setEnabled(False)
            self.license_menu.addAction(action)
            return

        combo = self.build_widget.solver_combo
        if combo.count() == 0:
            action = QAction(tr("license.no_solver"), self)
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
                lambda checked=False, path=solver_path, name=solver_name: (
                    self.launch_solver_console(path, name)
                )
            )
            self.license_menu.addAction(action)

    def launch_solver_console(self, solver_path: str, solver_name: str) -> None:
        if not solver_path or not os.path.exists(solver_path):
            QMessageBox.warning(
                self,
                tr("dialog.solver_not_found.title"),
                tr("dialog.solver_not_found.body", path=solver_path),
            )
            return

        try:
            cwd = os.path.dirname(solver_path)

            if sys.platform == "win32":
                subprocess.Popen(
                    [solver_path], cwd=cwd, creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                subprocess.Popen([solver_path], cwd=cwd)

            if self.build_widget:
                self.build_widget.update_status(
                    tr("status.solver_console_opened", name=solver_name), success=True
                )

        except Exception as e:
            QMessageBox.critical(
                self,
                tr("dialog.launch_error.title"),
                tr("status.launch_tool_failed", tool="solver console", error=e),
            )

    def create_tabs(self) -> None:
        self.report_startup_progress(2, 5, tr("startup.build"))
        from .build_simulation_widget import BuildSimulationWidget

        self.build_widget = BuildSimulationWidget()
        self.build_widget.outputProjectPathPrepared.connect(self.prepare_output_targets)
        self.build_widget.simulationFinished.connect(self.prepare_output_targets)
        self.tab_widget.addTab(self.build_widget, tr("tab.build"))

        self.report_startup_progress(3, 5, tr("startup.log"))
        from .log_statistics_widget import LogStatisticsWidget

        self.log_stat_widget = LogStatisticsWidget()
        self.log_stat_widget.statusMessage.connect(self.route_log_stat_status)
        self.log_tab_index = self.tab_widget.addTab(
            self.log_stat_widget, tr("tab.log_stat")
        )

        self.report_startup_progress(4, 5, tr("startup.vts"))
        from .vts_viewer_widget import VTSViewerWidget

        self.vts_viewer = VTSViewerWidget()
        self.vts_tab_index = self.tab_widget.addTab(
            self.vts_viewer, tr("tab.vts_viewer")
        )
        self.apply_font_scales()

    def set_font_scale(self, target: str, percent: int):
        percent = max(20, min(300, int(percent)))
        self.font_scales[target] = percent
        self.settings.setValue(f"font_scale/{target}", percent)
        self.apply_font_scales()

    def apply_font_scales(self):
        if getattr(self, "file_browser", None) is not None:
            self.file_browser.set_navigation_font_scale(self.font_scales["navigation"])
        if self.build_widget is not None:
            self.build_widget.set_editor_font_scales(
                edit_percent=self.font_scales["edit"],
                debug_percent=self.font_scales["debug"],
            )
        if self.log_stat_widget is not None:
            self.log_stat_widget.set_text_font_scales(
                log_percent=self.font_scales["log"],
                statistic_percent=self.font_scales["statistic"],
            )

    def route_log_stat_status(self, message: str, level: str) -> None:
        """
        将 (message, level) 转换为 update_status(error=..., warning=...) 形式
        """
        kwargs = {
            "error": level == "error",
            "warning": level == "warning",
            "success": level == "success",
            "info": level in ("info", ""),  # 默认 info
        }
        if self.build_widget is not None:
            self.build_widget.update_status(message, **kwargs)
        else:
            print("self.build_widget is None!")
            return

    def show_custom_solver_help(self) -> None:
        """显示自定义求解器帮助信息"""
        QMessageBox.information(
            self, tr("solver_guide.title"), tr("solver_guide.body")
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        self.settings.setValue("last_directory", self.file_browser.current_path)

        if self.build_widget and self.build_widget.is_running:
            reply = QMessageBox.question(
                self,
                tr("dialog.solver_running.title"),
                tr("dialog.solver_running.body"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

            stopped_cleanly = self.build_widget.shutdown_solver(timeout_ms=5000)
            if not stopped_cleanly:
                QMessageBox.warning(
                    self,
                    tr("dialog.exit_warning.title"),
                    tr("dialog.exit_warning.body"),
                )

        return super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
    app = QApplication(argv)
    initialize_i18n(app)

    splash = make_splash()
    splash.show()
    app.processEvents()

    def startup_progress(current: int, total: int, text: str) -> None:
        update_splash_progress(splash, current, total, text)

    startup_progress(1, 5, tr("startup.main_window"))
    window = MainWindow(startup_progress=startup_progress)

    startup_progress(5, 5, tr("startup.complete"))
    window.show()

    # 启动后自动打开命令行传入的 .mindes / 文件夹
    def open_startup_target() -> None:
        if len(argv) > 1:
            startup_path = argv[1].strip().strip('"')
            if startup_path:
                window.handle_open_path(startup_path)

    def finish_startup():
        splash.finish(window)
        window.showNormal()
        window.raise_()
        window.activateWindow()

    QTimer.singleShot(0, open_startup_target)
    QTimer.singleShot(500, finish_startup)
    exit_code = app.exec()
    if window.restart_requested:
        if getattr(sys, "frozen", False):
            QProcess.startDetached(
                sys.executable, argv[1:], os.getcwd()
            )
        else:
            QProcess.startDetached(
                sys.executable, ["-m", "mindes_ui", *argv[1:]], os.getcwd()
            )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
