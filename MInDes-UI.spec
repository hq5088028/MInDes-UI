# MInDes.spec
# Single-entry onedir build for MInDes-UI with embedded tools.
#
# Build command:
#   pyinstaller MInDes.spec --noconfirm

# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# ---------------------------------------------------------------------------
# Runtime resources
# ---------------------------------------------------------------------------
datas = [
    ('icon', 'icon'),
]

# ---------------------------------------------------------------------------
# Hidden imports PyInstaller sometimes misses
# ---------------------------------------------------------------------------
hiddenimports = [
    'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
    'vtkmodules.all',
    'vtkmodules.qt.QVTKRenderWindowInteractor',
    'matplotlib.backends.backend_qtagg',
    'openpyxl',
    # tools 以包方式被 import, 这里保险起见显式列出
    'Tools',
    'Tools.CSVPlotterTools',
    'Tools.CSVPlotterTools.models',
    'Tools.CSVPlotterTools.dataset_card',
    'Tools.CSVPlotterTools.style_formats',
    'Tools.CSVPlotterTools.rendering',
    'Tools.CSVPlotterTools.vtk_utils',
    'Tools.CSVPlotterTools.vtk_properties',
    'Tools.CSVPlotterTools.csv_plotter_gui',
    'Tools.CommonTangentTools',
    'Tools.CommonTangentTools.common_tangent_o3_gui',
    'Tools.CommonTangentTools.common_tangent_core',
    'Tools.FittingTools',
    'Tools.FittingTools.gibbs_fitter_gui',
    'Tools.FittingTools.fitter_core',
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
    ['MInDes-UI.py'],
    pathex=['.'],
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
