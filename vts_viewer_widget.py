import queue
import threading
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout
)
import vtk
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from vts_viewer.ui_vtk_view import VTKViewMixin
from vts_viewer.ui_control_panel import ControlPanelMixin
from vts_viewer.data_loader import VTSDataLoaderMixin
from vts_viewer.visualization import VisualizationMixin
from vts_viewer.ui_plot_over_line import PlotOverLineMixin

class VTSViewerWidget(
    QWidget,
    VTKViewMixin,
    ControlPanelMixin,
    VTSDataLoaderMixin,
    VisualizationMixin,
    PlotOverLineMixin
    ):
    def __init__(self, parent=None, progress_callback=None):
        vtk.vtkOutputWindow.SetInstance(vtk.vtkOutputWindow()) # 禁用vts的自动弹窗
        super().__init__(parent)
        self.progress_callback = progress_callback
        # ✅ 只在这里设置主布局
        self._report_progress("   Creating VTS main layout...")
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.current_data = None
        self.arrow_color = (1.0, 1.0, 1.0)  # white
        self.current_vis_mode = "Surface"
        self.control_panel_width = 300

        # === 渲染状态缓存（仅在 load_vts_from_folder 时重置）===
        self.camera_position = None
        self.camera_focal_point = None
        self.camera_view_up = None
        self.camera_distance = None
        self.should_reset_camera_on_load = False

        # 初始化 axes , bounds , colorbar actor
        self._cube_axes_actor = None
        self.orientation_marker = None
        self._scalar_bar_actor = None

        # 控件状态快照（播放/自动更新时冻结）
        self.field_selection = None
        self.colormap_selection = "Cool-Warm"
        self.auto_range_enabled = True
        self.user_min_val = 0.0
        self.user_max_val = 1.0
        self.vis_mode = "Surface"
        self.clip_axis = "Z"
        self.clip_position = 0.0
        self.contour_levels_text = ""
        self.default_opacity = 1.0
        self.show_axes = False
        self.show_bounds = False
        self.show_colorbar = False
        self.show_with_boundary = False
        self.glyph_enabled = False
        self.arrow_color_rgb = (1.0, 1.0, 1.0)
        self.color_arrows_by_mag = False
        self.plot_line_enabled = False

        # === Control Panel ===
        self._report_progress("   Creating VTS control panel...")
        control_panel = self._create_control_panel()
        control_panel.setFixedWidth(self.control_panel_width)

        # === VTK + Plot Tabs ===
        self._report_progress("   Creating VTK view and tabs...")
        self._create_vtk_and_tabs()  # 封装 VTK 和 Tab 创建逻辑

        self.tab_widget.setTabEnabled(1, False)  # 🔑 禁用/启用 tab
        main_layout.addWidget(control_panel)
        main_layout.addWidget(self.tab_widget)
        # vts files
        self.vts_folder = None
        self.vts_prefix = None
        self.vts_file_list = []          # 排序后的完整路径列表
        self.current_file_index = -1     # 当前播放索引
        self.auto_update_timer = None    # QTimer 用于自动刷新
        self.auto_update_enabled = False
        self.sequential_timer = None      # 用于顺序播放的 QTimer
        self.is_sequential_playing = False

        # 构造后台加载，双缓冲式播放
        self._report_progress("   Creating VTK render pipeline...")
        self.frame_buffer = queue.Queue(maxsize=2)  # 双缓冲
        self.playback_worker = None
        self.stop_playback_event = threading.Event()
        self._loaded_or_queued_indices = set()      # 已加载或已入队的帧索引
        self._loaded_indices_lock = threading.Lock()  # 保护集合的锁
        # 构造渲染管线：
        # lut 颜色控制
        self._current_colormap = None
        self._current_lut_range = None
        self.lut = vtk.vtkLookupTable()
        self._boundary_extract_filter = None
        # surface
        self.surface_mapper = vtk.vtkDataSetMapper()
        self.surface_actor = vtk.vtkActor()
        self.surface_actor.SetMapper(self.surface_mapper)
        self._is_surface_render_new = True
        # self.renderer.AddActor(self.surface_actor)
        # wire
        self.wire_mapper = vtk.vtkDataSetMapper()
        self.wire_actor = vtk.vtkActor()
        self.wire_actor.SetMapper(self.wire_mapper)
        prop = self.wire_actor.GetProperty()
        prop.SetRepresentationToWireframe()
        prop.SetColor(0.0, 0.0, 0.0)  # 黑色
        prop.SetLineWidth(1.0)         # 线宽
        prop.SetOpacity(1.0)          # 完全不透明
        self.wire_mapper.ScalarVisibilityOff()  # 关键：关闭标量着色，使用固定颜色
        self.wire_mapper.SetResolveCoincidentTopologyToPolygonOffset()# 解决 Z-fighting
        self.wire_mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-1, -1)#使浮于表面
        self._is_surface_wire_render_new = True
        # self.renderer.AddActor(self.wire_actor)
        self.wire_actor.GetProperty().SetRenderLinesAsTubes(False)  # 设置线的状态
        self.wire_actor.GetProperty().SetLighting(False)  # 关闭光照以获得纯黑色
        # clip
        self.plane = vtk.vtkPlane()
        self.clipper = vtk.vtkClipDataSet()
        self.clipper.SetClipFunction(self.plane)
        self.clipper.GenerateClipScalarsOff()
        self.clipper.GenerateClippedOutputOff()
        self.clip_mapper = vtk.vtkDataSetMapper()
        self.clip_mapper.SetInputConnection(self.clipper.GetOutputPort())
        self.clip_actor = vtk.vtkActor()
        self.clip_actor.SetMapper(self.clip_mapper)
        self._is_clip_render_new = True
        # self.renderer.AddActor(self.clip_actor)
        # contour
        self.contour_filter = vtk.vtkContourFilter()
        self.contour_mapper = vtk.vtkPolyDataMapper()
        self.contour_mapper.SetInputConnection(self.contour_filter.GetOutputPort())
        self.contour_actor = vtk.vtkActor()
        self.contour_actor.SetMapper(self.contour_mapper)
        # self.renderer.AddActor(self.contour_actor)
        self._is_contour_render_new = True
        # Arrows
        self.arrow_color = (1.0, 0.0, 0.0)
        self.glyph_arrow_source = vtk.vtkArrowSource()
        self.glyph_arrow_source.SetTipResolution(8)
        self.glyph_arrow_source.SetShaftResolution(8)
        self.glyph_arrow_source.SetTipLength(0.3)
        self.glyph_arrow_source.SetTipRadius(0.1)
        self.glyph_arrow_source.SetShaftRadius(0.03)
        self.glyph_filter = vtk.vtkGlyph3D()
        self.glyph_filter.SetSourceConnection(self.glyph_arrow_source.GetOutputPort())
        self.glyph_mapper = vtk.vtkPolyDataMapper()
        self.glyph_mapper.SetInputConnection(self.glyph_filter.GetOutputPort())
        self.glyph_actor = vtk.vtkActor()
        self.glyph_actor.SetMapper(self.glyph_mapper)
        # self.renderer.AddActor(self.glyph_actor)
        # 3. 重构 UI 设置
        self.update_colormap_preview()

    def _report_progress(self, detail: str):
        if self.progress_callback:
            self.progress_callback(detail)
