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
    # tools 以包方式被 import, 这里保险起见显式列出
    'Tools',
    'Tools.CommonTangentTools',
    'Tools.CommonTangentTools.common_tangent_o3_gui',
    'Tools.FittingTools',
    'Tools.FittingTools.gibbs_fitter_gui',
    'Tools.FittingTools.fitter_core',
    # scipy 只用到这三个子模块 + 它们的依赖
    'scipy.spatial',
    'scipy.spatial.qhull',
    'scipy.interpolate',
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
    # scipy 不用到的重模块
    'scipy.stats',
    'scipy.optimize',
    'scipy.integrate',
    'scipy.signal',
    'scipy.sparse.csgraph',
    'scipy.sparse.linalg',
    'scipy.ndimage',
    'scipy.io',
    'scipy.fft',
    'scipy.fftpack',
    'scipy.odr',
    'scipy.cluster',
    'scipy.datasets',
    'scipy.misc',
    'scipy.special._ufuncs_cxx',  # 不是全部排掉, 只去掉确认没用的
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