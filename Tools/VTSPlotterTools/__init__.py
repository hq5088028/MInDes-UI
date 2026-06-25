"""Multi-file VTS 3D plotting tool."""

from .models import VtsDatasetConfig, VtsPlotterState, VtkAxisConfig, VtkPlotConfig, VtkTextStyle

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
