# -*- mode: python ; coding: utf-8 -*-
"""
MInDes-UI.spec

放置位置：项目根目录（与 MInDes-UI.py 同级）
构建命令：pyinstaller --clean --noconfirm MInDes-UI.spec

说明：
1) 这是针对当前项目的 onedir 封装方案；
2) solver/ 不打进 PyInstaller 内部，构建后请手动复制到 dist/MInDes-UI/ 同级；
3) icon/mid.ico 与 icon/logo.png 若存在会自动打包；不存在也不会导致 spec 构建失败；
4) 该 spec 假定你本地真实项目里 vts_viewer/ 包结构是完整的。
"""

from pathlib import Path
from PyInstaller.utils.hooks import (
    collect_submodules,
    collect_data_files,
    collect_dynamic_libs,
)


PROJECT_ROOT = Path(SPECPATH).resolve()
ENTRY_SCRIPT = PROJECT_ROOT / "MInDes-UI.py"
APP_NAME = "MInDes-UI"
ICON_DIR = PROJECT_ROOT / "icon"
ICON_FILE = ICON_DIR / "mid.ico"
LOGO_FILE = ICON_DIR / "logo.png"

if not ENTRY_SCRIPT.exists():
    raise FileNotFoundError(f"Entry script not found: {ENTRY_SCRIPT}")


def _safe_collect_submodules(pkg_name: str):
    try:
        return collect_submodules(pkg_name)
    except Exception:
        return []


def _safe_collect_data_files(pkg_name: str):
    try:
        return collect_data_files(pkg_name)
    except Exception:
        return []


def _safe_collect_dynamic_libs(pkg_name: str):
    try:
        return collect_dynamic_libs(pkg_name)
    except Exception:
        return []


# -------------------------
# Data files
# -------------------------
datas = []

# 项目资源：图标 / logo
if ICON_FILE.exists():
    datas.append((str(ICON_FILE), "icon"))
if LOGO_FILE.exists():
    datas.append((str(LOGO_FILE), "icon"))

# matplotlib 运行时资源（字体、mpl-data 等）
datas += _safe_collect_data_files("matplotlib")


# -------------------------
# Binary files / dynamic libs
# -------------------------
binaries = []

# VTK 动态库；不同环境里可能挂在 vtk 或 vtkmodules 名下，双保险
binaries += _safe_collect_dynamic_libs("vtk")
binaries += _safe_collect_dynamic_libs("vtkmodules")


# -------------------------
# Hidden imports
# -------------------------
hiddenimports = [
    # 明确的动态/间接导入
    "matplotlib.backends.backend_qtagg",
    "openpyxl",
    "vtkmodules.qt.QVTKRenderWindowInteractor",

    # 主模块
    "build_simulation_widget",
    "file_browser_widget",
    "log_statistics_widget",
    "vts_viewer_widget",
]

# 如果本地项目中存在 vts_viewer/ 包，则补齐其子模块
VTS_PACKAGE_DIR = PROJECT_ROOT / "vts_viewer"
if VTS_PACKAGE_DIR.is_dir():
    hiddenimports += [
        "vts_viewer",
        "vts_viewer.data_loader",
        "vts_viewer.models",
        "vts_viewer.ui_control_panel",
        "vts_viewer.ui_plot_over_line",
        "vts_viewer.ui_vtk_view",
        "vts_viewer.utils",
        "vts_viewer.visualization",
    ]

# 对 VTK / matplotlib 后端做递归补全，减少漏包概率
hiddenimports += _safe_collect_submodules("vtkmodules")
hiddenimports += _safe_collect_submodules("matplotlib.backends")

# 去重并排序，方便排查
hiddenimports = sorted(set(hiddenimports))


# -------------------------
# Excludes
# -------------------------
excludes = [
    "tkinter",
    "test",
    "tests",
    "unittest",
    "pytest",
    "IPython",
    "jupyter_client",
    "jupyter_core",
    "notebook",
]


# -------------------------
# Analysis
# -------------------------
a = Analysis(
    [str(ENTRY_SCRIPT)],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ICON_FILE) if ICON_FILE.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)