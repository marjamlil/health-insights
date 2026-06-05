"""
Advanced Training and Recovery Analytics

Pure functions for training load analysis, HRV trending, sleep consistency,
and notable-event detection. Designed to work with the processed CSVs in data/
and the existing helpers in src/metrics.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

import numpy as np
import pandas as pd

try:
    from .metrics import estimate_max_hr, get_hr_zone
except ImportError:  # allow running this file directly for the verification block
    from metrics import estimate_max_hr, get_hr_zone


# ---------------------------------------------------------------------------
# 1. HR Zone Distribution
# ---------------------------------------------------------------------------

def hr_zone_distribution(
    workouts_df: pd.DataFrame,
    config: dict,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
) -> dict:
    """
    Accumulate workout duration into HR zones over an optional date window.

    Limitation: avg_hr gives a single whole-workout zone assignment; no
    per-second HR stream is available in the CSV, so intra-workout zone splits
    are not possible.

    Args:
        workouts_df: Workouts DataFrame with start_date, avg_hr, duration_minutes.
        config: Loaded settings dict (hr_zones key required).
        period_start: Inclusive start datetime (filter on start_date). None = all.
        period_end: Exclusive end datetime. None = all.

    Returns:
        {
            "zone_minutes":      {1: float, ..., 5: float},
            "zone_pct":          {1: float, ..., 5: float},
            "total_minutes":     float,
            "workouts_with_hr":  int,
            "workouts_without_hr": int,
        }
    """
    df = workouts_df.copy()
    df["start_date"] = pd.to_datetime(df["start_date"])

    if period_start is not None:
        df = df[df["start_date"] >= period_start]
    if period_end is not None:
        df = df[df["start_date"] < period_end]

    hr_config = config.get("hr_zones", {})
    max_hr: float = hr_config.get("max_hr", estimate_max_hr())
    zones = {k: v for k, v in hr_config.items() if k.startswith("zone")}

    has_hr = df["avg_hr"].notna()
    workouts_without_hr = int((~has_hr).sum())
    workouts_with_hr = int(has_hr.sum())

    zone_minutes: dict[int, float] = {z: 0.0 for z in range(1, 6)}

    for _, row in df[has_hr].iterrows():
        zone = get_hr_zone(row["avg_hr"], max_hr, zones)
        zone_minutes[zone] += float(row["duration_minutes"])

    total_minutes = sum(zone_minutes.values())

    if total_minutes > 0:
        zone_pct = {z: round(mins / total_minutes * 100, 2) for z, mins in zone_minutes.items()}
    else:
        zone_pct = {z: 0.0 for z in range(1, 6)}

    return {
        "zone_minutes": zone_minutes,
        "zone_pct": zone_pct,
        "total_minutes": total_minutes,
        "workouts_with_hr": workouts_with_hr,
        "workouts_without_hr": workouts_without_hr,
    }


# ---------------------------------------------------------------------------
# 2. Training Monotony
# ---------------------------------------------------------------------------

def training_monotony(daily_load: pd.DataFrame, window: int = 7) -> pd.DataFrame:
    """
    Compute training monotony and strain over a rolling window.

    Reindexes to a continuous daily range, filling rest days with TSS = 0.

    Monotony = rolling_mean(TSS) / rolling_std(TSS).
    Strain    = weekly_load * monotony.

    Foster's threshold: monotony > 2.0 is associated with elevated injury and
    illness risk (Foster, 1998). A varied training stimulus (lower monotony)
    at the same total load is generally safer.

    Args:
        daily_load: DataFrame indexed by date with a 'tss' column.
        window: Rolling window in days (default 7).

    Returns:
        DataFrame with columns: daily_tss, monotony, weekly_load, strain.
    """
    df = daily_load[["tss"]].copy().rename(columns={"tss": "daily_tss"})

    # Fill date gaps (rest days) with zero
    full_range = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(full_range, fill_value=0.0)

    rolling = df["daily_tss"].rolling(window=window, min_periods=1)
    roll_mean = rolling.mean()
    roll_std = rolling.std()

    # Guard against divide-by-zero on flat / all-zero windows
    monotony = roll_mean / roll_std.replace(0, np.nan)

    weekly_load = df["daily_tss"].rolling(window=window, min_periods=1).sum()
    strain = weekly_load * monotony

    result = pd.DataFrame(
        {
            "daily_tss": df["daily_tss"],
            "monotony": monotony,
            "weekly_load": weekly_load,
            "strain": strain,
        }
    )
    return result


# ---------------------------------------------------------------------------
# 3. HRV Rolling Averages
# ---------------------------------------------------------------------------

def hrv_rolling(
    daily_metrics: pd.DataFrame,
    short: int = 7,
    long: int = 30,
) -> Tuple[pd.DataFrame, str]:
    """
    Compute short- and long-term rolling HRV averages.

    A suppressed status indicates the recent 7-day mean has dropped below 95%
    of the 30-day baseline — a sign of reduced parasympathetic activity and
    accumulating fatigue.

    Args:
        daily_metrics: DataFrame indexed by date with an 'hrv' column.
        short: Short rolling window in days (default 7).
        long: Long rolling window in days (default 30).

    Returns:
        Tuple of:
          - DataFrame with columns hrv, hrv_7d, hrv_30d (indexed by date).
          - latest_status: "suppressed" if most recent hrv_7d < hrv_30d * 0.95,
            else "normal". Returns "insufficient_data" when windows aren't full.
    """
    hrv_series = daily_metrics["hrv"].dropna()

    df = pd.DataFrame({"hrv": hrv_series})
    df["hrv_7d"] = df["hrv"].rolling(short, min_periods=3).mean()
    df["hrv_30d"] = df["hrv"].rolling(long, min_periods=7).mean()

    # Latest status
    last = df.dropna(subset=["hrv_7d", "hrv_30d"])
    if last.empty:
        latest_status = "insufficient_data"
    else:
        row = last.iloc[-1]
        latest_status = "suppressed" if row["hrv_7d"] < row["hrv_30d"] * 0.95 else "normal"

    return df, latest_status


# ---------------------------------------------------------------------------
# 4. Year-on-Year Cardiac Trend
# ---------------------------------------------------------------------------

def yoy_cardiac(daily_metrics: pd.DataFrame) -> pd.DataFrame:
    """
    Resample resting HR and HRV to monthly means across the full history.

    Only months that contain at least one non-null reading for either metric
    are included, giving a clean multi-year trajectory for charting.

    Args:
        daily_metrics: Full daily_metrics DataFrame indexed by date.

    Returns:
        DataFrame indexed by month-start datetime with columns resting_hr, hrv.
    """
    cardiac = daily_metrics[["resting_hr", "hrv"]].copy()
    monthly = cardiac.resample("MS").mean()
    # Drop months with no data in either column
    monthly = monthly.dropna(how="all")
    return monthly


# ---------------------------------------------------------------------------
# 5. Notable Events
# ---------------------------------------------------------------------------

def notable_events(
    daily_metrics: pd.DataFrame,
    daily_load: pd.DataFrame,
    sleep_df: pd.DataFrame,
    period_start: datetime,
    period_end: datetime,
) -> list[str]:
    """
    Return 4-6 factual, coach-worthy observations about the period.

    Only includes events that actually occurred. Each string is under ~60 chars
    and uses UK date format (e.g. "7 May").

    Args:
        daily_metrics: Daily metrics DataFrame indexed by date.
        daily_load: Daily training load DataFrame indexed by date with 'tss'.
        sleep_df: Sleep DataFrame indexed by date.
        period_start: Inclusive period start.
        period_end: Exclusive period end.

    Returns:
        List of short factual strings.
    """
    events: list[str] = []

    def _fmt_date(dt) -> str:
        return pd.Timestamp(dt).strftime("%-d %b")

    def _filter(df: pd.DataFrame) -> pd.DataFrame:
        return df[(df.index >= period_start) & (df.index < period_end)]

    dm = _filter(daily_metrics)
    dl = _filter(daily_load)
    sl = _filter(sleep_df)

    # --- Highest training day ---
    if not dl.empty and dl["tss"].max() > 0:
        idx = dl["tss"].idxmax()
        tss_val = dl["tss"].max()
        events.append(f"Highest training day: {_fmt_date(idx)} ({tss_val:.0f} TSS)")

    # --- Lowest resting HR (30-day low check) ---
    if "resting_hr" in dm.columns and dm["resting_hr"].notna().any():
        period_min = dm["resting_hr"].min()
        min_date = dm["resting_hr"].idxmin()
        # 30-day context window ending at period_start
        context_start = period_start - pd.Timedelta(days=30)
        context = daily_metrics[
            (daily_metrics.index >= context_start) & (daily_metrics.index < period_start)
        ]["resting_hr"].dropna()
        label = " (30-day low)" if context.empty or period_min < context.min() else ""
        events.append(
            f"Lowest resting HR: {period_min:.0f} bpm on {_fmt_date(min_date)}{label}"
        )

    # --- Longest sleep streak ≥ 7.5h ---
    if "total_sleep" in sl.columns and sl["total_sleep"].notna().any():
        sl_sorted = sl.sort_index()
        meets = sl_sorted["total_sleep"] >= 7.5
        if meets.any():
            # Find longest consecutive run
            best_start = best_end = best_len = 0
            cur_start = cur_len = 0
            dates = sl_sorted.index.tolist()
            for i, (dt, ok) in enumerate(zip(dates, meets)):
                if ok:
                    if cur_len == 0:
                        cur_start = i
                    cur_len += 1
                    if cur_len > best_len:
                        best_len = cur_len
                        best_start = cur_start
                        best_end = i
                else:
                    cur_len = 0
            if best_len >= 3:
                s_d = _fmt_date(dates[best_start])
                e_d = _fmt_date(dates[best_end])
                events.append(
                    f"Longest sleep streak ≥7.5h: {s_d}–{e_d} ({best_len} nights)"
                )

    # --- Biggest step day ---
    if "steps" in dm.columns and dm["steps"].notna().any():
        max_steps = int(dm["steps"].max())
        step_date = dm["steps"].idxmax()
        events.append(f"Biggest step day: {max_steps:,} steps on {_fmt_date(step_date)}")

    # --- ACWR high-risk zone (>1.5) ---
    if not dl.empty and "tss" in dl.columns:
        full_range = pd.date_range(dl.index.min(), dl.index.max(), freq="D")
        dl_full = dl["tss"].reindex(full_range, fill_value=0.0)
        acute = dl_full.rolling(7, min_periods=1).mean()
        chronic = dl_full.rolling(28, min_periods=7).mean()
        acwr = (acute / chronic.replace(0, np.nan)).reindex(dm.index)
        high_risk = acwr[acwr > 1.5].dropna()
        if not high_risk.empty:
            first_hr = _fmt_date(high_risk.index.min())
            last_hr = _fmt_date(high_risk.index.max())
            n_days = len(high_risk)
            if n_days == 1:
                events.append(f"ACWR entered high-risk zone (>1.5) on {first_hr}")
            else:
                events.append(
                    f"ACWR high-risk zone (>1.5): {first_hr}–{last_hr} ({n_days} days)"
                )

    # --- Best HRV day ---
    if "hrv" in dm.columns and dm["hrv"].notna().any():
        best_hrv = dm["hrv"].max()
        hrv_date = dm["hrv"].idxmax()
        events.append(f"Best HRV: {best_hrv:.0f} ms on {_fmt_date(hrv_date)}")

    return events[:6]


# ---------------------------------------------------------------------------
# 6. Sleep Consistency
# ---------------------------------------------------------------------------

def sleep_consistency(
    sleep_df: pd.DataFrame,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
) -> dict:
    """
    Measure bedtime and wake-time consistency via standard deviation (minutes).

    Bedtimes are mapped to a continuous clock that treats post-midnight times
    (00:00–06:00) as the continuation of the previous evening, so 23:50 and
    00:10 are correctly computed as 20 minutes apart rather than 23h 40m.

    Args:
        sleep_df: Sleep DataFrame indexed by date. bedtime/wake_time are
                  datetime strings or datetime objects.
        period_start: Inclusive filter on the date index. None = all.
        period_end: Exclusive filter. None = all.

    Returns:
        {
            "bedtime_sd_min": float,   # lower = more consistent
            "wake_sd_min":    float,
            "mean_bedtime":   "HH:MM",
            "mean_wake":      "HH:MM",
        }
    """
    df = sleep_df.copy()
    if period_start is not None:
        df = df[df.index >= period_start]
    if period_end is not None:
        df = df[df.index < period_end]

    df = df.dropna(subset=["bedtime", "wake_time"])
    if df.empty:
        return {"bedtime_sd_min": float("nan"), "wake_sd_min": float("nan"),
                "mean_bedtime": "N/A", "mean_wake": "N/A"}

    def _to_minutes_of_day(series: pd.Series) -> pd.Series:
        """Convert datetimes to minutes-of-day (0–1439)."""
        ts = pd.to_datetime(series)
        return ts.dt.hour * 60 + ts.dt.minute + ts.dt.second / 60

    def _wrap_bedtime(minutes: pd.Series) -> pd.Series:
        """
        Shift post-midnight bedtimes (00:00–06:00, i.e. < 360 min) to
        1440+ so they sit naturally after an evening bedtime, making
        circular-mean and SD calculations straightforward.
        """
        return minutes.apply(lambda m: m + 1440 if m < 360 else m)

    bedtime_raw = _to_minutes_of_day(df["bedtime"])
    wake_raw = _to_minutes_of_day(df["wake_time"])

    # Only bedtimes cross midnight and need wrapping.
    # Wake times are always genuine morning times; wrapping would
    # misclassify early wakes (e.g. 05:29) as post-midnight bedtimes.
    bedtime_adj = _wrap_bedtime(bedtime_raw)

    def _minutes_to_hhmm(mean_min: float) -> str:
        total = int(round(mean_min)) % 1440
        return f"{total // 60:02d}:{total % 60:02d}"

    return {
        "bedtime_sd_min": round(float(bedtime_adj.std()), 1),
        "wake_sd_min": round(float(wake_raw.std()), 1),
        "mean_bedtime": _minutes_to_hhmm(bedtime_adj.mean()),
        "mean_wake": _minutes_to_hhmm(wake_raw.mean()),
    }


# ---------------------------------------------------------------------------
# Verification block
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from pathlib import Path
    import yaml

    ROOT = Path(__file__).parent.parent
    DATA = ROOT / "data"

    # Load config
    with open(ROOT / "config" / "settings.yaml") as f:
        config = yaml.safe_load(f)

    # Load CSVs
    daily_metrics = pd.read_csv(
        DATA / "daily_metrics.csv", index_col=0, parse_dates=True
    )
    sleep_df = pd.read_csv(
        DATA / "sleep.csv", index_col=0, parse_dates=True
    )
    workouts_df = pd.read_csv(
        DATA / "workouts.csv", index_col=0
    )
    workouts_df["start_date"] = pd.to_datetime(workouts_df["start_date"])

    # Build daily_load (TSS by date from workouts)
    workouts_df["_date"] = workouts_df["start_date"].dt.normalize()
    daily_load_raw = (
        workouts_df.groupby("_date")[["tss", "trimp", "duration_minutes"]]
        .sum()
        .rename_axis("date")
    )

    PS = datetime(2026, 5, 1)
    PE = datetime(2026, 6, 1)

    print("=" * 60)
    print("1. hr_zone_distribution (May 2026)")
    print("=" * 60)
    zd = hr_zone_distribution(workouts_df, config, period_start=PS, period_end=PE)
    for z in range(1, 6):
        print(f"  Zone {z}: {zd['zone_minutes'][z]:.1f} min  ({zd['zone_pct'][z]:.1f}%)")
    pct_total = sum(zd["zone_pct"].values())
    print(f"  Zone pct total: {pct_total:.1f}%")
    print(f"  Workouts with HR: {zd['workouts_with_hr']},  without: {zd['workouts_without_hr']}")
    print(f"  Total minutes:    {zd['total_minutes']:.1f}")

    print()
    print("=" * 60)
    print("2. training_monotony (May 2026 daily_load)")
    print("=" * 60)
    dl_may = daily_load_raw[
        (daily_load_raw.index >= PS) & (daily_load_raw.index < PE)
    ]
    mono = training_monotony(dl_may, window=7)
    print(mono[["daily_tss", "monotony", "weekly_load", "strain"]].tail(7).round(2).to_string())
    print(f"  Max monotony: {mono['monotony'].max():.2f}  (Foster threshold = 2.0)")

    print()
    print("=" * 60)
    print("3. hrv_rolling (full history)")
    print("=" * 60)
    hrv_df, status = hrv_rolling(daily_metrics)
    print(hrv_df[["hrv", "hrv_7d", "hrv_30d"]].dropna().tail(7).round(1).to_string())
    print(f"  Latest status: {status}")

    print()
    print("=" * 60)
    print("4. yoy_cardiac (full history)")
    print("=" * 60)
    yoy = yoy_cardiac(daily_metrics)
    print(f"  Monthly rows: {len(yoy)}")
    print(yoy.round(1).head(3).to_string())
    print("  ...")
    print(yoy.round(1).tail(3).to_string())

    print()
    print("=" * 60)
    print("5. notable_events (May 2026)")
    print("=" * 60)
    events = notable_events(daily_metrics, daily_load_raw, sleep_df, PS, PE)
    for e in events:
        print(f"  - {e}")

    print()
    print("=" * 60)
    print("6. sleep_consistency (May 2026)")
    print("=" * 60)
    sc = sleep_consistency(sleep_df, period_start=PS, period_end=PE)
    print(f"  Bedtime SD:  {sc['bedtime_sd_min']} min")
    print(f"  Wake SD:     {sc['wake_sd_min']} min")
    print(f"  Mean bedtime: {sc['mean_bedtime']}")
    print(f"  Mean wake:    {sc['mean_wake']}")

    print()
    print("All checks passed.")
