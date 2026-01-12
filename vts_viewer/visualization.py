# visualization.py
import vtk
import math
from PySide6.QtCore import Qt

class VisualizationMixin:
    """
    VTK 可视化核心：
    - actor / mapper / pipeline
    - update_visualization 统一入口
    """

    # =====================================================
    # Public entry
    # =====================================================
    
    def update_visualization(self):
        # self.renderer.RemoveAllViewProps()
        if not self.current_data:
            return
        # 隐藏所有无关 actor
        self._hide_all_actors_except()
        # 保存当前相机位置（如果需要保持）
        camera = self.renderer.GetActiveCamera()
        current_position = camera.GetPosition()
        current_focal_point = camera.GetFocalPoint()
        current_view_up = camera.GetViewUp()
        # 禁用渲染事件的自动渲染，手动控制
        self.vtk_widget.GetRenderWindow().SetDesiredUpdateRate(30.0)
        # === 根据 "Show with boundary" 决定是否裁剪 ===
        grid_to_render = None
        if not self.show_with_boundary_checkbox.isChecked():
            # 需要去掉最外层（边界层）
            dims = [0, 0, 0]
            self.current_data.GetDimensions(dims)  # [nx, ny, nz]
            nx, ny, nz = dims[0], dims[1], dims[2]
            # 安全检查：至少要有 3 层才能裁剪（0,1,2 → 保留 1）
            if nx >= 3 and ny >= 3 and nz >= 3:
                self._boundary_extract_filter = vtk.vtkExtractGrid()
                self._boundary_extract_filter.SetInputData(self.current_data)
                # VOI: (imin, imax, jmin, jmax, kmin, kmax) —— inclusive
                self._boundary_extract_filter.SetVOI(1, nx - 2, 1, ny - 2, 1, nz - 2)
                self._boundary_extract_filter.Update()
                grid_to_render = self._boundary_extract_filter.GetOutput()
            else:
                grid_to_render = self.current_data
        else:
            grid_to_render = self.current_data
            self._boundary_extract_filter = None
        # 确保有数据
        if grid_to_render.GetNumberOfPoints() == 0:
            self.playback_status_label.setText("⚠️ No valid data points")
            return
        
        # === 后续使用 grid_to_render 进行可视化 ===
        display_text = self.field_combo.currentText()
        if "(No fields)" in display_text:
            return
        is_vector = display_text.startswith("[V]")
        field_name = display_text[4:]

        # Always compute magnitude if needed
        mag_arr = None
        scalar_arr = None
        scalar_name = None
        if is_vector:
            scalar_name = self.array_magnitude_name(field_name)
        else:
            scalar_name = field_name
        if grid_to_render.GetPointData().HasArray(scalar_name):
            scalar_arr = grid_to_render.GetPointData().GetArray(scalar_name)
            grid_to_render.GetPointData().SetActiveScalars(scalar_name)
        else:
            if is_vector:
                mag_arr = self.compute_magnitude_array(field_name, grid_to_render)
                if not mag_arr:
                    return
                scalar_arr = mag_arr
                scalar_name = mag_arr.GetName()
                grid_to_render.GetPointData().AddArray(mag_arr)
                grid_to_render.GetPointData().SetActiveScalars(scalar_name)
            else:
                return

        # Update range
        if self.auto_range_checkbox.isChecked():
            rmin, rmax = scalar_arr.GetRange()
            self.min_spin.blockSignals(True)
            self.max_spin.blockSignals(True)
            self.min_spin.setValue(rmin)
            self.max_spin.setValue(rmax)
            self.min_spin.blockSignals(False)
            self.max_spin.blockSignals(False)
        else:
            rmin = self.min_spin.value()
            rmax = self.max_spin.value()
            if rmin >= rmax:
                rmin, rmax = scalar_arr.GetRange()

        # prepare lut
        self._create_lookup_table(self.colormap_combo.currentText(), (rmin, rmax))

        mode = self.current_vis_mode

        # === 渲染当前模式（复用 actor）===
        if mode == "Surface":
            self._render_surface_actor(grid_to_render, scalar_name, with_grid=False)
        elif mode == "Surface with Grid":
            self._render_surface_actor(grid_to_render, scalar_name, with_grid=True)
        elif mode == "Clip":
            self._render_clip_actor(grid_to_render, scalar_name)
        elif mode == "Contour":
            self._render_contour_actor(grid_to_render, scalar_name)
        elif mode == "Vector Arrows":
            if not is_vector:
                return
            self._render_glyph_actor(
                grid_to_render,
                field_name,
                color_mode=self.glyph_color_mode_combo.currentText(),
                size_mode=self.glyph_size_mode_combo.currentText(),
                scale_factor=float(self.glyph_scale_edit.text())
            )
        else:
            return

        # === Add optional visual aids ===
        if self.show_axes_checkbox.isChecked():
            if not self.orientation_marker:
                axes = vtk.vtkAxesActor()
                axes.SetTotalLength(1.0, 1.0, 1.0)
                axes.SetShaftTypeToCylinder()
                axes.SetCylinderRadius(0.02)
                axes.SetAxisLabels(True)
                widget = vtk.vtkOrientationMarkerWidget()
                widget.SetOutlineColor(0.93, 0.57, 0.13)
                widget.SetOrientationMarker(axes)
                widget.SetInteractor(self.iren)
                widget.SetViewport(0.0, 0.0, 0.2, 0.2)
                widget.EnabledOn()
                widget.InteractiveOff()
                self.orientation_marker = widget                
                # 设置初始文本颜色
                brightness = self.renderer.GetBackground()[0]  # 获取背景亮度
                text_color = [0, 0, 0] if brightness > 0.5 else [1, 1, 1]
                self._update_text_colors(text_color)
            self.orientation_marker.On()
        else:
            if self.orientation_marker:
                self.orientation_marker.Off()

        if self.show_bounds_checkbox.isChecked() and grid_to_render:
            if not self._cube_axes_actor:
                bounds = grid_to_render.GetBounds()
                cube_axes = vtk.vtkCubeAxesActor()
                cube_axes.SetBounds(bounds)
                cube_axes.SetCamera(self.renderer.GetActiveCamera())
                cube_axes.SetXLabelFormat("%.2g")
                cube_axes.SetYLabelFormat("%.2g")
                cube_axes.SetZLabelFormat("%.2g")
                cube_axes.SetFlyModeToOuterEdges()
                cube_axes.SetTickLocationToInside()
                cube_axes.XAxisMinorTickVisibilityOff()
                cube_axes.YAxisMinorTickVisibilityOff()
                cube_axes.ZAxisMinorTickVisibilityOff()
                self._cube_axes_actor = cube_axes
                self.renderer.AddActor(self._cube_axes_actor)
                # 设置初始文本颜色
                brightness = self.renderer.GetBackground()[0]
                text_color = [0, 0, 0] if brightness > 0.5 else [1, 1, 1]
                self._update_text_colors(text_color)
            else:
                # 更新边界和相机
                bounds = grid_to_render.GetBounds()
                self._cube_axes_actor.SetBounds(bounds)
                self._cube_axes_actor.SetCamera(self.renderer.GetActiveCamera())
            self._cube_axes_actor.VisibilityOn()
        else:
            if self._cube_axes_actor:
                self._cube_axes_actor.VisibilityOff()

        if self.show_colorbar_checkbox.isChecked():
            if not self._scalar_bar_actor:
                scalar_bar = vtk.vtkScalarBarActor()
                scalar_bar.SetLookupTable(self.lut)
                scalar_bar.SetTitle(scalar_name)
                scalar_bar.SetNumberOfLabels(5)
                scalar_bar.SetLabelFormat("%.3g")
                scalar_bar.SetOrientationToHorizontal()
                scalar_bar.SetPosition(0.2, 0.02)
                scalar_bar.SetWidth(0.5)
                scalar_bar.SetHeight(0.05)
                title_prop = scalar_bar.GetTitleTextProperty()
                title_prop.SetFontFamilyToArial()
                title_prop.SetFontSize(14)
                title_prop.SetBold(0)
                title_prop.SetItalic(0)
                label_prop = scalar_bar.GetLabelTextProperty()
                label_prop.SetFontFamilyToArial()
                label_prop.SetFontSize(10)
                label_prop.SetBold(0)
                label_prop.SetItalic(0)
                self._scalar_bar_actor = scalar_bar
                self.renderer.AddActor2D(self._scalar_bar_actor)
                # 设置初始文本颜色
                brightness = self.renderer.GetBackground()[0]
                text_color = [0, 0, 0] if brightness > 0.5 else [1, 1, 1]
                self._update_text_colors(text_color)
            else:
                # 更新颜色映射和标题
                self._scalar_bar_actor.SetLookupTable(self.lut)
                self._scalar_bar_actor.SetTitle(scalar_name)
            self._scalar_bar_actor.VisibilityOn()
        else:
            if self._scalar_bar_actor:
                self._scalar_bar_actor.VisibilityOff()
        if self.should_reset_camera_on_load:
            self.renderer.ResetCamera()
            self.should_reset_camera_on_load = False
        else:
            # 恢复之前的相机设置
            camera.SetPosition(current_position)
            camera.SetFocalPoint(current_focal_point)
            camera.SetViewUp(current_view_up)
        self.vtk_widget.GetRenderWindow().Render()

    # =====================================================
    # Surface
    # =====================================================
    
    def _render_surface_actor(self, grid, scalar_name, with_grid=False):
        # --- 主 Surface (填充) ---
        current_opacity = self.opacity_slider.value() / 100.0
        self.surface_mapper.SetInputData(grid)
        self.surface_mapper.SetScalarModeToUsePointFieldData()
        self.surface_mapper.SelectColorArray(scalar_name)
        self.surface_mapper.SetLookupTable(self.lut)
        self.surface_mapper.UseLookupTableScalarRangeOn()
        self.surface_actor.GetProperty().SetOpacity(current_opacity)  # 修正透明度
        self.surface_actor.GetProperty().SetRepresentationToSurface()
        self.surface_actor.VisibilityOn()
        
        # --- Wireframe (网格线) ---
        if with_grid:
            # 设置输入数据
            self.wire_mapper.SetInputData(grid)
            wire_opacity = min(1.0, max(0.02, current_opacity * 1.2))  # 网格线稍微更明显一些
            self.wire_actor.GetProperty().SetOpacity(wire_opacity)
            self.wire_actor.VisibilityOn()

    # =====================================================
    # Clip
    # =====================================================
    
    def _render_clip_actor(self, grid, scalar_name):
        bounds = grid.GetBounds()
        pos = self.clip_slider.value()
        axis = self.clip_axis_combo.currentText()

        if axis == "X":
            center = [pos, (bounds[2]+bounds[3])/2, (bounds[4]+bounds[5])/2]
            normal = (1, 0, 0)
        elif axis == "Y":
            center = [(bounds[0]+bounds[1])/2, pos, (bounds[4]+bounds[5])/2]
            normal = (0, 1, 0)
        else:  # Z
            center = [(bounds[0]+bounds[1])/2, (bounds[2]+bounds[3])/2, pos]
            normal = (0, 0, 1)

        self.plane.SetOrigin(*center)
        self.plane.SetNormal(*normal)

        self.clipper.SetInputData(grid)
        self.clip_mapper.SetScalarModeToUsePointFieldData()
        self.clip_mapper.SelectColorArray(scalar_name)
        self.clip_mapper.SetLookupTable(self.lut)
        self.clip_mapper.UseLookupTableScalarRangeOn()
        self.clip_actor.GetProperty().SetOpacity(self.opacity_slider.value() / 100.0)
        self.clip_actor.VisibilityOn()

    # =====================================================
    # Contour
    # =====================================================
    
    def _render_contour_actor(self, grid, scalar_name):
        text = self.contour_levels_edit.text().strip()
        if not text:
            if self.contour_actor:
                self.contour_actor.VisibilityOff()
            return

        try:
            levels = [float(x.strip()) for x in text.split(",") if x.strip()]
        except ValueError:
            if self.contour_actor:
                self.contour_actor.VisibilityOff()
            return

        if not levels:
            if self.contour_actor:
                self.contour_actor.VisibilityOff()
            return
        # 设置等值面层级
        self.contour_filter.SetNumberOfContours(0)
        for i, level in enumerate(levels):
            self.contour_filter.SetValue(i, level)
        # 更新输入数据
        self.contour_filter.SetInputData(grid)
        self.contour_filter.SetInputArrayToProcess(
            0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, scalar_name
        )
        self.contour_mapper.SetScalarModeToUsePointFieldData()
        self.contour_mapper.SelectColorArray(scalar_name)
        self.contour_mapper.SetLookupTable(self.lut)
        self.contour_mapper.UseLookupTableScalarRangeOn()
        self.contour_actor.GetProperty().SetOpacity(self.opacity_slider.value() / 100.0)
        self.contour_actor.VisibilityOn()

    # =====================================================
    # Glyph
    # =====================================================
    
    def _render_glyph_actor(self, grid, vector_field_name, color_mode, size_mode, scale_factor):
        """
        渲染向量箭头 (Glyph)。
        """
        vectors = grid.GetPointData().GetArray(vector_field_name)
        if not vectors or vectors.GetNumberOfComponents() != 3:
            self.playback_status_label.setText("❌ Invalid vector data for glyph.")
            self.glyph_actor.VisibilityOff()
            return
        grid.GetPointData().SetActiveVectors(vector_field_name)
        # =============================
        # 1. 处理 Scale Mode
        # =============================
    

        # =============================
        # 2. 配置 Glyph Filter
        # =============================
        self.glyph_filter.SetInputData(grid)
        self.glyph_filter.SetInputArrayToProcess(
            0, 0, 0,
            vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS,
            vector_field_name
        )
        self.glyph_filter.SetVectorModeToUseVector()
        if size_mode == "Uniform":
            self.glyph_filter.SetScaleModeToDataScalingOff()
        else:
            self.glyph_filter.SetScaleModeToScaleByVector()
        self.glyph_filter.OrientOn()
        self.glyph_filter.SetScaleFactor(scale_factor)
        self.glyph_filter.Update()
        
        # =============================
        # 3. 配置颜色（Display）
        # =============================
        if color_mode == "Colormap":
            mag_name = self.array_magnitude_name(vector_field_name)
            self.glyph_mapper.SetScalarModeToUsePointFieldData()
            self.glyph_mapper.SelectColorArray(mag_name)
            self.glyph_mapper.SetLookupTable(self.lut)
            self.glyph_mapper.UseLookupTableScalarRangeOn()
            self.glyph_mapper.ScalarVisibilityOn()
        else:
            self.glyph_mapper.ScalarVisibilityOff()
            r, g, b = self.arrow_color  # 已初始化，无需 getattr
            self.glyph_actor.GetProperty().SetColor(r, g, b)

        # =============================
        # 4. 其他显示属性
        # =============================
        # self.glyph_actor.GetProperty().SetRepresentationToSurface()
        opacity = self.opacity_slider.value() / 100.0
        self.glyph_actor.GetProperty().SetOpacity(opacity)
        self.glyph_actor.VisibilityOn()

    # =====================================================
    # Color bar
    # =====================================================
    
    def update_colorbar_visibility(self, state):
        if self._scalar_bar_actor:
            if state == Qt.CheckState.Checked.value:
                self._scalar_bar_actor.VisibilityOn()
            else:
                self._scalar_bar_actor.VisibilityOff()
            self.vtk_widget.GetRenderWindow().Render()
        self.update_visualization()

    # =====================================================
    # Axes
    # =====================================================
    
    def update_axes_visibility(self, state):
        if self.orientation_marker:
            if state == Qt.CheckState.Checked.value:
                self.orientation_marker.On()
            else:
                self.orientation_marker.Off()
            self.vtk_widget.GetRenderWindow().Render()
        self.update_visualization()

    # =====================================================
    # Bounds
    # =====================================================
    
    def update_bounds_visibility(self, state):
        if self._cube_axes_actor:
            if state == Qt.CheckState.Checked.value:
                self._cube_axes_actor.VisibilityOn()
            else:
                self._cube_axes_actor.VisibilityOff()
            self.vtk_widget.GetRenderWindow().Render()
        self.update_visualization()

    # =====================================================
    # Background
    # =====================================================
   
    def update_background_color(self):
        """根据下拉栏选择更新背景颜色"""
        # 从下拉栏获取颜色
        color_name = self.bg_color_combo.currentText()
        color_map = {
            "White": (1.0, 1.0, 1.0),
            "Light Gray": (0.9, 0.9, 0.9),
            "Gray": (0.5, 0.5, 0.5),
            "Dark Gray": (0.2, 0.2, 0.2),
            "Black": (0.0, 0.0, 0.0)
        }
        r, g, b = color_map.get(color_name, (0.9, 0.9, 0.9))  # 默认淡灰色
        if not hasattr(self, 'renderer') or not self.renderer:
            print("Warning: Renderer not ready yet")
            return
        self.renderer.SetBackground(r, g, b)
        # 计算合适的文本颜色（基于亮度）
        brightness = (r * 299 + g * 587 + b * 114) / 1000  # BT.709 系数
        # 根据亮度选择文本颜色
        text_color = [0, 0, 0] if brightness > 0.5 else [1, 1, 1]
        # 更新 color bar、cube axes 和 orientation marker 的文本颜色
        self._update_text_colors(text_color)
        if hasattr(self, 'vtk_widget') and self.vtk_widget:
            self.vtk_widget.GetRenderWindow().Render()
        
    def _update_text_colors(self, text_color):
        # 更新 color bar 文本颜色
        if self._scalar_bar_actor:
            title_prop = self._scalar_bar_actor.GetTitleTextProperty()
            label_prop = self._scalar_bar_actor.GetLabelTextProperty()
            title_prop.SetColor(*text_color)
            label_prop.SetColor(*text_color)
        # 更新 cube axes 文本颜色
        if self._cube_axes_actor:
            for i in range(3):  # X=0, Y=1, Z=2
                self._cube_axes_actor.GetTitleTextProperty(i).SetColor(*text_color)
                self._cube_axes_actor.GetLabelTextProperty(i).SetColor(*text_color)

            # 设置轴线颜色
            r, g, b = text_color
            x_prop = self._cube_axes_actor.GetXAxesLinesProperty()
            if x_prop:
                x_prop.SetColor(r, g, b)
                x_prop.SetLineWidth(1.0)

            y_prop = self._cube_axes_actor.GetYAxesLinesProperty()
            if y_prop:
                y_prop.SetColor(r, g, b)
                y_prop.SetLineWidth(1.0)

            z_prop = self._cube_axes_actor.GetZAxesLinesProperty()
            if z_prop:
                z_prop.SetColor(r, g, b)
                z_prop.SetLineWidth(1.0)
        # 更新 orientation marker 文本颜色
        if self.orientation_marker:
            axes = self.orientation_marker.GetOrientationMarker()
            if isinstance(axes, vtk.vtkAxesActor):
                axes.GetXAxisCaptionActor2D().GetCaptionTextProperty().SetColor(*text_color)
                axes.GetYAxisCaptionActor2D().GetCaptionTextProperty().SetColor(*text_color)
                axes.GetZAxisCaptionActor2D().GetCaptionTextProperty().SetColor(*text_color)

    def reset_view(self, axis):
        if not self.current_data:
            return
        camera = self.renderer.GetActiveCamera()
        bounds = self.current_data.GetBounds()
        center = [(bounds[0]+bounds[1])/2, (bounds[2]+bounds[3])/2, (bounds[4]+bounds[5])/2]
        dist = max(bounds[1]-bounds[0], bounds[3]-bounds[2], bounds[5]-bounds[4]) * 3

        if axis == "X":
            camera.SetPosition(center[0] + dist, center[1], center[2])
            camera.SetFocalPoint(*center)
            camera.SetViewUp(0, 0, 1)
        elif axis == "Y":
            camera.SetPosition(center[0], center[1] + dist, center[2])
            camera.SetFocalPoint(*center)
            camera.SetViewUp(0, 0, 1)
        elif axis == "Z":
            camera.SetPosition(center[0], center[1], center[2] + dist)
            camera.SetFocalPoint(*center)
            camera.SetViewUp(0, 1, 0)

        self.renderer.ResetCameraClippingRange()
        self.vtk_widget.GetRenderWindow().Render()

    # =====================================================
    # Helper
    # =====================================================

    def _hide_all_actors_except(self, keep_actor_name=None):
        """隐藏所有可视化 actor，除了指定的一个"""
        actors_to_hide = [
            'surface_actor',
            'wire_actor',
            'clip_actor',
            'contour_actor',
            'glyph_actor',
        ]
        for attr_name in actors_to_hide:
            if attr_name == keep_actor_name:
                continue
            actor = getattr(self, attr_name, None)
            if actor:
                actor.VisibilityOff()

    def compute_magnitude_array(self, vector_array_name, grid=None):
        if grid is None:
            grid = self.current_data
        if not grid:
            return None
        vectors = grid.GetPointData().GetArray(vector_array_name)
        if not vectors or vectors.GetNumberOfComponents() != 3:
            return None
        n_points = vectors.GetNumberOfTuples()
        magnitude = vtk.vtkFloatArray()
        magnitude.SetName(self.array_magnitude_name(vector_array_name))
        magnitude.SetNumberOfValues(n_points)
        for i in range(n_points):
            vx, vy, vz = vectors.GetTuple3(i)
            mag = math.sqrt(vx*vx + vy*vy + vz*vz)
            magnitude.SetValue(i, mag)
        return magnitude
    
    def array_magnitude_name(self, vector_array_name):
        return f"{vector_array_name}_magnitude"

    def _create_lookup_table(self, colormap_name, table_range):
        # 如果 colormap 或 range 没变，不修改现有 LUT
        if (self._current_colormap == colormap_name and
            self._current_lut_range == table_range):
            return
        self.lut = vtk.vtkLookupTable()
        if colormap_name == "Cool-Warm":
            self._setup_coolwarm_lut(self.lut)
        elif colormap_name == "Rainbow":
            self.lut.SetHueRange(0.0, 0.667)
        elif colormap_name == "Grayscale":
            self.lut.SetHueRange(0, 0)
            self.lut.SetSaturationRange(0, 0)
            self.lut.SetValueRange(0, 1)
        elif colormap_name == "Viridis":
            self._setup_viridis_lut(self.lut)
        elif colormap_name == "Plasma":
            self._setup_plasma_lut(self.lut)
        self.lut.SetTableRange(*table_range)
        self.lut.Build()
        self._current_colormap = colormap_name
        self._current_lut_range = table_range
        return

    def _setup_coolwarm_lut(self, lut):
        """经典 Cool-Warm: 深蓝 -> 白 -> 深红"""
        # 将提供的颜色值转换为RGB浮点数
        deep_blue_rgb = [int('3b', 16) / 255.0, int('4c', 16) / 255.0, int('c0', 16) / 255.0]  # 深蓝
        white_rgb = [int('dd', 16) / 255.0, int('dd', 16) / 255.0, int('dd', 16) / 255.0]      # 白色
        deep_red_rgb = [int('b4', 16) / 255.0, int('04', 16) / 255.0, int('26', 16) / 255.0]   # 深红
        lut.SetNumberOfColors(256)
        lut.Build()
        for i in range(256):
            t = i / 255.0
            if t <= 0.5:
                # 计算从深蓝到白色的插值
                r = deep_blue_rgb[0] + (white_rgb[0] - deep_blue_rgb[0]) * (t * 2)
                g = deep_blue_rgb[1] + (white_rgb[1] - deep_blue_rgb[1]) * (t * 2)
                b = deep_blue_rgb[2] + (white_rgb[2] - deep_blue_rgb[2]) * (t * 2)
            else:
                # 计算从白色到深红的插值
                r = white_rgb[0] + (deep_red_rgb[0] - white_rgb[0]) * ((t - 0.5) * 2)
                g = white_rgb[1] + (deep_red_rgb[1] - white_rgb[1]) * ((t - 0.5) * 2)
                b = white_rgb[2] + (deep_red_rgb[2] - white_rgb[2]) * ((t - 0.5) * 2)
            # 设置颜色值
            lut.SetTableValue(i, r, g, b, 1.0)

    def _setup_viridis_lut(self, lut):
        lut.SetNumberOfColors(256)
        lut.Build()
        viridis_colors = [
            (0.267, 0.005, 0.329), (0.282, 0.140, 0.450), (0.251, 0.280, 0.528),
            (0.200, 0.410, 0.538), (0.151, 0.520, 0.520), (0.122, 0.610, 0.470),
            (0.208, 0.690, 0.388), (0.380, 0.750, 0.280), (0.600, 0.800, 0.150),
            (0.993, 0.906, 0.145)
        ]
        for i in range(256):
            t = i / 255.0
            idx = min(int(t * (len(viridis_colors) - 1)), len(viridis_colors) - 2)
            a = viridis_colors[idx]
            b = viridis_colors[idx + 1]
            f = (t * (len(viridis_colors) - 1)) - idx
            r = a[0] + f * (b[0] - a[0])
            g = a[1] + f * (b[1] - a[1])
            b_ = a[2] + f * (b[2] - a[2])
            lut.SetTableValue(i, r, g, b_, 1.0)

    def _setup_plasma_lut(self, lut):
        lut.SetNumberOfColors(256)
        lut.Build()
        plasma_colors = [
            (0.050, 0.030, 0.500), (0.150, 0.080, 0.600), (0.300, 0.120, 0.650),
            (0.500, 0.200, 0.600), (0.700, 0.300, 0.500), (0.850, 0.450, 0.350),
            (0.950, 0.700, 0.200), (0.990, 0.900, 0.150)
        ]
        for i in range(256):
            t = i / 255.0
            idx = min(int(t * (len(plasma_colors) - 1)), len(plasma_colors) - 2)
            a = plasma_colors[idx]
            b = plasma_colors[idx + 1]
            f = (t * (len(plasma_colors) - 1)) - idx
            r = a[0] + f * (b[0] - a[0])
            g = a[1] + f * (b[1] - a[1])
            b_ = a[2] + f * (b[2] - a[2])
            lut.SetTableValue(i, r, g, b_, 1.0)
