"""
Monthly Health Report — redesigned.

Editorial layout: restrained, high whitespace, confident typography.
4 pages: Overview, Cardiac, Training, Sleep & Activity.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_pdf import PdfPages

from . import report_style as rs
from . import analytics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe(val, fmt=".0f", fallback="--"):
    """Format a numeric value safely, returning fallback on None/NaN."""
    if val is None:
        return fallback
    try:
        if pd.isna(val):
            return fallback
    except (TypeError, ValueError):
        pass
    return format(val, fmt)


def _filter_month(df: pd.DataFrame, month_start: datetime, month_end: datetime) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    return df[(df.index >= month_start) & (df.index < month_end)]


def _stat_line(ax, items: list[tuple], y_start: float, row_h: float = 0.055,
               x_label: float = 0.0, x_value: float = 0.60) -> None:
    """
    Draw aligned stat rows (label | value) on a bare axes.
    items: list of (label, value_str, color_opt)
    """
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    for i, item in enumerate(items):
        label = item[0]
        value = item[1]
        color = item[2] if len(item) > 2 else rs.INK
        y = y_start - i * row_h
        ax.text(x_label, y, label, fontsize=9.5, color=rs.INK_2, va="center")
        ax.text(x_value, y, value, fontsize=9.5, color=color, va="center",
                fontweight="bold")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_monthly_report(
    month_summary: dict,
    prev_month_summary: dict,
    daily_metrics: pd.DataFrame,
    daily_load: pd.DataFrame,
    sleep_df: pd.DataFrame,
    workouts_df: pd.DataFrame,
    readiness,
    anomalies: list,
    baselines: dict,
    config: dict,
    output_path: Path,
) -> Path:
    """
    Generate a 4-page editorial monthly PDF report.

    Pages: Overview | Cardiac | Training | Sleep & Activity
    """
    rs.apply_base_style()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    month_start: datetime = month_summary.get("month_start", datetime.now().replace(day=1))
    month_end: datetime = month_summary.get("month_end", datetime.now())
    month_name: str = month_start.strftime("%B %Y")

    # Convenience filters
    m_metrics = _filter_month(daily_metrics, month_start, month_end)
    m_load = _filter_month(daily_load, month_start, month_end)
    m_sleep = _filter_month(sleep_df, month_start, month_end)

    # Month-filtered anomalies (whole-history list passed in)
    m_anomalies = [a for a in (anomalies or [])
                   if month_start <= a["date"] < month_end]

    with PdfPages(output_path) as pdf:

        # ================================================================
        # PAGE 1 — OVERVIEW
        # ================================================================
        fig = rs.new_page()
        rs.add_header(fig, f"Monthly Report — {month_name}", "Health Insights", accent=rs.INK)

        # --- Hero panel -----------------------------------------------
        rhr_curr = month_summary.get("resting_hr_mean")
        rhr_prev = prev_month_summary.get("resting_hr_mean") if prev_month_summary else None
        hrv_curr = month_summary.get("hrv_mean")
        hrv_prev = prev_month_summary.get("hrv_mean") if prev_month_summary else None
        slp_curr = month_summary.get("total_sleep_mean")
        slp_prev = prev_month_summary.get("total_sleep_mean") if prev_month_summary else None
        wkt_curr = month_summary.get("workout_count")

        rhr_d, rhr_dc = rs.delta_str(rhr_curr, rhr_prev, "", lower_is_better=True)
        hrv_d, hrv_dc = rs.delta_str(hrv_curr, hrv_prev, "", lower_is_better=False)
        slp_d, slp_dc = rs.delta_str(slp_curr, slp_prev, "", lower_is_better=False)

        hero_items = [
            {"label": "Avg Resting HR", "value": _safe(rhr_curr), "unit": "bpm",
             "delta": rhr_d, "delta_color": rhr_dc, "accent": rs.CARDIAC},
            {"label": "Avg HRV", "value": _safe(hrv_curr), "unit": "ms",
             "delta": hrv_d, "delta_color": hrv_dc, "accent": rs.SLEEP},
            {"label": "Avg Sleep", "value": _safe(slp_curr, ".1f"), "unit": "h",
             "delta": slp_d, "delta_color": slp_dc, "accent": rs.SLEEP},
            {"label": "Workouts", "value": _safe(wkt_curr), "unit": "sessions",
             "accent": rs.TRAINING},
        ]
        rs.hero_panel(fig, hero_items, y=0.800, h=0.095)

        # --- Notable This Month ----------------------------------------
        rs.hairline(fig, y=0.770)
        rs.section_label(fig, "Notable This Month", y=0.740, accent=rs.INK)

        events = analytics.notable_events(
            daily_metrics, daily_load, sleep_df, month_start, month_end
        )

        ax_ev = fig.add_axes([0.065, 0.580, 0.870, 0.145])
        ax_ev.axis("off")
        ax_ev.set_xlim(0, 1)
        ax_ev.set_ylim(0, 1)
        if events:
            n = len(events)
            row_h = min(0.16, 0.90 / max(n, 1))
            for i, ev in enumerate(events):
                y_pos = 0.92 - i * row_h
                ax_ev.text(0.0, y_pos, "—", fontsize=9.5, color=rs.INK_3, va="center")
                ax_ev.text(0.03, y_pos, ev, fontsize=9.5, color=rs.INK_2, va="center")
        else:
            ax_ev.text(0.0, 0.5, "No notable events detected.", fontsize=9.5,
                       color=rs.INK_3, va="center")

        # --- Versus Last Month -----------------------------------------
        rs.hairline(fig, y=0.560)
        rs.section_label(fig, "Versus Last Month", y=0.530, accent=rs.INK)

        # Build comparison rows
        compare_rows = []
        metrics_cfg = [
            ("Resting HR", "resting_hr_mean", "bpm", True),
            ("HRV", "hrv_mean", "ms", False),
            ("Avg Sleep", "total_sleep_mean", "h", False),
            ("Training Load (TSS)", "total_tss", "", False),
        ]
        for label, key, unit, lib in metrics_cfg:
            curr = month_summary.get(key)
            prev = prev_month_summary.get(key) if prev_month_summary else None
            if curr is None:
                val_str = "--"
                chg_str = ""
                chg_col = rs.INK_3
            else:
                fmt = ".1f" if unit in ("h", "ms") else ".0f"
                val_str = f"{_safe(curr, fmt)} {unit}".strip()
                chg_str, chg_col = rs.delta_str(curr, prev, unit, lower_is_better=lib)
            compare_rows.append((label, val_str, chg_str, chg_col))

        ax_cmp = fig.add_axes([0.065, 0.360, 0.870, 0.155])
        ax_cmp.axis("off")
        ax_cmp.set_xlim(0, 1)
        ax_cmp.set_ylim(0, 1)
        row_h_c = 0.22
        for i, (lbl, val, chg, ccol) in enumerate(compare_rows):
            y_c = 0.88 - i * row_h_c
            ax_cmp.text(0.0, y_c, lbl, fontsize=9.5, color=rs.INK_2, va="center")
            ax_cmp.text(0.48, y_c, val, fontsize=9.5, color=rs.INK, va="center",
                        fontweight="bold")
            if chg:
                ax_cmp.text(0.72, y_c, chg, fontsize=9.5, color=ccol, va="center",
                            fontweight="bold")
            # subtle separator line
            if i < len(compare_rows) - 1:
                ax_cmp.axhline(y_c - row_h_c * 0.45, color=rs.HAIRLINE, linewidth=0.6,
                               xmin=0, xmax=1)

        # --- Flags -------------------------------------------------------
        rs.hairline(fig, y=0.340)
        rs.section_label(fig, "Flags", y=0.310, accent=rs.CARDIAC if m_anomalies else rs.INK)

        ax_fl = fig.add_axes([0.065, 0.075, 0.870, 0.220])
        ax_fl.axis("off")
        ax_fl.set_xlim(0, 1)
        ax_fl.set_ylim(0, 1)
        if m_anomalies:
            row_h_f = min(0.16, 0.90 / max(len(m_anomalies), 1))
            for i, a in enumerate(m_anomalies[:6]):
                y_f = 0.92 - i * row_h_f
                date_str = pd.Timestamp(a["date"]).strftime("%-d %b")
                sev_col = rs.BAD if a.get("severity") == "high" else rs.WARN
                ax_fl.text(0.0, y_f, date_str, fontsize=8.5, color=rs.INK_3, va="center")
                ax_fl.text(0.10, y_f, a.get("metric", ""), fontsize=8.5,
                           color=sev_col, va="center", fontweight="bold")
                ax_fl.text(0.28, y_f, a.get("description", ""), fontsize=8.5,
                           color=rs.INK_2, va="center")
        else:
            ax_fl.text(0.0, 0.5, "No anomalies flagged this month.", fontsize=9.5,
                       color=rs.INK_3, va="center")

        rs.footer(fig, "Page 1")
        pdf.savefig(fig, facecolor="white")
        plt.close(fig)

        # ================================================================
        # PAGE 2 — CARDIAC
        # ================================================================
        fig = rs.new_page()
        rs.add_header(fig, "Cardiac", month_name, accent=rs.CARDIAC)

        # --- Resting HR chart ------------------------------------------
        rs.section_label(fig, "Resting Heart Rate", y=0.875, accent=rs.CARDIAC)
        ax_rhr = fig.add_axes([0.095, 0.730, 0.840, 0.130])
        rhr_series = (m_metrics["resting_hr"].dropna()
                      if not m_metrics.empty and "resting_hr" in m_metrics.columns
                      else pd.Series(dtype=float))
        rhr_rolling = (daily_metrics["resting_hr"].rolling(7, min_periods=3).mean()
                       .loc[m_metrics.index] if not rhr_series.empty else pd.Series(dtype=float))
        rhr_baseline = (baselines.get("resting_hr", {}).get("recent_mean")
                        if baselines else None)
        if not rhr_series.empty:
            rs.trend_with_baseline(ax_rhr, rhr_series, rhr_rolling, rhr_baseline,
                                   rs.CARDIAC, rolling_label="7-day avg")
            ax_rhr.legend(fontsize=7.5, loc="upper right", frameon=False)
        rs.style_axis(ax_rhr, ylabel="bpm")

        # --- HRV chart --------------------------------------------------
        rs.section_label(fig, "Heart Rate Variability", y=0.685, accent=rs.SLEEP)
        ax_hrv = fig.add_axes([0.095, 0.540, 0.840, 0.130])
        hrv_df, hrv_status = analytics.hrv_rolling(daily_metrics)
        hrv_daily_month = (hrv_df["hrv"].loc[
            (hrv_df.index >= month_start) & (hrv_df.index < month_end)
        ] if not hrv_df.empty else pd.Series(dtype=float))
        hrv_7d_month = (hrv_df["hrv_7d"].loc[
            (hrv_df.index >= month_start) & (hrv_df.index < month_end)
        ] if not hrv_df.empty else pd.Series(dtype=float))
        hrv_baseline_val = float(hrv_df["hrv_30d"].dropna().iloc[-1]) if (
            not hrv_df.empty and not hrv_df["hrv_30d"].dropna().empty) else None

        if not hrv_daily_month.empty:
            rs.trend_with_baseline(ax_hrv, hrv_daily_month, hrv_7d_month,
                                   hrv_baseline_val, rs.SLEEP, rolling_label="7-day avg")
            ax_hrv.legend(fontsize=7.5, loc="upper right", frameon=False)
            # HRV status pill
            if hrv_status in ("suppressed", "normal"):
                pill_text = "HRV suppressed" if hrv_status == "suppressed" else "HRV normal"
                pill_status = "caution" if hrv_status == "suppressed" else "good"
                rs.status_pill(fig, x=0.65, y=0.665, status=pill_status, text=pill_text)
        rs.style_axis(ax_hrv, ylabel="ms")

        # --- VO2 Max chart ----------------------------------------------
        rs.section_label(fig, "VO2 Max", y=0.495, accent=rs.TRAINING)
        ax_vo2 = fig.add_axes([0.095, 0.350, 0.840, 0.130])
        vo2_series = (m_metrics["vo2_max"].dropna()
                      if not m_metrics.empty and "vo2_max" in m_metrics.columns
                      else pd.Series(dtype=float))
        if not vo2_series.empty:
            vo2_smooth = vo2_series.rolling(7, min_periods=2).mean()
            ax_vo2.plot(vo2_smooth.index, vo2_smooth.values,
                        color=rs.TRAINING, linewidth=2.4, zorder=3)
            ax_vo2.plot(vo2_series.index, vo2_series.values,
                        color=rs.TRAINING, linewidth=1.0, alpha=0.28, zorder=1)
            ax_vo2.set_ylim(40, 60)
            ax_vo2.xaxis.set_major_formatter(mdates.DateFormatter("%d"))
            ax_vo2.xaxis.set_major_locator(mdates.DayLocator(interval=5))
        rs.style_axis(ax_vo2, ylabel="ml/kg/min")
        fig.text(0.095, 0.342, "Apple Watch VO2 Max estimates carry ±2–3 ml/kg/min noise; "
                 "y-axis fixed at 40–60 to avoid over-reading small changes.",
                 fontsize=7.5, color=rs.INK_3)

        # --- Multi-year cardiac trajectory -----------------------------
        rs.hairline(fig, y=0.320)
        rs.section_label(fig, "Multi-Year Cardiac Trajectory", y=0.292, accent=rs.INK)
        ax_yoy = fig.add_axes([0.095, 0.115, 0.840, 0.165])
        yoy = analytics.yoy_cardiac(daily_metrics)
        if not yoy.empty and len(yoy) >= 3:
            ax2_yoy = ax_yoy.twinx()
            if "resting_hr" in yoy.columns and yoy["resting_hr"].notna().any():
                ax_yoy.plot(yoy.index, yoy["resting_hr"], color=rs.CARDIAC,
                            linewidth=2.2, label="Resting HR (left)")
                ax_yoy.set_ylabel("bpm", fontsize=8.5, color=rs.CARDIAC)
                ax_yoy.tick_params(axis="y", colors=rs.CARDIAC, labelsize=7.5)
            if "hrv" in yoy.columns and yoy["hrv"].notna().any():
                ax2_yoy.plot(yoy.index, yoy["hrv"], color=rs.SLEEP,
                             linewidth=2.2, linestyle="--", label="HRV (right)")
                ax2_yoy.set_ylabel("ms (HRV)", fontsize=8.5, color=rs.SLEEP)
                ax2_yoy.tick_params(axis="y", colors=rs.SLEEP, labelsize=7.5)
            ax_yoy.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            ax_yoy.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
            plt.setp(ax_yoy.xaxis.get_majorticklabels(), rotation=30, ha="right",
                     fontsize=7.5)
            # Combined legend
            lines_a = ax_yoy.get_lines()
            lines_b = ax2_yoy.get_lines()
            ax_yoy.legend(lines_a + lines_b,
                          [l.get_label() for l in lines_a + lines_b],
                          fontsize=7.5, loc="upper right", frameon=False)
            rs.style_axis(ax_yoy)
            for s in ("top", "right"):
                ax2_yoy.spines[s].set_visible(False)
            ax2_yoy.spines["left"].set_color(rs.HAIRLINE)
            ax2_yoy.spines["bottom"].set_color(rs.HAIRLINE)
        else:
            ax_yoy.text(0.5, 0.5, "Insufficient history for trajectory chart.",
                        ha="center", va="center", fontsize=9.5, color=rs.INK_3,
                        transform=ax_yoy.transAxes)
            ax_yoy.axis("off")

        # Cardiac stats line
        rhr_mean = month_summary.get("resting_hr_mean")
        rhr_std = month_summary.get("resting_hr_std")
        hrv_mean = month_summary.get("hrv_mean")
        hrv_std = month_summary.get("hrv_std")
        vo2_mean = month_summary.get("vo2_max_mean")
        vo2_std = month_summary.get("vo2_max_std")
        stat_parts = []
        if rhr_mean:
            stat_parts.append(f"RHR {_safe(rhr_mean)} ± {_safe(rhr_std)} bpm")
        if hrv_mean:
            stat_parts.append(f"HRV {_safe(hrv_mean)} ± {_safe(hrv_std)} ms")
        if vo2_mean:
            stat_parts.append(f"VO2 {_safe(vo2_mean, '.1f')} ± {_safe(vo2_std, '.1f')} ml/kg/min")
        fig.text(0.095, 0.076, "   ·   ".join(stat_parts), fontsize=8.5,
                 color=rs.INK_2, fontweight="medium")

        rs.footer(fig, "Page 2")
        pdf.savefig(fig, facecolor="white")
        plt.close(fig)

        # ================================================================
        # PAGE 3 — TRAINING
        # ================================================================
        fig = rs.new_page()
        rs.add_header(fig, "Training", month_name, accent=rs.TRAINING)

        # --- Daily TSS bars --------------------------------------------
        rs.section_label(fig, "Daily Training Load", y=0.875, accent=rs.TRAINING)
        ax_tss = fig.add_axes([0.095, 0.730, 0.840, 0.130])
        if not m_load.empty and "tss" in m_load.columns:
            ax_tss.bar(m_load.index, m_load["tss"],
                       color=rs.TRAINING, alpha=0.80, width=0.85, zorder=2)
            ax_tss.xaxis.set_major_formatter(mdates.DateFormatter("%d"))
            ax_tss.xaxis.set_major_locator(mdates.DayLocator(interval=5))
        rs.style_axis(ax_tss, ylabel="TSS")

        # --- ACWR line with risk zones ---------------------------------
        rs.section_label(fig, "Acute:Chronic Workload Ratio", y=0.685, accent=rs.TRAINING)
        ax_acwr = fig.add_axes([0.095, 0.540, 0.840, 0.130])
        if not m_load.empty and "acwr" in m_load.columns:
            acwr_data = m_load["acwr"].dropna()
            if not acwr_data.empty:
                ax_acwr.fill_between(acwr_data.index, 1.5, 2.0,
                                     alpha=0.10, color=rs.BAD, zorder=1)
                ax_acwr.fill_between(acwr_data.index, 0.8, 1.3,
                                     alpha=0.10, color=rs.GOOD, zorder=1)
                ax_acwr.axhline(1.0, color=rs.INK_3, linestyle=(0, (4, 3)),
                                linewidth=1.0, zorder=2)
                ax_acwr.plot(acwr_data.index, acwr_data.values,
                             color=rs.TRAINING, linewidth=2.4, zorder=3, label="ACWR")
                ax_acwr.set_ylim(0.5, 2.0)
                ax_acwr.xaxis.set_major_formatter(mdates.DateFormatter("%d"))
                ax_acwr.xaxis.set_major_locator(mdates.DayLocator(interval=5))
                from matplotlib.patches import Patch
                legend_els = [
                    Patch(facecolor=rs.GOOD, alpha=0.25, label="Optimal 0.8–1.3"),
                    Patch(facecolor=rs.BAD, alpha=0.20, label="High risk >1.5"),
                    plt.Line2D([0], [0], color=rs.TRAINING, linewidth=2, label="ACWR"),
                ]
                ax_acwr.legend(handles=legend_els, fontsize=7.5, loc="upper right",
                               frameon=False)
        rs.style_axis(ax_acwr, ylabel="Ratio")

        # --- HR Zone Distribution --------------------------------------
        rs.hairline(fig, y=0.515)
        rs.section_label(fig, "HR Zone Distribution", y=0.487, accent=rs.TRAINING)
        ax_zone = fig.add_axes([0.095, 0.380, 0.840, 0.095])
        zone_result = analytics.hr_zone_distribution(
            workouts_df, config, month_start, month_end
        )
        rs.zone_bar(ax_zone, zone_result["zone_pct"], zone_result["zone_minutes"])

        # Polarisation insight
        z_pct = zone_result["zone_pct"]
        easy_pct = z_pct.get(1, 0) + z_pct.get(2, 0)
        grey_pct = z_pct.get(3, 0)
        hard_pct = z_pct.get(4, 0) + z_pct.get(5, 0)
        total_zone_pct = easy_pct + grey_pct + hard_pct

        if total_zone_pct > 5:
            if grey_pct > 25 and easy_pct < 70:
                polar_text = (
                    f"{grey_pct:.0f}% of training in Z3 (moderate-hard) — "
                    "endurance research favours a polarised split (~80% easy, ~20% hard) "
                    "with less time in the Z3 grey zone."
                )
            elif easy_pct >= 75:
                polar_text = (
                    f"{easy_pct:.0f}% easy / {grey_pct:.0f}% Z3 / {hard_pct:.0f}% hard "
                    "— solid polarised distribution; most training at low intensity."
                )
            else:
                polar_text = (
                    f"{easy_pct:.0f}% easy / {grey_pct:.0f}% Z3 / {hard_pct:.0f}% hard "
                    "— endurance research suggests ~80% easy, ~20% hard with minimal Z3."
                )
            fig.text(0.095, 0.366, polar_text, fontsize=8.0, color=rs.INK_2,
                     wrap=True)
        else:
            fig.text(0.095, 0.366, "No HR zone data available for this month.",
                     fontsize=8.0, color=rs.INK_3)

        # --- Training Monotony -----------------------------------------
        rs.hairline(fig, y=0.340)
        rs.section_label(fig, "Training Monotony", y=0.312, accent=rs.INK)

        monotony_df = analytics.training_monotony(daily_load)
        # Filter monotony to the month
        mono_month = monotony_df[
            (monotony_df.index >= month_start) & (monotony_df.index < month_end)
        ] if not monotony_df.empty else pd.DataFrame()

        ax_mono = fig.add_axes([0.095, 0.160, 0.840, 0.140])
        if not mono_month.empty and "monotony" in mono_month.columns:
            mono_vals = mono_month["monotony"].dropna()
            if not mono_vals.empty:
                ax_mono.plot(mono_vals.index, mono_vals.values,
                             color=rs.INK, linewidth=2.0, zorder=3)
                ax_mono.axhline(2.0, color=rs.BAD, linestyle=(0, (4, 3)),
                                linewidth=1.2, zorder=2, label="Foster threshold (2.0)")
                ax_mono.xaxis.set_major_formatter(mdates.DateFormatter("%d"))
                ax_mono.xaxis.set_major_locator(mdates.DayLocator(interval=5))
                ax_mono.legend(fontsize=7.5, loc="upper right", frameon=False)
        rs.style_axis(ax_mono, ylabel="Monotony")
        ax_mono.set_xticklabels([])  # shares date range with the TSS chart above

        # Monotony callout + training summary
        mean_mono = float(mono_month["monotony"].mean()) if (
            not mono_month.empty and "monotony" in mono_month.columns
            and mono_month["monotony"].notna().any()) else None
        peak_mono = float(mono_month["monotony"].max()) if (
            not mono_month.empty and "monotony" in mono_month.columns
            and mono_month["monotony"].notna().any()) else None

        mono_text_parts = []
        if mean_mono is not None:
            mono_text_parts.append(f"Mean monotony {mean_mono:.2f}")
        if peak_mono is not None:
            flag = "  — above Foster's injury-risk threshold of 2.0" if peak_mono > 2.0 else ""
            mono_text_parts.append(f"peak {peak_mono:.2f}{flag}")
        if mono_text_parts:
            fig.text(0.095, 0.146, "  ·  ".join(mono_text_parts),
                     fontsize=8.0, color=rs.INK_2)

        # Training summary stat block
        total_workouts = month_summary.get("workout_count", 0)
        training_days = month_summary.get("training_days", 0)
        total_hours = month_summary.get("total_duration_hours", 0)
        total_tss = month_summary.get("total_tss", 0)
        avg_mono_str = f"{mean_mono:.2f}" if mean_mono is not None else "--"

        summary_items = [
            ("Workouts", str(int(total_workouts)) if total_workouts else "--"),
            ("Training days", str(int(training_days)) if training_days else "--"),
            ("Total duration", f"{total_hours:.1f} h" if total_hours else "--"),
            ("Total TSS", f"{total_tss:.0f}" if total_tss else "--"),
            ("Avg monotony", avg_mono_str),
        ]

        ax_tsumm = fig.add_axes([0.095, 0.060, 0.840, 0.075])
        ax_tsumm.axis("off")
        ax_tsumm.set_xlim(0, 1)
        ax_tsumm.set_ylim(0, 1)
        col_w = 0.20
        for i, (lbl, val) in enumerate(summary_items):
            x_off = i * col_w
            ax_tsumm.text(x_off, 0.88, lbl.upper(), fontsize=7.0, color=rs.INK_3)
            ax_tsumm.text(x_off, 0.38, val, fontsize=12, color=rs.INK, fontweight="bold")

        rs.footer(fig, "Page 3")
        pdf.savefig(fig, facecolor="white")
        plt.close(fig)

        # ================================================================
        # PAGE 4 — SLEEP & ACTIVITY
        # ================================================================
        fig = rs.new_page()
        rs.add_header(fig, "Sleep & Activity", month_name, accent=rs.SLEEP)

        # --- Sleep duration bars ---------------------------------------
        rs.section_label(fig, "Sleep Duration", y=0.875, accent=rs.SLEEP)
        ax_slp = fig.add_axes([0.095, 0.730, 0.840, 0.130])
        if not m_sleep.empty and "total_sleep" in m_sleep.columns:
            slp_data = m_sleep["total_sleep"].dropna()
            if not slp_data.empty:
                ax_slp.bar(slp_data.index, slp_data.values,
                           color=rs.SLEEP, alpha=0.75, width=0.85, zorder=2)
                ax_slp.axhline(7.5, color=rs.INK_3, linestyle=(0, (4, 3)),
                               linewidth=1.0, zorder=3, label="7.5h target")
                ax_slp.xaxis.set_major_formatter(mdates.DateFormatter("%d"))
                ax_slp.xaxis.set_major_locator(mdates.DayLocator(interval=5))
                ax_slp.legend(fontsize=7.5, loc="upper right", frameon=False)
        rs.style_axis(ax_slp, ylabel="Hours")

        # --- Sleep efficiency line ------------------------------------
        rs.section_label(fig, "Sleep Efficiency", y=0.685, accent=rs.SLEEP)
        ax_eff = fig.add_axes([0.095, 0.540, 0.840, 0.130])
        if not m_sleep.empty and "sleep_efficiency" in m_sleep.columns:
            eff_data = (m_sleep["sleep_efficiency"].dropna() * 100)
            if not eff_data.empty:
                ax_eff.plot(eff_data.index, eff_data.values,
                            color=rs.SLEEP, linewidth=2.4, zorder=3)
                ax_eff.set_ylim(50, 100)
                ax_eff.xaxis.set_major_formatter(mdates.DateFormatter("%d"))
                ax_eff.xaxis.set_major_locator(mdates.DayLocator(interval=5))
        rs.style_axis(ax_eff, ylabel="%")
        fig.text(0.095, 0.532, "Efficiency = sleep time / tracked window. "
                 "Apple Watch tracks from sleep onset, not lights-out, "
                 "so values tend to run higher than polysomnography.",
                 fontsize=7.5, color=rs.INK_3)

        # --- Sleep stage distribution — horizontal stacked bar ---------
        rs.hairline(fig, y=0.510)
        rs.section_label(fig, "Average Sleep Stage Distribution", y=0.482, accent=rs.SLEEP)
        ax_stage = fig.add_axes([0.095, 0.400, 0.840, 0.070])
        ax_stage.axis("off")
        ax_stage.set_xlim(0, 100)
        ax_stage.set_ylim(0, 1)

        deep_avg = (m_sleep["deep_sleep"].dropna().mean()
                    if not m_sleep.empty and "deep_sleep" in m_sleep.columns else 0) or 0
        rem_avg = (m_sleep["rem_sleep"].dropna().mean()
                   if not m_sleep.empty and "rem_sleep" in m_sleep.columns else 0) or 0
        light_avg = (m_sleep["light_sleep"].dropna().mean()
                     if not m_sleep.empty and "light_sleep" in m_sleep.columns else 0) or 0
        total_stages = deep_avg + rem_avg + light_avg

        if total_stages > 0:
            deep_pct = deep_avg / total_stages * 100
            rem_pct = rem_avg / total_stages * 100
            light_pct = light_avg / total_stages * 100
            stage_colors = ["#1a237e", "#4F4FC4", "#a0a0d8"]
            stage_labels = [f"Deep {deep_pct:.0f}%", f"REM {rem_pct:.0f}%",
                            f"Light {light_pct:.0f}%"]
            stage_vals = [deep_pct, rem_pct, light_pct]
            left = 0.0
            for s_val, s_col, s_lbl in zip(stage_vals, stage_colors, stage_labels):
                if s_val > 0:
                    ax_stage.barh(0.5, s_val, left=left, height=0.45,
                                  color=s_col, edgecolor="white", linewidth=1.2,
                                  align="center")
                    if s_val >= 8:
                        ax_stage.text(left + s_val / 2, 0.5, s_lbl,
                                      ha="center", va="center", fontsize=8.5,
                                      color="white", fontweight="bold")
                    left += s_val
        else:
            ax_stage.text(50, 0.5, "Sleep stage data not available.",
                          ha="center", va="center", fontsize=9, color=rs.INK_3)

        # --- Sleep consistency callout --------------------------------
        rs.hairline(fig, y=0.380)
        rs.section_label(fig, "Sleep Consistency", y=0.352, accent=rs.INK)

        sc = analytics.sleep_consistency(sleep_df, month_start, month_end)
        sc_items = []
        if sc.get("mean_bedtime") and sc["mean_bedtime"] != "N/A":
            sc_items.append(("Mean bedtime", sc["mean_bedtime"]))
        if sc.get("mean_wake") and sc["mean_wake"] != "N/A":
            sc_items.append(("Mean wake", sc["mean_wake"]))
        bsd = sc.get("bedtime_sd_min")
        wsd = sc.get("wake_sd_min")
        if bsd is not None and not np.isnan(bsd):
            sc_items.append(("Bedtime variability", f"{bsd:.0f} min SD"))
        if wsd is not None and not np.isnan(wsd):
            sc_items.append(("Wake variability", f"{wsd:.0f} min SD"))

        ax_sc = fig.add_axes([0.095, 0.238, 0.840, 0.105])
        ax_sc.axis("off")
        ax_sc.set_xlim(0, 1)
        ax_sc.set_ylim(0, 1)
        col_w_sc = 0.25
        for i, (lbl, val) in enumerate(sc_items[:4]):
            x_sc = i * col_w_sc
            ax_sc.text(x_sc, 0.85, lbl.upper(), fontsize=7.0, color=rs.INK_3)
            ax_sc.text(x_sc, 0.40, val, fontsize=11.5, color=rs.INK, fontweight="bold")
        fig.text(0.095, 0.228, "Lower SD = more consistent schedule.",
                 fontsize=7.5, color=rs.INK_3)

        # --- Activity: Steps + Distance --------------------------------
        rs.hairline(fig, y=0.210)
        rs.section_label(fig, "Activity", y=0.182, accent=rs.ACTIVITY)

        # Steps bars (no arbitrary 8k line — use rounded monthly mean or omit)
        ax_steps = fig.add_axes([0.095, 0.090, 0.400, 0.085])
        steps_target = None
        if not m_metrics.empty and "steps" in m_metrics.columns:
            steps_data = m_metrics["steps"].dropna()
            if not steps_data.empty:
                ax_steps.bar(steps_data.index, steps_data.values / 1000,
                             color=rs.ACTIVITY, alpha=0.75, width=0.85, zorder=2)
                # Rounded monthly mean line instead of arbitrary 8k
                monthly_mean_steps = steps_data.mean()
                if monthly_mean_steps > 0:
                    rounded_mean = round(monthly_mean_steps / 1000) * 1000
                    steps_target = rounded_mean
                    ax_steps.axhline(monthly_mean_steps / 1000, color=rs.INK_3,
                                     linestyle=(0, (4, 3)), linewidth=0.9, zorder=3)
                ax_steps.xaxis.set_major_formatter(mdates.DateFormatter("%d"))
                ax_steps.xaxis.set_major_locator(mdates.DayLocator(interval=7))
        rs.style_axis(ax_steps, ylabel="k steps")
        ax_steps.set_xticklabels([])

        # Distance line
        ax_dist = fig.add_axes([0.560, 0.090, 0.375, 0.085])
        if not m_metrics.empty and "distance_walk_run" in m_metrics.columns:
            dist_data = m_metrics["distance_walk_run"].dropna()
            if not dist_data.empty:
                ax_dist.plot(dist_data.index, dist_data.values,
                             color=rs.ACTIVITY, linewidth=2.2, zorder=3)
                ax_dist.fill_between(dist_data.index, dist_data.values,
                                     alpha=0.10, color=rs.ACTIVITY)
                ax_dist.xaxis.set_major_formatter(mdates.DateFormatter("%d"))
                ax_dist.xaxis.set_major_locator(mdates.DayLocator(interval=7))
        rs.style_axis(ax_dist, ylabel="km")
        ax_dist.set_xticklabels([])

        # Activity summary stat block
        steps_mean = month_summary.get("steps_mean")
        steps_total = month_summary.get("steps_total")
        dist_total = month_summary.get("distance_total")
        cals_total = month_summary.get("active_calories_total")

        act_items = [
            ("Avg steps",
             f"{int(steps_mean):,}" if steps_mean else "--"),
            ("Total steps",
             f"{int(steps_total):,}" if steps_total else "--"),
            ("Total distance",
             f"{dist_total:.0f} km" if dist_total else "--"),
            ("Active cals",
             f"{int(cals_total):,} kcal" if cals_total else "--"),
        ]

        ax_asum = fig.add_axes([0.095, 0.043, 0.840, 0.040])
        ax_asum.axis("off")
        ax_asum.set_xlim(0, 1)
        ax_asum.set_ylim(0, 1)
        col_w_a = 0.25
        for i, (lbl, val) in enumerate(act_items):
            x_a = i * col_w_a
            ax_asum.text(x_a, 0.90, lbl.upper(), fontsize=7.0, color=rs.INK_3)
            ax_asum.text(x_a, 0.20, val, fontsize=10.0, color=rs.INK, fontweight="bold")

        rs.footer(fig, "Page 4")
        pdf.savefig(fig, facecolor="white")
        plt.close(fig)

    return output_path
