"""Shared-axis publication rendering for multiple independent CSV series."""
from __future__ import annotations

import shutil

import numpy as np
from matplotlib import ticker


def font_kwargs(style):
    return dict(fontfamily=style.font, fontsize=style.size,
                fontweight="bold" if style.bold else "normal",
                fontstyle="italic" if style.italic else "normal", color=style.color)


def apply_locator_formatter(axis, style):
    tick = style.tick
    if tick.manual_mode == "Positions":
        values = [float(value.strip()) for value in tick.positions.split(",") if value.strip()]
        if values:
            axis.set_major_locator(ticker.FixedLocator(values))
    elif tick.manual_mode == "Start/Stop/Step" and tick.step > 0:
        count = int(np.floor((tick.stop - tick.start) / tick.step)) + 1
        if count > 10000:
            raise ValueError("Manual tick range creates too many ticks.")
        axis.set_major_locator(ticker.FixedLocator(tick.start + np.arange(max(0, count)) * tick.step))
    if tick.minor_visible:
        if style.scale == "Linear":
            axis.set_minor_locator(ticker.AutoMinorLocator())
        elif style.scale == "SymLog":
            axis.set_minor_locator(ticker.SymmetricalLogLocator(base=10, linthresh=1.0, subs=np.arange(2, 10)))
        else:
            axis.set_minor_locator(ticker.LogLocator(subs="auto"))
    else:
        axis.set_minor_locator(ticker.NullLocator())
    if tick.format_mode == "Fixed":
        axis.set_major_formatter(ticker.FormatStrFormatter(f"%.{tick.decimals}f"))
    elif tick.format_mode == "Scientific":
        formatter = ticker.ScalarFormatter(useMathText=True); formatter.set_scientific(True); formatter.set_powerlimits((0, 0))
        axis.set_major_formatter(formatter)
    elif tick.format_mode == "Percent":
        axis.set_major_formatter(ticker.PercentFormatter(xmax=1.0, decimals=tick.decimals))


def apply_scale(ax, style, dimension):
    scale = {"Linear": "linear", "Log10": "log", "SymLog": "symlog"}.get(style.scale, "linear")
    (ax.set_xscale if dimension == "x" else ax.set_yscale)(scale)
    if not style.auto_range:
        (ax.set_xlim if dimension == "x" else ax.set_ylim)(style.minimum, style.maximum)
    if style.inverted:
        (ax.invert_xaxis if dimension == "x" else ax.invert_yaxis)()
    apply_locator_formatter(ax.xaxis if dimension == "x" else ax.yaxis, style)


