# file_browser_widget.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QFileIconProvider, 
    QLineEdit, QAbstractItemView, QMessageBox, QMenu, QInputDialog
)
from PySide6.QtCore import Qt, Signal, QDir, QFileSystemWatcher, QSettings
import os
import shutil
import subprocess  # 👈 用于跨平台兼容（可选）

# 允许的文件扩展名（小写）
ALLOWED_EXTENSIONS = {'.mindes', '.dat', '.txt', '.vts'}

class FileBrowserWidget(QWidget):
    fileDoubleClicked = Signal(str)
    folderDoubleClicked = Signal(str)
    pathEdited = Signal(str)
    loadVtsFolderRequested = Signal(str)  # 发射一个字符串（文件夹路径）
    loadLogStatisticFolderRequested = Signal(str)  # 发射一个字符串（文件夹路径）

    def __init__(self, parent=None):
        super().__init__(parent)
        # 默认路径设为用户 Documents 文件夹，不存在则为用户主目录
        default_path = os.path.expanduser("~")+os.path.sep+"Documents"
        open_path = default_path if os.path.isdir(default_path) else os.path.expanduser("~")
        self.default_path = open_path
        self.current_path = self.default_path
        # 👇 新增文件系统监听器
        self.watcher = QFileSystemWatcher()
        self.watcher.directoryChanged.connect(self.on_directory_changed)
        #
        self.init_ui()

    def set_current_path(self, path: str):
        if os.path.isdir(path):
            # 先移除旧路径监听（避免内存泄漏）
            if self.watcher.directories():
                self.watcher.removePaths(self.watcher.directories())
            # 添加新路径监听
            self.watcher.addPath(path)
            self.current_path = os.path.normpath(path)
            self.refresh_view()
        else:
            QMessageBox.warning(self, "Invalid path", f"Path does not exist: \n{path}")

    def on_directory_changed(self):
        """当目录被外部修改时自动刷新"""
        # 使用 QTimer.singleShot 避免频繁刷新（防抖）
        from PySide6.QtCore import QTimer
        if not hasattr(self, '_refresh_timer'):
            self._refresh_timer = QTimer()
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.timeout.connect(self.refresh_view)
        self._refresh_timer.start(100)  # 100ms 防抖

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.path_line_edit = QLineEdit()
        self.path_line_edit.setFixedHeight(30)  # 👈 增加高度
        self.path_line_edit.returnPressed.connect(self.on_path_edited)
        layout.addWidget(self.path_line_edit)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        # 禁用双击/F2 自动进入编辑
        self.list_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list_widget.itemChanged.connect(self.on_item_renamed)

        layout.addWidget(self.list_widget)

        self.refresh_view()

    def _is_allowed_file(self, filename: str) -> bool:
        """判断文件是否属于允许的扩展名"""
        _, ext = os.path.splitext(filename)
        return ext.lower() in ALLOWED_EXTENSIONS

    def refresh_view(self):
        self.path_line_edit.setText(self.current_path)
        self.list_widget.clear()

        dir_obj = QDir(self.current_path)
        # 获取系统文件夹图标（一次即可）
        folder_icon = QFileIconProvider().icon(QFileIconProvider.IconType.Folder)

        # 添加 ".."（如果不是根目录）
        if not dir_obj.isRoot():
            up_item = QListWidgetItem("..")
            up_item.setData(Qt.ItemDataRole.UserRole, "parent_dir")
            self.list_widget.addItem(up_item)

        # 获取所有条目（文件夹在前）
        entries = dir_obj.entryInfoList(
            QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot,
            QDir.SortFlag.Name | QDir.SortFlag.DirsFirst
        )

        for entry in entries:
            name = entry.fileName()
            item = QListWidgetItem(name)
            if entry.isDir():
                item = QListWidgetItem(folder_icon, name)
                item.setData(Qt.ItemDataRole.UserRole, "dir")
                self.list_widget.addItem(item)
            else:
                # 👇 只添加允许的文件类型
                if self._is_allowed_file(name):
                    item = QListWidgetItem(name)
                    item.setData(Qt.ItemDataRole.UserRole, "file")
                    self.list_widget.addItem(item)
                # 否则跳过（不显示）
            # 默认不可编辑
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            # 但保存原始名称用于重命名校验
            item._original_name = name

    def on_path_edited(self):
        new_path = self.path_line_edit.text().strip()
        if not new_path:
            return
        # 自动将 "d:" 转为 "d:\"
        if len(new_path) == 2 and new_path[1] == ':' and new_path[0].isalpha():
            new_path += os.sep  # 变成 "d:\"
        if os.path.isdir(new_path):
            normalized = os.path.normpath(new_path)
            self.pathEdited.emit(normalized)
        else:
            QMessageBox.warning(self, "Invalid path", "Please enter a valid folder path.")
            self.path_line_edit.setText(self.current_path)

    def on_item_double_clicked(self, item):
        item_type = item.data(Qt.ItemDataRole.UserRole)
        name = item.text()

        if item_type == "parent_dir":
            parent_path = os.path.dirname(self.current_path)
            self.folderDoubleClicked.emit(parent_path)
        elif item_type == "dir":
            new_path = os.path.join(self.current_path, name)
            self.folderDoubleClicked.emit(new_path)
        elif item_type == "file":
            file_path = os.path.join(self.current_path, name)
            self.fileDoubleClicked.emit(file_path)

    def show_context_menu(self, pos):
        """在空白处或选中项上右键显示菜单"""
        global_pos = self.list_widget.mapToGlobal(pos)
        menu = QMenu()

        # 判断是否点击在空白区域（无选中项）
        clicked_item = self.list_widget.itemAt(pos)
        if clicked_item is None:
            # 空白处：只允许新建
            new_folder_action = menu.addAction("New folder")
            new_mindes_action = menu.addAction("New .mindes file")
            menu.addSeparator()
            open_explorer_action = menu.addAction("Open File Explorer")
            action = menu.exec(global_pos)
            if action == new_folder_action:
                self.create_new_folder()
            elif action == new_mindes_action:
                self.create_new_mindes_file()
            elif action == open_explorer_action:
                self.open_in_explorer()
        else:
            # 点击了某一项：判断类型
            item_type = clicked_item.data(Qt.ItemDataRole.UserRole)
            name = clicked_item.text()
            full_path = os.path.join(self.current_path, name)
            load_action = None
            # 如果是 .mindes 文件，额外添加“加载”选项
            if item_type == "file" and name.lower().endswith('.mindes'):
                load_action = menu.addAction("Build Simulation")
                menu.addSeparator()
            load_vts_action = None
            load_log_statis_action = None
            if os.path.isdir(full_path):
                load_log_statis_action = menu.addAction("Load Log && Statistics Data")
                load_vts_action = menu.addAction("Load VTS Data")
                menu.addSeparator()
            
            # 点击了某一项：复制 + 删除 + 重命名
            copy_action = menu.addAction("Copy")
            rename_action = menu.addAction("Rename")
            delete_action = menu.addAction("Delete")
            action = menu.exec(global_pos)
            if action == copy_action:
                self.copy_selected_items() 
            elif action == rename_action:
                self.start_rename_edit(clicked_item) 
            elif action == delete_action:
                self.delete_selected_items()
            elif action == load_action:
                self.load_mindes_file_temp(os.path.join(self.current_path, name))
            elif load_log_statis_action and action == load_log_statis_action:
                self.loadLogStatisticFolderRequested.emit(full_path)
            elif load_vts_action and action == load_vts_action:
                self.loadVtsFolderRequested.emit(full_path)

    def start_rename_edit(self, item):
        """启动内联重命名编辑模式"""
        # 设置当前项为可编辑（临时）
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        # 开始编辑
        self.list_widget.editItem(item)
        # 编辑结束后会触发 itemChanged

    def load_mindes_file_temp(self, file_path: str):
        """发射信号让主窗口处理 .mindes 文件加载"""
        self.fileDoubleClicked.emit(file_path)  # 直接复用现有信号

    def on_item_renamed(self, item):
        """
        处理重命名结果（仅在右键 Rename 后触发）
        """
        if not hasattr(item, '_original_name'):
            return

        old_name = item._original_name
        new_name = item.text().strip()

        if new_name == old_name:
            return

        if not new_name:
            QMessageBox.warning(self, "Invalid name", "Name cannot be empty.")
            item.setText(old_name)
            return

        invalid_chars = '<>:"/\\|?*'
        if any(c in new_name for c in invalid_chars):
            QMessageBox.critical(self, "Invalid name", f"Name cannot contain: {invalid_chars}")
            item.setText(old_name)
            return

        old_path = os.path.join(self.current_path, old_name)
        new_path = os.path.join(self.current_path, new_name)

        if os.path.exists(new_path):
            QMessageBox.warning(self, "Already exists", f"'{new_name}' already exists.")
            item.setText(old_name)
            return

        try:
            os.rename(old_path, new_path)
            item._original_name = new_name  # 更新原始名
        except Exception as e:
            QMessageBox.critical(self, "Rename failed", f"Cannot rename:\n{e}")
            item.setText(old_name)

    def copy_selected_items(self):
        """复制选中的文件或文件夹，添加 _copy 后缀"""
        items = self.list_widget.selectedItems()
        if not items:
            return
        for item in items:
            old_name = item.text()
            src_path = os.path.join(self.current_path, old_name)
            # 生成目标路径（带 _copy 后缀，自动处理重名）
            dst_path = self._generate_copy_path(src_path)
            try:
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dst_path)
                else:
                    shutil.copy2(src_path, dst_path)  # 保留元数据
            except Exception as e:
                QMessageBox.critical(
                    self, "Copy failed",
                    f"Failed to copy '{old_name}':\n{str(e)}"
                )
                continue
        self.refresh_view()

    def _generate_copy_path(self, original_path: str) -> str:
        """
        生成带 _copy 后缀的新路径，自动处理重名：
        - file.txt → file_copy.txt
        - file_copy.txt → file_copy1.txt
        - folder → folder_copy
        - folder_copy → folder_copy1
        """
        dir_name = os.path.dirname(original_path)
        base_name = os.path.basename(original_path)
        if os.path.isdir(original_path):
            # 文件夹：直接在名字后加 _copy
            name, ext = base_name, ""
        else:
            # 文件：分离名称和扩展名
            name, ext = os.path.splitext(base_name)
        # 尝试基本名
        candidate = os.path.join(dir_name, f"{name}_copy{ext}")
        counter = 1
        while os.path.exists(candidate):
            candidate = os.path.join(dir_name, f"{name}_copy{counter}{ext}")
            counter += 1
        return candidate

    def create_new_folder(self):
        """创建默认名为 'New_Folder' 的文件夹并进入重命名"""
        base_name = "New_Folder"
        full_path = self._get_unique_name(os.path.join(self.current_path, base_name))
        try:
            os.makedirs(full_path)
            self.refresh_view()
            # 找到刚创建的项并开始编辑
            item = self._find_item_by_name(os.path.basename(full_path))
            if item:
                self.start_rename_edit(item)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Unable to create folder:\n{e}")

    def open_in_explorer(self):
        """在 Windows 资源管理器中打开当前路径"""
        try:
            # 方法1：使用 os.startfile（仅 Windows）
            if os.name == 'nt':
                os.startfile(self.current_path)
            else:
                # 非 Windows（如 Linux/macOS）可选处理
                subprocess.Popen(['xdg-open', self.current_path])  # Linux
                # subprocess.Popen(['open', self.current_path])   # macOS
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Unable to open File Explorer:\n{e}")

    def create_new_mindes_file(self):
        """创建默认名为 'New_Simu.mindes' 的文件并进入重命名"""
        base_name = "New_Simu.mindes"
        full_path = self._get_unique_name(os.path.join(self.current_path, base_name))
        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write("# MInDes input file\n")
            self.refresh_view()
            item = self._find_item_by_name(os.path.basename(full_path))
            if item:
                self.start_rename_edit(item)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Unable to create file:\n{e}")

    def _get_unique_name(self, path: str) -> str:
        """给定基础路径，返回不冲突的唯一路径（类似 New_Folder, New_Folder1, ...）"""
        if not os.path.exists(path):
            return path
        root, ext = os.path.splitext(path)
        counter = 1
        while True:
            candidate = f"{root}{counter}{ext}"
            if not os.path.exists(candidate):
                return candidate
            counter += 1

    def _find_item_by_name(self, name: str):
        """在 list_widget 中查找文本为 name 的 item"""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.text() == name:
                return item
        return None

    def delete_selected_items(self):
        items = self.list_widget.selectedItems()
        if not items:
            return

        names = [item.text() for item in items]
        reply = QMessageBox.question(
            self, "Confirm deletion",
            f"Are you sure you want to delete the following {len(names)} items?\n" + "\n".join(names),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            for item in items:
                name = item.text()
                full_path = os.path.join(self.current_path, name)
                try:
                    if os.path.isdir(full_path):
                        shutil.rmtree(full_path)
                    else:
                        os.remove(full_path)
                except Exception as e:
                    QMessageBox.critical(self, "Deletion failed", f"Cannot delete {name}:\n{e}")
            self.refresh_view()