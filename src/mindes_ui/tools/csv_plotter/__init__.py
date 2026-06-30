"""Multi-file CSV plotting tool."""

from .models import CsvDatasetConfig, CsvPlotterState, VtkAxisConfig, VtkPlotConfig, VtkTextStyle

__all__ = ["CSVPlotterDialog", "CsvDatasetConfig", "CsvPlotterState", "VtkAxisConfig", "VtkPlotConfig", "VtkTextStyle"]


def __getattr__(name):
    if name == "CSVPlotterDialog":
        from .csv_plotter_gui import CSVPlotterDialog
        return CSVPlotterDialog
    raise AttributeError(name)
