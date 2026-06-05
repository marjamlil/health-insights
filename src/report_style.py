"""
Report design system.

A small, opinionated set of palette constants and composable matplotlib
helpers so the weekly and monthly reports share one visual language.

Design rules (deliberately restrained — the opposite of dashboard clutter):
  - One ink colour for text, one muted accent per section, one alert scale.
  - No filled cards. Whitespace and thin hairlines do the structuring.
  - Big confident numbers; small letter-spaced labels; minimal chart chrome.
"""

from __future__ import annotations

from typing import Optional, Sequence

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

INK = "#16161A"          # primary text / data
INK_2 = "#6E6E73"        # secondary text
INK_3 = "#A6A6AD"        # captions, axis ticks
HAIRLINE = "#E4E4EA"     # rules, gridlines, borders
PAPER = "#FFFFFF"

# One muted accent per section (wayfinding, used sparingly)
CARDIAC = "#D7263D"      # deep red
TRAINING = "#E07A1F"     # burnt orange
SLEEP = "#4F4FC4"        # indigo
ACTIVITY = "#2A9D5C"     # forest green

# Alert scale (status)
GOOD = "#2A9D5C"
WARN = "#E0A030"
BAD = "#D7263D"

STATUS = {"green": GOOD, "amber": WARN, "red": BAD,
          "good": GOOD, "ok": GOOD, "normal": GOOD,
          "caution": WARN, "suppressed": WARN, "low": BAD, "high": BAD}

# HR zone ramp (Z1 easy -> Z5 max), conventional cool->hot
ZONE_COLORS = ["#5AA9E6", "#2A9D5C", "#E0C030", "#E07A1F", "#D7263D"]
ZONE_LABELS = {1: "Z1 Recovery", 2: "Z2 Aerobic", 3: "Z3 Tempo",
               4: "Z4 Threshold", 5: "Z5 VO2max"}

LETTER = 8.5
PAGE_H = 11.0


# ---------------------------------------------------------------------------
# Base style
# ---------------------------------------------------------------------------

def apply_base_style() -> None:
    """Apply global rcParams. Call once before building a figure."""
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 9,
        "text.color": INK,
        "axes.edgecolor": HAIRLINE,
        "axes.labelcolor": INK_2,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": INK_3,
        "ytick.color": INK_3,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "figure.facecolor": PAPER,
        "axes.facecolor": PAPER,
        "grid.color": HAIRLINE,
        "grid.linewidth": 0.8,
        "lines.linewidth": 2.0,
        "lines.solid_capstyle": "round",
    })


def new_page():
    """Return a fresh Letter-size figure."""
    return plt.figure(figsize=(LETTER, PAGE_H))


# ---------------------------------------------------------------------------
# Page furniture
# ---------------------------------------------------------------------------

def add_header(fig, title: str, subtitle: str = "", accent: str = INK) -> None:
    """Flat colour band at the top of a page (no gradients)."""
    ax = fig.add_axes([0, 0.935, 1, 0.065])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, facecolor=accent, edgecolor="none"))
    ax.text(0.065, 0.56, title, ha="left", va="center",
            fontsize=17, fontweight="bold", color="white")
    if subtitle:
        ax.text(0.065, 0.18, subtitle.upper(), ha="left", va="center",
                fontsize=8.5, color="white", alpha=0.85,
                fontweight="medium")


def footer(fig, page_label: str = "") -> None:
    from datetime import datetime
    fig.text(0.065, 0.022, "HEALTH INSIGHTS", fontsize=7,
             color=INK_3, fontweight="medium")
    right = page_label if page_label else datetime.now().strftime("%d %b %Y")
    fig.text(0.935, 0.022, right, ha="right", fontsize=7, color=INK_3)


def section_label(fig, text: str, y: float, accent: str = INK,
                  x: float = 0.065) -> None:
    """Small letter-spaced section label with a short accent rule above it."""
    rule = fig.add_axes([x, y + 0.012, 0.04, 0.0035])
    rule.axis("off")
    rule.add_patch(plt.Rectangle((0, 0), 1, 1, facecolor=accent, edgecolor="none"))
    fig.text(x, y, _track(text.upper()), fontsize=10.5, fontweight="bold",
             color=INK, va="center")


def _track(s: str, spaces: int = 1) -> str:
    """Crude letter-spacing for labels (matplotlib lacks tracking)."""
    return (" " * spaces).join(list(s))


def hairline(fig, y: float, x0: float = 0.065, x1: float = 0.935) -> None:
    line = fig.add_axes([x0, y, x1 - x0, 0.0005])
    line.axis("off")
    line.add_patch(plt.Rectangle((0, 0), 1, 1, facecolor=HAIRLINE, edgecolor="none"))


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

