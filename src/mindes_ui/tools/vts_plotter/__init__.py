"""Multi-file VTS 3D plotting tool."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import (
    VtsDatasetConfig,
    VtsPlotterState,
    VtkAxisConfig,
    VtkPlotConfig,
    VtkTextStyle,
)

if TYPE_CHECKING:
    from .vts_plotter_gui import VTSPlotterDialog

__all__ = [
    "VTSPlotterDialog",
    "VtsDatasetConfig",
    "VtsPlotterState",
    "VtkAxisConfig",
    "VtkPlotConfig",
    "VtkTextStyle",
]


def __getattr__(name):
    if name == "VTSPlotterDialog":
        from .vts_plotter_gui import VTSPlotterDialog

        return VTSPlotterDialog
    raise AttributeError(name)