def render_shared_figure(figure, config, series):
    """Render series dictionaries containing key, label, x, y and optional errors."""
    figure.clear()
    transparent = config.background == "Transparent"
    figure.patch.set_facecolor("none" if transparent else "white")
    figure.patch.set_alpha(0.0 if transparent else 1.0)
    figure.set_size_inches(config.width_cm / 2.54, config.height_cm / 2.54, forward=False)
    left, right = config.margin_left_cm / config.width_cm, 1 - config.margin_right_cm / config.width_cm
    bottom, top = config.margin_bottom_cm / config.height_cm, 1 - config.margin_top_cm / config.height_cm
    if not (0 <= left < right <= 1 and 0 <= bottom < top <= 1):
        raise ValueError("Figure margins leave no plotting area.")
    figure.subplots_adjust(left=left, right=right, bottom=bottom, top=top)
    ax = figure.add_subplot(111)
    xstyle, ystyle = config.x_axis, config.shared_y_axis
    apply_scale(ax, xstyle, "x"); apply_scale(ax, ystyle, "y")
    latex = bool(config.use_latex and shutil.which("latex"))
    if config.use_latex and not latex:
        config.use_latex = False

    curve_map = {curve.column: curve for curve in config.curves}
    handles, labels = [], []
    for item in series:
        curve = curve_map.get(item["key"])
        if curve is None or not curve.visible:
            continue
        x, y = np.asarray(item["x"], float), np.asarray(item["y"], float)
        marker = "" if curve.marker == "None" else curve.marker
        linestyle = "" if curve.linestyle == "None" else curve.linestyle
        line, = ax.plot(x, y, color=curve.color, linewidth=curve.linewidth, linestyle=linestyle,
                        marker=marker, markersize=curve.markersize,
                        markerfacecolor=curve.marker_face_color, markeredgecolor=curve.marker_edge_color,
                        markeredgewidth=curve.marker_edge_width, markevery=max(1, curve.markevery),
                        label=curve.legend_text or item["label"])
        handles.append(line); labels.append(curve.legend_text or item["label"])
        error = curve.error
        error_values = item.get("errors", {}).get(error.column) if error.source == "Column" else None
        if error.source == "Constant":
            error_values = np.full_like(y, error.constant, dtype=float)
        if error.mode != "None" and error_values is not None:
            err = np.asarray(error_values, float)
            if np.any(err[np.isfinite(err)] < 0):
                raise ValueError(f"{item['label']}: error values must be non-negative.")
            if error.mode in ("Bars", "Bars + Band"):
                ax.errorbar(x, y, yerr=err, fmt="none", errorevery=max(1, error.every), ecolor=error.color,
                            elinewidth=error.linewidth, capsize=error.capsize, capthick=error.capthick)
            if error.mode in ("Band", "Bars + Band"):
                ax.fill_between(x, y - err, y + err, color=error.fill_color, alpha=error.fill_alpha, linewidth=0)

    if config.title.visible and config.title.text:
        text = ax.set_title(config.title.text, **font_kwargs(config.title)); text.set_usetex(latex)
    if xstyle.label.visible:
        text = ax.set_xlabel(xstyle.label.text or "X", **font_kwargs(xstyle.label)); text.set_usetex(latex)
    if ystyle.label.visible:
        text = ax.set_ylabel(ystyle.label.text or "Y", **font_kwargs(ystyle.label)); text.set_usetex(latex)
    for dimension, style in (("x", xstyle), ("y", ystyle)):
        tick = style.tick
        kwargs = dict(which="major", direction=tick.direction, length=tick.major_length,
                      width=tick.width, colors=tick.color)
        if dimension == "x":
            ax.tick_params(axis="x", bottom=tick.major_visible and tick.show_bottom,
                           top=tick.major_visible and tick.show_top, **kwargs)
            ax.tick_params(axis="x", which="minor", bottom=tick.minor_visible and tick.show_bottom,
                           top=tick.minor_visible and tick.show_top, direction=tick.direction,
                           length=tick.minor_length, width=tick.width, colors=tick.color)
            labels_to_style = ax.get_xticklabels()
        else:
            ax.tick_params(axis="y", left=tick.major_visible and tick.show_left,
                           right=tick.major_visible and tick.show_right, **kwargs)
            ax.tick_params(axis="y", which="minor", left=tick.minor_visible and tick.show_left,
                           right=tick.minor_visible and tick.show_right, direction=tick.direction,
                           length=tick.minor_length, width=tick.width, colors=tick.color)
            labels_to_style = ax.get_yticklabels()
        for label in labels_to_style:
            label.update(font_kwargs(tick.font)); label.set_usetex(latex)
        grid = style.grid
        ax.grid(grid.visible, axis=dimension, which="major",
                **({"color": grid.color, "linestyle": grid.linestyle,
                    "linewidth": grid.linewidth, "alpha": grid.alpha} if grid.visible else {}))
    for name, visible in (("top", config.show_top_spine), ("bottom", config.show_bottom_spine),
                          ("left", config.show_left_spine), ("right", config.show_right_spine)):
        ax.spines[name].set_visible(visible)
        style = xstyle if name in ("top", "bottom") else ystyle
        ax.spines[name].set_linewidth(style.spine_width); ax.spines[name].set_color(style.spine_color)
    if config.legend.visible and handles:
        kwargs = dict(loc=config.legend.location, ncol=config.legend.columns, frameon=config.legend.frame_visible,
                      facecolor=config.legend.face_color, edgecolor=config.legend.edge_color,
                      framealpha=config.legend.frame_alpha,
                      prop={"family": config.legend.font.font, "size": config.legend.font.size,
                            "weight": "bold" if config.legend.font.bold else "normal",
                            "style": "italic" if config.legend.font.italic else "normal"})
        if config.legend.custom_anchor:
            kwargs["bbox_to_anchor"] = (config.legend.anchor_x, config.legend.anchor_y)
        legend = ax.legend(handles, labels, **kwargs)
        for text in legend.get_texts():
            text.set_color(config.legend.font.color); text.set_usetex(latex)
    return ax