def metric_tile(ax, label: str, value: str, unit: str = "",
                delta: Optional[str] = None, delta_color: str = INK_2,
                accent: str = INK) -> None:
    """A clean number tile: no fill, just a thin top rule and typography."""
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    # thin top rule in accent
    ax.plot([0, 0.32], [0.97, 0.97], color=accent, linewidth=2.4,
            solid_capstyle="butt", transform=ax.transAxes)
    ax.text(0, 0.84, label.upper(), fontsize=8, color=INK_2,
            fontweight="medium", va="center")
    ax.text(0, 0.42, value, fontsize=30, color=INK, fontweight="bold",
            va="center")
    if delta:
        ax.text(0.34, 0.52, delta, fontsize=10, color=delta_color,
                va="center", fontweight="bold")
    if unit:
        ax.text(0.002, 0.12, unit, fontsize=8.5, color=INK_3, va="center")


def hero_panel(fig, items: Sequence[dict], y: float = 0.80,
               h: float = 0.10) -> None:
    """Row of headline numbers. items: {label, value, unit, accent}."""
    n = len(items)
    gap = 0.02
    total = 0.87
    w = (total - gap * (n - 1)) / n
    x = 0.065
    for it in items:
        ax = fig.add_axes([x, y, w, h])
        metric_tile(ax, it["label"], it["value"], it.get("unit", ""),
                    it.get("delta"), it.get("delta_color", INK_2),
                    it.get("accent", INK))
        x += w + gap


def status_pill(fig, x: float, y: float, status: str, text: str) -> None:
    """Tinted rounded pill, text only (no bullet)."""
    color = STATUS.get(status, INK_2)
    ax = fig.add_axes([x, y, 0.30, 0.028])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    pill = FancyBboxPatch((0.02, 0.1), 0.96, 0.8,
                          boxstyle="round,pad=0.02,rounding_size=0.5",
                          facecolor=color, alpha=0.12, edgecolor="none")
    ax.add_patch(pill)
    ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=9.5,
            color=color, fontweight="bold")


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def style_axis(ax, ylabel: str = "", xlabel: str = "") -> None:
    """Consistent minimal axis: horizontal grid only, hairline spines."""
    ax.grid(axis="y", alpha=0.6)
    ax.grid(axis="x", visible=False)
    ax.set_axisbelow(True)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(HAIRLINE)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=8.5, color=INK_2)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=8.5, color=INK_2)


def chart_title(ax, title: str) -> None:
    """Title placed cleanly ABOVE the axis (never over the data)."""
    ax.set_title(title, fontsize=11, fontweight="bold", color=INK,
                 loc="left", pad=8)


def trend_with_baseline(ax, daily: pd.Series, rolling: pd.Series,
                        baseline: Optional[float], accent: str,
                        rolling_label: str = "7-day avg") -> None:
    """Faint daily series + bold rolling mean + dashed long-term baseline."""
    daily = daily.dropna()
    if not daily.empty:
        ax.plot(daily.index, daily.values, color=accent, linewidth=1.0,
                alpha=0.28, zorder=1)
    rolling = rolling.dropna()
    if not rolling.empty:
        ax.plot(rolling.index, rolling.values, color=accent, linewidth=2.4,
                zorder=3, label=rolling_label)
    if baseline is not None:
        ax.axhline(baseline, color=INK_3, linestyle=(0, (4, 3)),
                   linewidth=1.0, zorder=2, label="30-day baseline")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))


def sparkline(ax, series: pd.Series, accent: str = INK) -> None:
    """Minimal trend with no axes — for inline summary use."""
    ax.axis("off")
    s = series.dropna()
    if s.empty:
        return
    ax.plot(range(len(s)), s.values, color=accent, linewidth=1.6)
    ax.fill_between(range(len(s)), s.values, s.min(), alpha=0.08, color=accent)


def zone_bar(ax, zone_pct: dict, zone_minutes: Optional[dict] = None) -> None:
    """Horizontal stacked HR-zone distribution bar with a legend row."""
    ax.axis("off")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 1)
    left = 0.0
    for z in range(1, 6):
        pct = zone_pct.get(z, 0.0)
        if pct <= 0:
            continue
        ax.add_patch(plt.Rectangle((left, 0.45), pct, 0.4,
                                   facecolor=ZONE_COLORS[z - 1], edgecolor="white",
                                   linewidth=1.2))
        if pct >= 7:
            ax.text(left + pct / 2, 0.65, f"{pct:.0f}%", ha="center",
                    va="center", fontsize=8, color="white", fontweight="bold")
        left += pct
    # legend row beneath
    lx = 0.0
    for z in range(1, 6):
        ax.add_patch(plt.Rectangle((lx, 0.05), 2.0, 0.16,
                                   facecolor=ZONE_COLORS[z - 1], edgecolor="none"))
        ax.text(lx + 2.8, 0.13, ZONE_LABELS[z], fontsize=6.8, color=INK_2,
                va="center")
        lx += 20.0


def delta_str(curr, prev, unit: str = "", lower_is_better: bool = False):
    """Return (text, colour) for a value with its change vs prev."""
    if curr is None or pd.isna(curr):
        return ("--", INK_3)
    if prev is None or pd.isna(prev):
        return (f"{curr:.0f}{unit}", INK_2)
    d = curr - prev
    if abs(d) < 0.05:
        return (f"~ {unit}".strip(), INK_3)
    improved = (d < 0) if lower_is_better else (d > 0)
    sign = "+" if d > 0 else "−"
    return (f"{sign}{abs(d):.1f}{unit}", GOOD if improved else BAD)
