# MInDes.spec
# Single-entry onedir build for MInDes-UI with embedded tools.
#
# Build command:
#   pyinstaller MInDes.spec --noconfirm

# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

from PyInstaller.utils.hooks import collect_data_files

# ---------------------------------------------------------------------------
# Runtime resources
# ---------------------------------------------------------------------------
datas = [
    ('icon', 'icon'),
] + collect_data_files(
    'PySide6',
    includes=[
        'translations/qt_zh_CN.qm', 'translations/qtbase_zh_CN.qm',
        'translations/qt_zh_TW.qm', 'translations/qtbase_zh_TW.qm',
        'translations/qt_de.qm', 'translations/qtbase_de.qm',
        'translations/qt_fr.qm', 'translations/qtbase_fr.qm',
        'translations/qt_es.qm', 'translations/qtbase_es.qm',
        'translations/qt_ru.qm', 'translations/qtbase_ru.qm',
        'translations/qt_ko.qm', 'translations/qtbase_ko.qm',
        'translations/qt_ja.qm', 'translations/qtbase_ja.qm',
    ],
)

# ---------------------------------------------------------------------------
# Hidden imports PyInstaller sometimes misses
# ---------------------------------------------------------------------------
hiddenimports = [
    'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
    'vtkmodules.all',
    'vtkmodules.qt.QVTKRenderWindowInteractor',
    'matplotlib.backends.backend_qtagg',
    'openpyxl',
    'mindes_ui.i18n',
    'mindes_ui.i18n.manager',
    'mindes_ui.i18n.en',
    'mindes_ui.i18n.zh_cn',
    'mindes_ui.i18n.zh_tw',
    'mindes_ui.i18n.de',
    'mindes_ui.i18n.fr',
    'mindes_ui.i18n.es',
    'mindes_ui.i18n.ru',
    'mindes_ui.i18n.ko',
    'mindes_ui.i18n.ja',
    # tools 以包方式被 import, 这里保险起见显式列出
    'mindes_ui.tools',
    'mindes_ui.tools.csv_plotter',
    'mindes_ui.tools.csv_plotter.models',
    'mindes_ui.tools.csv_plotter.dataset_card',
    'mindes_ui.tools.csv_plotter.style_formats',
    'mindes_ui.tools.csv_plotter.rendering',
    'mindes_ui.tools.csv_plotter.vtk_utils',
    'mindes_ui.tools.csv_plotter.vtk_properties',
    'mindes_ui.tools.csv_plotter.csv_plotter_gui',
    'mindes_ui.tools.common_tangent',
    'mindes_ui.tools.common_tangent.common_tangent_o3_gui',
    'mindes_ui.tools.common_tangent.common_tangent_core',
    'mindes_ui.tools.fitting',
    'mindes_ui.tools.fitting.gibbs_fitter_gui',
    'mindes_ui.tools.fitting.fitter_core',
    'mindes_ui.tools.vts_plotter',
    'mindes_ui.tools.vts_plotter.models',
    'mindes_ui.tools.vts_plotter.dataset_card',
    'mindes_ui.tools.vts_plotter.style_formats',
    'mindes_ui.tools.vts_plotter.visualization',
    'mindes_ui.tools.vts_plotter.vtk_utils',
    'mindes_ui.tools.vts_plotter.vtk_properties',
    'mindes_ui.tools.vts_plotter.vts_plotter_gui',
    'mindes_ui.vts_viewer',
    'mindes_ui.vts_viewer.models',
    'mindes_ui.vts_viewer.data_loader',
    'mindes_ui.vts_viewer.ui_vtk_view',
    'mindes_ui.vts_viewer.ui_control_panel',
    'mindes_ui.vts_viewer.visualization',
    'mindes_ui.vts_viewer.ui_plot_over_line',
    'mindes_ui.vts_viewer.utils',
]

# ---------------------------------------------------------------------------
# Hard excludes — cut size aggressively.
# Keep this list conservative: only exclude what we are SURE we don't use.
# ---------------------------------------------------------------------------
excludes = [
    # Tk 栈 (已不再使用 Tkinter)
    'tkinter', '_tkinter', 'Tkinter',
    # PyVista 栈 (已改用原生 VTK)
    'pyvista', 'pyvistaqt',
    # matplotlib 的非 Qt 后端
    'matplotlib.backends.backend_tkagg',
    'matplotlib.backends.backend_tkcairo',
    'matplotlib.backends.backend_wx',
    'matplotlib.backends.backend_wxagg',
    'matplotlib.backends.backend_gtk3agg',
    'matplotlib.backends.backend_gtk4agg',
    'matplotlib.backends.backend_webagg',
    'matplotlib.backends.backend_nbagg',
    # Jupyter / IPython (无关)
    'IPython', 'ipykernel', 'ipython_genutils', 'jupyter',
    'notebook', 'nbformat', 'nbconvert',
    'matplotlib.sphinxext',
    # 其他常见体积大但 MInDes-UI 不用的东西
    'sympy', 'numba', 'llvmlite',
    'sphinx', 'docutils',
    'pytest', 'nose', 'unittest2',
]

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    ['src/mindes_ui/app.py'],
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='MInDes-UI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='icon/mid.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MInDes-UI',
)
