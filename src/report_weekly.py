"""
Weekly health summary — single page.

Composed entirely from the report_style design system so it shares one visual
language with the monthly report. Four zones top to bottom: hero numbers,
training load (with HR-zone distribution), recovery trends, and a notable-events
strip with activity totals.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import matplotlib.dates as mdates
import pandas as pd

from . import report_style as rs
from . import analytics


def _readiness_status(score):
    if score is None or pd.isna(score):
        return None
    return "green" if score >= 60 else ("amber" if score >= 40 else "red")


_READINESS_TEXT = {
    "green": "Recovery: Optimal",
    "amber": "Recovery: Moderate",
    "red": "Recovery: Low",
}


def generate_weekly_report(week_summary, prev_week_summary, daily_metrics,
                           daily_load, sleep_df, workouts_df, readiness,
                           anomalies, baselines, config, output_path):
    rs.apply_base_style()
    fig = rs.new_page()

    week_start = week_summary["week_start"]
    week_end_excl = week_summary["week_end"]
    week_end = week_end_excl - timedelta(days=1)
    subtitle = f"{week_start.strftime('%d %b')} – {week_end.strftime('%d %b %Y')}"

    rs.add_header(fig, "Weekly Health Summary", subtitle, accent=rs.INK)

    # --- Readiness status (derived from the week mean, not a single volatile day) ---
    status = _readiness_status(week_summary.get("readiness_avg"))
    if status:
        rs.status_pill(fig, 0.065, 0.892, status, _READINESS_TEXT[status])

    # --- Hero numbers ---
    def delta(metric_key, unit, lower_better=False):
        return rs.delta_str(week_summary.get(metric_key),
                            prev_week_summary.get(metric_key) if prev_week_summary else None,
                            unit, lower_is_better=lower_better)

    rhr = week_summary.get("resting_hr_avg")
    hrv = week_summary.get("hrv_avg")
    vo2 = week_summary.get("vo2_max")
    slp = week_summary.get("sleep_avg")
    rhr_d, rhr_c = delta("resting_hr_avg", "", lower_better=True)
    hrv_d, hrv_c = delta("hrv_avg", "")
    slp_d, slp_c = delta("sleep_avg", "")

    hero = [
        {"label": "Resting HR", "value": f"{rhr:.0f}" if rhr else "--",
         "unit": "bpm", "accent": rs.CARDIAC, "delta": rhr_d, "delta_color": rhr_c},
        {"label": "HRV (SDNN)", "value": f"{hrv:.0f}" if hrv else "--",
         "unit": "ms", "accent": rs.CARDIAC, "delta": hrv_d, "delta_color": hrv_c},
        {"label": "VO2 Max", "value": f"{vo2:.1f}" if vo2 else "--",
         "unit": "ml/kg/min", "accent": rs.CARDIAC},
        {"label": "Sleep", "value": f"{slp:.1f}" if slp else "--",
         "unit": "h / night", "accent": rs.SLEEP, "delta": slp_d, "delta_color": slp_c},
    ]
    rs.hero_panel(fig, hero, y=0.80, h=0.085)

    # ================= TRAINING LOAD =================
    rs.section_label(fig, "Training Load", 0.725, rs.TRAINING)

    zd = analytics.hr_zone_distribution(workouts_df, config, week_start, week_end_excl)
    ax_zone = fig.add_axes([0.065, 0.655, 0.87, 0.05])
    if zd["total_minutes"] > 0:
        rs.zone_bar(ax_zone, zd["zone_pct"], zd["zone_minutes"])
        easy = zd["zone_pct"][1] + zd["zone_pct"][2]
        grey = zd["zone_pct"][3]
        hard = zd["zone_pct"][4] + zd["zone_pct"][5]
        fig.text(0.065, 0.612,
                 f"Easy {easy:.0f}%   ·   Grey-zone (Z3) {grey:.0f}%   ·   Hard {hard:.0f}%",
                 fontsize=8.5, color=rs.INK_2)
    else:
        ax_zone.axis("off")
        fig.text(0.065, 0.66, "No HR-based workouts this week.",
                 fontsize=9, color=rs.INK_3)

    # Training tiles
    tss = week_summary.get("total_tss", 0) or 0
    acwr = week_summary.get("acwr")
    wcount = week_summary.get("workout_count", 0) or 0
    dur = week_summary.get("total_duration", 0) or 0

    tss_d, tss_c = delta("total_tss", "")
    ax_tss = fig.add_axes([0.065, 0.50, 0.27, 0.075])
    rs.metric_tile(ax_tss, "Training Stress", f"{tss:.0f}", "TSS this week",
                   tss_d, tss_c, rs.TRAINING)

    ax_acwr = fig.add_axes([0.385, 0.50, 0.27, 0.075])
    if acwr:
        if acwr > 1.5:
            sub, ac = "High-risk", rs.BAD
        elif acwr < 0.8:
            sub, ac = "Detraining", rs.WARN
        else:
            sub, ac = "Optimal range", rs.GOOD
        rs.metric_tile(ax_acwr, "Acute:Chronic", f"{acwr:.2f}", sub,
                       None, rs.INK_2, ac)
    else:
        rs.metric_tile(ax_acwr, "Acute:Chronic", "--", "", None, rs.INK_2, rs.TRAINING)

    ax_wk = fig.add_axes([0.705, 0.50, 0.27, 0.075])
    hrs = int(dur // 60)
    mins = int(dur % 60)
    dur_txt = f"{hrs}h {mins}m" if hrs else f"{mins}m"
    rs.metric_tile(ax_wk, "Workouts", str(wcount), dur_txt, None, rs.INK_2, rs.TRAINING)

    rs.hairline(fig, 0.47)

    # ================= RECOVERY TRENDS =================
    rs.section_label(fig, "Recovery Trends · 30 days", 0.43, rs.CARDIAC)

    window_start = week_end_excl - timedelta(days=30)

    def _spark(ax_box, series, accent, label, fmt, unit):
        ax = fig.add_axes(ax_box)
        s = series[(series.index >= window_start) & (series.index < week_end_excl)].dropna()
        rs.sparkline(ax, s, accent)
        if not s.empty:
            fig.text(ax_box[0], ax_box[1] + ax_box[3] + 0.012, label.upper(),
                     fontsize=8, color=rs.INK_2, fontweight="medium")
            fig.text(ax_box[0] + ax_box[2], ax_box[1] + ax_box[3] + 0.012,
                     f"{fmt.format(s.iloc[-1])} {unit}", ha="right",
                     fontsize=9, color=rs.INK, fontweight="bold")

    _spark([0.065, 0.34, 0.41, 0.055], daily_metrics["resting_hr"],
           rs.CARDIAC, "Resting HR", "{:.0f}", "bpm")
    _spark([0.525, 0.34, 0.41, 0.055], daily_metrics["hrv"],
           rs.CARDIAC, "HRV", "{:.0f}", "ms")

    rs.hairline(fig, 0.30)

    # ================= THIS WEEK + ACTIVITY =================
    rs.section_label(fig, "This Week", 0.26, rs.ACTIVITY)
    events = analytics.notable_events(daily_metrics, daily_load, sleep_df,
                                      week_start, week_end_excl)
    y = 0.225
    if events:
        for e in events[:4]:
            fig.text(0.065, y, "—", fontsize=9, color=rs.ACTIVITY, va="center")
            fig.text(0.085, y, e, fontsize=9.5, color=rs.INK_2, va="center")
            y -= 0.028
    else:
        fig.text(0.065, y, "Quiet week — nothing notable flagged.",
                 fontsize=9.5, color=rs.INK_3)

    # Activity strip
    steps = week_summary.get("steps_avg")
    dist_total = week_summary.get("distance_total", 0) or 0
    cals_total = week_summary.get("active_calories_total", 0) or 0

    ax_steps = fig.add_axes([0.065, 0.05, 0.27, 0.07])
    rs.metric_tile(ax_steps, "Avg Steps", f"{steps/1000:.1f}k" if steps else "--",
                   "per day", None, rs.INK_2, rs.ACTIVITY)
    ax_dist = fig.add_axes([0.385, 0.05, 0.27, 0.07])
    rs.metric_tile(ax_dist, "Distance", f"{dist_total:.0f}", "km this week",
                   None, rs.INK_2, rs.ACTIVITY)
    ax_cals = fig.add_axes([0.705, 0.05, 0.27, 0.07])
    rs.metric_tile(ax_cals, "Active Energy", f"{cals_total/1000:.1f}k", "kcal this week",
                   None, rs.INK_2, rs.ACTIVITY)

    rs.footer(fig)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, facecolor="white")
    import matplotlib.pyplot as plt
    plt.close(fig)
    print(f"Weekly report saved to: {output_path}")
    return output_path
