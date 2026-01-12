# data_loader.py
import os
import glob
import vtk
import time
import queue
import threading

from PySide6.QtWidgets import (
    QFileDialog, QMessageBox, QDialog,
    QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton
)
from PySide6.QtCore import Qt, QTimer

class VTSDataLoaderMixin:
    """
    负责：
    - VTS 文件扫描 / 加载
    - 系列识别
    - 播放（Play / Stop）
    - Auto Update
    """

    # =====================================================
    # Public entry
    # =====================================================
    def load_vts(self, folder_path: str = None):
        if folder_path:
            if not os.path.isdir(folder_path):
                QMessageBox.critical(
                    self, "Invalid Path",
                    f"Not a valid directory:\n{folder_path}"
                )
                return
            self._load_vts_from_folder_or_series(folder_path)
        else:
            self._load_vts_interactive()

    # =====================================================
    # Interactive load
    # =====================================================
    def _load_vts_interactive(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select VTS Output Folder"
        )
        if folder:
            self._load_vts_from_folder_or_series(folder)

    # =====================================================
    # Detect series
    # =====================================================
    def _load_vts_from_folder_or_series(self, folder: str):
        vts_files = glob.glob(os.path.join(folder, "*.vts"))
        if not vts_files:
            QMessageBox.warning(
                self, "No Files",
                "No .vts files found in the selected folder."
            )
            return

        prefixes = set()
        for f in vts_files:
            prefix = self._extract_series_prefix(os.path.basename(f))
            if prefix is not None:
                prefixes.add(prefix)

        if not prefixes:
            QMessageBox.warning(
                self, "No Valid Series",
                "No valid VTS series found."
            )
            return

        prefixes = sorted(prefixes)

        # Multiple series → dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Select VTS Series")

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Multiple series detected:"))

        combo = QComboBox()
        combo.addItems(prefixes)
        layout.addWidget(combo)

        btns = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec() == QDialog.Accepted:
            self.load_vts_from_folder(folder, combo.currentText())

    # =====================================================
    # Folder load
    # =====================================================
    def load_vts_from_folder(self, folder: str, prefix: str):
        pattern = os.path.join(folder, f"{prefix}*.vts")
        files = glob.glob(pattern)

        def extract_index(path):
            name = os.path.basename(path)
            suffix = name[len(prefix):].replace(".vts", "")
            digits = "".join(c for c in suffix if c.isdigit())
            return int(digits) if digits else float("inf")

        files.sort(key=extract_index)

        if not files:
            QMessageBox.warning(
                self, "No Files",
                "No matching .vts files found."
            )
            return

        self.vts_folder = folder
        self.vts_prefix = prefix
        self.vts_file_list = files
        self.current_file_index = 0

        if not self.load_single_vts_file(files[0]):
            return
        
        self._reset_series_state()
        
        self.playback_group.setVisible(True)
        self.plot_line_checkbox.setVisible(True)
        self.display_group.setVisible(True)
        self._update_file_combo()
        self._update_playback_ui_enabled(True)

    # =====================================================
    # Single file load
    # =====================================================
    def load_single_vts_file(self, file_path: str):
        try:

            reader = vtk.vtkXMLStructuredGridReader()
            reader.SetFileName(file_path)
            reader.Update()

            output = reader.GetOutput()
            if not output or output.GetNumberOfPoints() == 0:
                self.playback_status_label.setText("❌ Empty dataset")
                self.current_data = None
                return False

            self.current_data = output
            self.populate_field_combos()

            self.playback_status_label.setText(
                f"✅ Loaded: {os.path.basename(file_path)}"
            )

            self._update_current_state_snapshot()

            # Initialize clip slider range
            if self.current_vis_mode == "Clip":
                self.on_clip_axis_changed(self.clip_axis_combo.currentText())
            self.playback_group.setVisible(True)

            return True

        except Exception as e:
            self.playback_status_label.setText(f"❌ Error: {e}")
            self.current_data = None
            return False

    # =====================================================
    # Playback UI helpers
    # =====================================================
    def on_file_combo_changed(self, index: int):
        if 0 <= index < len(self.vts_file_list):
            self.current_file_index = index
            self.load_single_vts_file(self.vts_file_list[index])
            self.update_playback_status()

    def refresh_file_list(self):
        if not self.vts_folder or not self.vts_prefix:
            return
        import glob, os
        pattern = os.path.join(self.vts_folder, f"{self.vts_prefix}*.vts")
        current_files = glob.glob(pattern)
        if not current_files:
            # 如果没有文件了，清空列表
            self.vts_file_list = []
            self._update_file_combo()
            self.playback_status_label.setText("⚠️ No .vts files found.")
            return
        # 提取数字并排序（与 auto-update 逻辑一致）
        def extract_number(f):
            base = os.path.basename(f)
            num_str = base[len(self.vts_prefix):].split('.')[0]
            digits = ''.join(filter(str.isdigit, num_str))
            return int(digits) if digits else -1
        current_files.sort(key=extract_number)
        # 记住当前选中的文件名（如果有效）
        current_selected_name = None
        if (0 <= self.current_file_index < len(self.vts_file_list)):
            current_selected_name = os.path.basename(self.vts_file_list[self.current_file_index])
        # 更新内部文件列表
        self.vts_file_list = current_files
        # 更新下拉框内容（但不触发 on_file_combo_changed）
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        self.file_combo.addItems([os.path.basename(f) for f in self.vts_file_list])
        # 尝试恢复原选中项
        new_index = -1
        if current_selected_name:
            try:
                new_index = [os.path.basename(f) for f in self.vts_file_list].index(current_selected_name)
            except ValueError:
                new_index = -1  # 未找到
        if new_index >= 0:
            self.file_combo.setCurrentIndex(new_index)
        else:
            if self.vts_file_list:
                # 可选：保持原 index（如果还在范围内），否则设为 0
                if self.current_file_index < len(self.vts_file_list):
                    self.file_combo.setCurrentIndex(self.current_file_index)
                else:
                    self.file_combo.setCurrentIndex(0)
            # 否则 combo 为空
        self.file_combo.blockSignals(False)
        # 可选：更新状态提示
        self.playback_status_label.setText("✅ File list refreshed.")

    def _update_file_combo(self):
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        self.file_combo.addItems(
            [os.path.basename(f) for f in self.vts_file_list]
        )
        if 0 <= self.current_file_index < len(self.vts_file_list):
            self.file_combo.setCurrentIndex(self.current_file_index)
        self.file_combo.blockSignals(False)

    # =====================================================
    # Sequential playback
    # =====================================================

    def start_sequential_playback(self):
        if not self.vts_file_list or self.is_sequential_playing:
            return
        self._disable_all_interactive_controls(True)
        self.play_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.is_sequential_playing = True
        # 重置状态
        if self.current_file_index >= len(self.vts_file_list) - 1:
            self.current_file_index = 0
        self.stop_playback_event.clear()
        while not self.frame_buffer.empty():
            self.frame_buffer.get()  # 清空旧缓冲
        with self._loaded_indices_lock:
            self._loaded_or_queued_indices.clear()
        # 加载第一帧（同步，确保开始）

        if not self.load_single_vts_file(self.vts_file_list[self.current_file_index]):
            self.stop_sequential_playback()
            return
        self.file_combo.setCurrentIndex(self.current_file_index)
        self.update_visualization()
        # 启动后台预加载（从第 1 帧开始，因为第 0 帧已加载）
        self.playback_worker = threading.Thread(
            target=self._preload_frames_worker,
            args=(self.current_file_index,),
            daemon=True
        )
        self.playback_worker.start()
        # 开始播放循环
        QTimer.singleShot(self._get_frame_delay_ms(), self._play_next_frame)

    def stop_sequential_playback(self):
        self.is_sequential_playing = False
        self.stop_playback_event.set()  # 通知线程退出
        # 清空缓冲区
        while not self.frame_buffer.empty():
            self.frame_buffer.get()
        self._disable_all_interactive_controls(False)
        self.play_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _play_next_frame(self):
        if not self.is_sequential_playing:
            return
        # 1. 尝试从缓冲区获取已加载的帧
        try:
            index, grid = self.frame_buffer.get_nowait()
            self.current_file_index = index
            self.current_data = grid  # 直接使用预加载数据！

            # 2. 更新 UI（文件名、状态等）
            self.file_combo.blockSignals(True)
            self.file_combo.setCurrentIndex(index)
            self.file_combo.blockSignals(False)
            self.playback_status_label.setText(f"✅ Playing: {os.path.basename(self.vts_file_list[index])}")
            # 3. 触发渲染（在 GUI 线程）
            self.update_visualization()
            if self.current_file_index == len(self.vts_file_list) - 1:
                self.stop_sequential_playback()
                return
        except queue.Empty:
            # 缓冲区空：降级为同步加载（不应常发生），这里修改为等待缓冲区
            # if self.current_file_index >= len(self.vts_file_list):
            #     self.stop_sequential_playback()
            #     return
            # # === 标记当前帧为“已加载” ===
            # with self._loaded_indices_lock:
            #     self._loaded_or_queued_indices.add(self.current_file_index)
            # success = self.load_single_vts_file(self.vts_file_list[self.current_file_index])
            # if not success:
            #     self.stop_sequential_playback()
            #     return
            # self.file_combo.setCurrentIndex(self.current_file_index)
            # self.current_file_index += 1
            # self.update_visualization()
            pass
        # 4. 安排下一帧（无论是否从缓冲区获取）
        if self.is_sequential_playing and self.current_file_index < len(self.vts_file_list):
            QTimer.singleShot(self._get_frame_delay_ms(), self._play_next_frame)
        else:
            self.stop_sequential_playback()

    def _preload_frames_worker(self, start_index: int):
        """后台线程：从 start_index 开始预加载 VTS 文件"""
        current_index = start_index
        while not self.stop_playback_event.is_set() and current_index < len(self.vts_file_list):
            # === 关键：检查是否已加载或已入队 ===
            with self._loaded_indices_lock:
                if current_index in self._loaded_or_queued_indices:
                    current_index += 1
                    continue
                # 标记为“已入队”，防止其他线程重复加载
                self._loaded_or_queued_indices.add(current_index)
            file_path = self.vts_file_list[current_index]
            # 1. 读取并解析 VTS（不涉及任何 GUI/VTK 渲染对象！）
            try:
                reader = vtk.vtkXMLStructuredGridReader()
                reader.SetFileName(file_path)
                reader.Update()
                output = reader.GetOutput()
                if output and output.GetNumberOfPoints() > 0:
                    # 2. 将数据放入缓冲区（线程安全）
                    # 注意：vtkDataObject 不是线程安全的，但只读使用通常 OK
                    self.frame_buffer.put((current_index, output))
                else:
                    print(f"⚠️ Skipped empty frame: {file_path}")
            except Exception as e:
                print(f"❌ Preload error at index {current_index}: {e}")
                pass
            current_index += 1
            # 控制预加载速度（避免占满磁盘 I/O）
            time.sleep(0.001)  # 可选

    # =====================================================
    # Auto update
    # =====================================================
    def toggle_auto_update(self, state):
        enabled = (state == Qt.CheckState.Checked.value)
        self.auto_update_interval_combo.setEnabled(enabled)
        if enabled:
            self.start_auto_update()
        else:
            self.pause_auto_update()

    def start_auto_update(self):
        if not self.vts_folder or not self.vts_prefix:
            self.auto_update_checkbox.setChecked(False)
            return

        self._disable_for_auto_update(True)

        interval_text = self.auto_update_interval_combo.currentText()
        interval_ms = int(float(interval_text[:-1]) * 1000)

        if not self.auto_update_timer:
            self.auto_update_timer = QTimer(self)
            self.auto_update_timer.timeout.connect(
                self.draw_new_vts_files
            )
        self.auto_update_timer.stop()
        self.auto_update_timer.start(interval_ms)

    def pause_auto_update(self):
        if self.auto_update_timer:
            self.auto_update_timer.stop()
        self._disable_for_auto_update(False)

    def draw_new_vts_files(self):
        if not self.vts_folder or not self.vts_prefix:
            return

        old_file_list = list(self.vts_file_list)
        self._save_scroll_position()
        self.refresh_file_list()
        self._restore_scroll_position()
        if not self.vts_file_list:
            self.playback_status_label.setText("⚠️ Auto-check: No .vts files.")
            return

        latest_file = self.vts_file_list[-1]
        latest_basename = os.path.basename(latest_file)

        # 获取当前正在显示的文件名（如果有效）
        current_displayed_basename = None
        if (self.current_data is not None 
            and 0 <= self.current_file_index < len(old_file_list)):
            current_displayed_basename = os.path.basename(old_file_list[self.current_file_index])

        # 如果最新文件不是当前显示的，则加载它
        if current_displayed_basename != latest_basename:
            try:
                success = self.load_single_vts_file(latest_file)
                if success:
                    # 更新当前索引为最新文件
                    self.current_file_index = len(self.vts_file_list) - 1
                    # 同步下拉框选中状态（虽然 refresh_file_list 可能已设，但确保一致）
                    self.file_combo.blockSignals(True)
                    self.file_combo.setCurrentIndex(self.current_file_index)
                    self.update_visualization()
                    self.file_combo.blockSignals(False)
                    self.playback_status_label.setText("✅ Auto-loaded latest file.")
                else:
                    self.playback_status_label.setText("❌ Auto-load failed.")
            except Exception as e:
                self.playback_status_label.setText(f"❌ Auto-load error: {str(e)}")
        else:
            self.playback_status_label.setText("ℹ️ No new files.")

    # =====================================================
    # Helpers
    # =====================================================
    def update_playback_status(self):
        if self.vts_file_list and 0 <= self.current_file_index < len(self.vts_file_list):
            fname = os.path.basename(self.vts_file_list[self.current_file_index])
            self.playback_status_label.setText("✅ Loaded")
        else:
            self.playback_status_label.setText("⚠️ No data")

    def _reset_series_state(self):
        # 重置所有状态（因为换了数据系列）
        self.camera_position = None
        self.should_reset_camera_on_load = True
        self.field_selection = None
        self.colormap_selection = "Cool-Warm"
        self._boundary_extract_filter = None
        self._create_lookup_table(self.colormap_selection, (0.0, 1.0))
        self.update_colormap_preview()
        self.auto_range_enabled = True
        self.vis_mode = "Surface"
        self.show_axes = False
        self.show_bounds = False
        self.show_colorbar = False
        self.show_with_boundary = False
        self.glyph_enabled = False
        self.plot_line_enabled = False
        self.show_with_boundary_checkbox.setChecked(True)
        self.auto_range_checkbox.setChecked(True)
        self.bg_color_combo.setCurrentText("Light Gray")
        self.auto_update_interval_combo.setCurrentText("0.5s")
        self.glyph_group.setVisible(False)

        # 统一透明度设置为100%（滑块值100，对应标签1.00）
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(100)  # 滑块值设为100
        self.opacity_value_label.setText("1.00")  # 标签显示1.00
        self.opacity_slider.blockSignals(False)
        # === 重置 render ===
        # surface
        self.surface_mapper.SetInputData(self.current_data)
        self.renderer.AddActor(self.surface_actor)
        # wire
        self.wire_mapper.SetInputData(self.current_data)
        self.renderer.AddActor(self.wire_actor)
        # clip
        self.clipper.SetInputData(self.current_data)
        self.renderer.AddActor(self.clip_actor)
        # contour
        self.contour_filter.SetInputData(self.current_data)
        self.renderer.AddActor(self.contour_actor)
        # Arrow
        self.glyph_filter.SetInputData(self.current_data)
        self.renderer.AddActor(self.glyph_actor)



    def _extract_series_prefix(self, filename):
        """
        从文件名（不含路径）中提取系列前缀。
        示例:
            "scalar_variables_step0.vts"      → "scalar_variables_step"
            "vec3_variables_step300.vts"     → "vec3_variables_step"
            "MeshData_step600.vts"           → "MeshData_step"
            "data123.vts"                    → "data"
            "test.vts"                       → "test" （无数字则保留原名）
        """
        if not filename.endswith('.vts'):
            return None
        base = filename[:-4]  # 移除 .vts
        # 从末尾移除连续数字
        i = len(base) - 1
        while i >= 0 and base[i].isdigit():
            i -= 1
        prefix = base[:i+1]
        # 如果全是数字（如 "123.vts"），返回空字符串，但我们保留至少一个字符
        if not prefix:
            prefix = base  # 或者返回 "file"，但这里保留原逻辑
        return prefix

    def _update_playback_ui_enabled(self, enabled=True):
        """启用/禁用播放相关控件（不包括 Auto Update 复选框）"""
        self.file_combo.setEnabled(enabled)

    def populate_field_combos(self):
        # 1. 保存当前选中的字段名（实际 name，不是带 [S]/[V] 的 display_name）
        current_name = None
        if self.field_combo.count() > 0:
            current_text = self.field_combo.currentText()
            # 尝试从 "[S] Temperature" 提取 "Temperature"
            if current_text.startswith("[S] ") or current_text.startswith("[V] "):
                current_name = current_text[4:]  # 跳过前缀 "[X] "
            else:
                current_name = current_text  # 兜底（比如 "(No fields)"）

        self.field_combo.blockSignals(True)
        # 2. 清空并重新填充
        self.field_combo.clear()

        point_data = self.current_data.GetPointData()
        fields = []  # 每项: (display_name, name, type)
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

        # 排序：标量在前，向量在后；同类型按名称排序
        fields.sort(key=lambda x: (x[2] != 'scalar', x[1]))

        # 3. 添加到 combo
        name_to_index = {}
        for idx, (display_name, name, _) in enumerate(fields):
            self.field_combo.addItem(display_name)
            name_to_index[name] = idx

        # 4. 恢复之前选中的字段（如果存在）
        if fields:
            target_index = 0  # 默认第一个
            if current_name and current_name in name_to_index:
                target_index = name_to_index[current_name]
            self.field_combo.setCurrentIndex(target_index)
            self.update_range_inputs()
        else:
            self.field_combo.addItem("(No fields)")
        self.field_combo.blockSignals(False)

    def _update_current_state_snapshot(self):
        """从当前控件读取值，更新状态快照（供后续恢复用）"""
        if not self.current_data:
            return

        cam = self.renderer.GetActiveCamera()
        self.camera_position = cam.GetPosition()
        self.camera_focal_point = cam.GetFocalPoint()
        self.camera_view_up = cam.GetViewUp()
        self.camera_distance = cam.GetDistance()

        self.field_selection = self.field_combo.currentText()
        self.colormap_selection = self.colormap_combo.currentText()
        self.auto_range_enabled = self.auto_range_checkbox.isChecked()
        self.user_min_val = self.min_spin.value()
        self.user_max_val = self.max_spin.value()
        self.vis_mode = self.vis_mode_combo.currentText()
        self.clip_axis = self.clip_axis_combo.currentText()
        self.clip_position = self.clip_slider.value()
        self.contour_levels_text = self.contour_levels_edit.text()
        self.opacity_value = self.opacity_slider.value() / 100.0
        self.show_axes = self.show_axes_checkbox.isChecked()
        self.show_bounds = self.show_bounds_checkbox.isChecked()
        self.show_colorbar = self.show_colorbar_checkbox.isChecked()
        self.show_with_boundary = self.show_with_boundary_checkbox.isChecked()
        self.arrow_color_rgb = self.arrow_color
        self.plot_line_enabled = self.plot_line_checkbox.isChecked()

    def _disable_for_auto_update(self, disable=True):
        """复用全禁用逻辑，但保持 auto_update_checkbox 可用"""
        self._disable_all_interactive_controls(disable)
        if disable:
            # 解禁 Auto Update 复选框，允许用户取消
            self.auto_update_checkbox.setEnabled(True)
        else:
            # 恢复时 _disable_all... 已恢复所有，但 Stop 为禁用状态
            self.stop_button.setDisabled(True)
            pass

    def _get_frame_delay_ms(self):
        """返回每帧之间的延迟（毫秒），可被子类或UI覆盖"""
        # 默认 20ms (50 FPS)，但可根据性能调整
        return 20

    def _save_scroll_position(self):
        """保存当前滚动位置"""
        if hasattr(self, 'control_scroll_area'):
            vbar = self.control_scroll_area.verticalScrollBar()
            self._saved_scroll_pos = vbar.value() if vbar else 0
        else:
            self._saved_scroll_pos = 0

    def _restore_scroll_position(self):
        """恢复滚动位置"""
        if hasattr(self, 'control_scroll_area'):
            vbar = self.control_scroll_area.verticalScrollBar()
            if vbar:
                vbar.setValue(self._saved_scroll_pos)