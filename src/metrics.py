"""
Derived Metrics Calculator

Calculates training load, recovery metrics, and derived health insights
from processed HealthKit data.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Union, List
import yaml
from pathlib import Path


def load_config(config_path: Optional[Union[str, Path]] = None) -> dict:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def estimate_max_hr(age: int = 35) -> float:
    """Estimate max HR using Tanaka formula (more accurate than 220-age)."""
    return 208 - (0.7 * age)


def get_hr_zone(hr: float, max_hr: float, zones: dict) -> int:
    """
    Determine HR zone (1-5) for a given heart rate.

    Args:
        hr: Heart rate in bpm
        max_hr: Maximum heart rate
        zones: Zone definitions as percentages of max HR

    Returns:
        Zone number (1-5)
    """
    hr_pct = hr / max_hr

    if hr_pct < zones["zone1"][1]:
        return 1
    elif hr_pct < zones["zone2"][1]:
        return 2
    elif hr_pct < zones["zone3"][1]:
        return 3
    elif hr_pct < zones["zone4"][1]:
        return 4
    else:
        return 5


def calculate_trimp(duration_minutes: float, avg_hr: float, max_hr: float,
                    resting_hr: float = 60, gender: str = "male") -> float:
    """
    Calculate Training Impulse (TRIMP) for a workout.

    Uses Banister's TRIMP formula which weights intensity exponentially.

    Args:
        duration_minutes: Workout duration in minutes
        avg_hr: Average heart rate during workout
        max_hr: Maximum heart rate
        resting_hr: Resting heart rate
        gender: 'male' or 'female' (affects weighting factor)

    Returns:
        TRIMP score
    """
    if pd.isna(avg_hr) or avg_hr <= resting_hr:
        return 0

    # Heart rate reserve fraction
    hr_reserve = (avg_hr - resting_hr) / (max_hr - resting_hr)
    hr_reserve = max(0, min(1, hr_reserve))  # Clamp to [0, 1]

    # Gender-specific weighting factor
    if gender == "female":
        k = 1.67
    else:
        k = 1.92

    # TRIMP = duration * HRR * e^(k * HRR)
    trimp = duration_minutes * hr_reserve * np.exp(k * hr_reserve)

    return trimp


def calculate_training_stress_score(trimp: float, threshold_trimp: float = 100) -> float:
    """
    Calculate Training Stress Score (TSS) normalized to threshold effort.

    A 1-hour workout at threshold intensity = 100 TSS.

    Args:
        trimp: Raw TRIMP score
        threshold_trimp: TRIMP for 1 hour at threshold (calibration value)

    Returns:
        TSS value
    """
    return (trimp / threshold_trimp) * 100


def calculate_workout_metrics(workouts_df: pd.DataFrame,
                              daily_metrics: pd.DataFrame,
                              config: dict) -> pd.DataFrame:
    """
    Calculate derived metrics for each workout.

    Adds: TRIMP, TSS, HR zone time, intensity factor
    """
    if workouts_df.empty:
        return workouts_df

    df = workouts_df.copy()

    # Get max HR from config or estimate
    max_hr = config.get("hr_zones", {}).get("max_hr", estimate_max_hr())

    # Get resting HR from daily metrics (use median as default)
    if not daily_metrics.empty and "resting_hr" in daily_metrics.columns:
        resting_hr = daily_metrics["resting_hr"].median()
    else:
        resting_hr = 60

    # Calculate TRIMP and TSS for each workout
    df["trimp"] = df.apply(
        lambda row: calculate_trimp(
            row["duration_minutes"],
            row["avg_hr"],
            max_hr,
            resting_hr
        ) if pd.notna(row["avg_hr"]) else 0,
        axis=1
    )

    df["tss"] = df["trimp"].apply(calculate_training_stress_score)

    # Intensity factor (ratio of workout HR to threshold HR)
    threshold_hr = max_hr * 0.85  # ~85% of max is threshold
    df["intensity_factor"] = df["avg_hr"].apply(
        lambda x: x / threshold_hr if pd.notna(x) else None
    )

    return df


def calculate_daily_training_load(workouts_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate workout metrics to daily totals.

    Returns DataFrame with daily TRIMP, TSS, workout count, duration.
    """
    if workouts_df.empty:
        return pd.DataFrame()

    df = workouts_df.copy()
    df["date"] = pd.to_datetime(df["start_date"]).dt.date

    daily = df.groupby("date").agg({
        "trimp": "sum",
        "tss": "sum",
        "duration_minutes": "sum",
        "calories": "sum",
        "type": "count"  # workout count
    }).rename(columns={"type": "workout_count"})

    daily.index = pd.to_datetime(daily.index)
    return daily.sort_index()


def calculate_acute_chronic_ratio(daily_load: pd.DataFrame,
                                   acute_days: int = 7,
                                   chronic_days: int = 28) -> pd.DataFrame:
    """
    Calculate Acute:Chronic Workload Ratio (ACWR).

    ACWR > 1.5 indicates increased injury risk
    ACWR < 0.8 indicates detraining

    Args:
        daily_load: DataFrame with daily training load (TSS or TRIMP)
        acute_days: Rolling window for acute load (default 7 days)
        chronic_days: Rolling window for chronic load (default 28 days)

    Returns:
        DataFrame with acute load, chronic load, and ACWR
    """
    if daily_load.empty:
        return pd.DataFrame()

    df = daily_load.copy()

    # Fill missing days with 0 (rest days)
    date_range = pd.date_range(df.index.min(), df.index.max())
    df = df.reindex(date_range, fill_value=0)

    # Calculate rolling averages
    df["acute_load"] = df["tss"].rolling(window=acute_days, min_periods=1).mean()
    df["chronic_load"] = df["tss"].rolling(window=chronic_days, min_periods=7).mean()

    # ACWR
    df["acwr"] = df.apply(
        lambda row: row["acute_load"] / row["chronic_load"]
        if row["chronic_load"] > 0 else None,
        axis=1
    )

    return df


def calculate_readiness_score(daily_metrics: pd.DataFrame,
                               config: dict) -> pd.DataFrame:
    """
    Calculate daily readiness score based on HRV and resting HR.

    Compares current values to rolling baseline to determine recovery status.

    Returns:
        DataFrame with readiness scores (0-100) and status (green/amber/red)
    """
    if daily_metrics.empty:
        return pd.DataFrame()

    df = daily_metrics.copy()
    window = config.get("baselines", {}).get("rolling_window_days", 30)

    readiness = pd.DataFrame(index=df.index)

    # HRV component (higher is better)
    if "hrv" in df.columns:
        hrv_baseline = df["hrv"].rolling(window=window, min_periods=7).mean()
        hrv_std = df["hrv"].rolling(window=window, min_periods=7).std()

        # Z-score: how many SDs above/below baseline
        readiness["hrv_zscore"] = (df["hrv"] - hrv_baseline) / hrv_std.replace(0, 1)
        # Convert to 0-100 scale (positive z-score = good); baseline day = 50
        readiness["hrv_score"] = 50 + (readiness["hrv_zscore"].clip(-2, 2) * 25)

    # Resting HR component (lower is better)
    if "resting_hr" in df.columns:
        rhr_baseline = df["resting_hr"].rolling(window=window, min_periods=7).mean()
        rhr_std = df["resting_hr"].rolling(window=window, min_periods=7).std()

        # Z-score: negative z-score = good (lower than baseline)
        readiness["rhr_zscore"] = (df["resting_hr"] - rhr_baseline) / rhr_std.replace(0, 1)
        # Convert to 0-100 scale (negative z-score = good); baseline day = 50
        readiness["rhr_score"] = 50 - (readiness["rhr_zscore"].clip(-2, 2) * 25)

    # Combined readiness score (0-100): mean of available 0-100 components
    score_cols = [c for c in readiness.columns if c.endswith("_score")]
    if score_cols:
        readiness["readiness_score"] = readiness[score_cols].mean(axis=1)

        # Status categories
        readiness["readiness_status"] = readiness["readiness_score"].apply(
            lambda x: "green" if x >= 60 else ("amber" if x >= 40 else "red")
            if pd.notna(x) else None
        )

    return readiness


def calculate_hr_recovery(workouts_df: pd.DataFrame,
                          hr_records: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate heart rate recovery for each workout.

    HR recovery = HR at end of workout - HR at 1min/2min post-workout.
    Higher values indicate better cardiovascular fitness.

    Note: Requires raw HR records with timestamps to match post-workout HR.
    """
    if workouts_df.empty or hr_records.empty:
        return workouts_df

    df = workouts_df.copy()

    # This is a simplified version - ideally we'd match HR records
    # to workout end times. For MVP, we'll estimate from workout data.
    # Full implementation would require detailed HR timeseries.

    # Placeholder: estimate recovery from max HR to avg HR
    df["hr_recovery_estimate"] = df.apply(
        lambda row: row["max_hr"] - row["avg_hr"]
        if pd.notna(row["max_hr"]) and pd.notna(row["avg_hr"])
        else None,
        axis=1
    )

    return df


def calculate_hr_zone_distribution(workouts_df: pd.DataFrame,
                                    config: dict) -> dict:
    """
    Calculate time spent in each HR zone across workouts.

    Returns dict with zone percentages.
    """
    if workouts_df.empty:
        return {}

    max_hr = config.get("hr_zones", {}).get("max_hr", estimate_max_hr())
    zones = config.get("hr_zones", {})

    # Simplified: assign entire workout to zone based on avg HR
    df = workouts_df.dropna(subset=["avg_hr"]).copy()

    df["zone"] = df["avg_hr"].apply(lambda x: get_hr_zone(x, max_hr, zones))

    # Sum duration by zone
    zone_minutes = df.groupby("zone")["duration_minutes"].sum()

    total = zone_minutes.sum()
    if total > 0:
        zone_pct = (zone_minutes / total * 100).to_dict()
    else:
        zone_pct = {}

    # Ensure all zones present
    for z in range(1, 6):
        if z not in zone_pct:
            zone_pct[z] = 0.0

    return zone_pct


def calculate_sleep_debt(sleep_df: pd.DataFrame,
                         target_hours: float = 7.5) -> pd.DataFrame:
    """
    Calculate running sleep debt.

    Tracks cumulative difference from target sleep hours.
    """
    if sleep_df.empty:
        return sleep_df

    df = sleep_df.copy()

    # Daily sleep deficit/surplus
    df["sleep_delta"] = df["total_sleep"] - target_hours

    # Running debt (negative = debt, positive = surplus)
    # Cap at +/- 20 hours to prevent extreme accumulation
    df["sleep_debt"] = df["sleep_delta"].cumsum().clip(-20, 20)

    return df


def calculate_personal_baselines(daily_metrics: pd.DataFrame,
                                  config: dict) -> dict:
    """
    Calculate personal baselines for key metrics.

    Returns dict with baseline values and ranges for each metric.
    """
    window = config.get("baselines", {}).get("rolling_window_days", 30)
    min_points = config.get("baselines", {}).get("min_data_points", 7)

    baselines = {}

    for col in ["resting_hr", "hrv", "vo2_max"]:
        if col in daily_metrics.columns:
            data = daily_metrics[col].dropna()
            if len(data) >= min_points:
                baselines[col] = {
                    "mean": data.mean(),
                    "std": data.std(),
                    "min": data.min(),
                    "max": data.max(),
                    "p25": data.quantile(0.25),
                    "p75": data.quantile(0.75),
                    "recent_mean": data.tail(window).mean(),
                    "recent_std": data.tail(window).std(),
                }

    return baselines


def detect_anomalies(daily_metrics: pd.DataFrame,
                     sleep_df: pd.DataFrame,
                     baselines: dict,
                     config: dict) -> List[dict]:
    """
    Detect anomalies in health metrics using conservative thresholds.

    Returns list of anomaly events with date, metric, value, and description.
    """
    anomalies = []
    thresholds = config.get("anomaly_detection", {})

    # Resting HR anomalies
    if "resting_hr" in daily_metrics.columns and "resting_hr" in baselines:
        rhr = daily_metrics["resting_hr"].dropna()
        baseline = baselines["resting_hr"]
        threshold = thresholds.get("resting_hr_std_threshold", 2.0)

        for date, value in rhr.items():
            zscore = (value - baseline["recent_mean"]) / baseline["recent_std"]
            if abs(zscore) > threshold:
                direction = "elevated" if zscore > 0 else "reduced"
                anomalies.append({
                    "date": date,
                    "metric": "Resting HR",
                    "value": f"{value:.0f} bpm",
                    "description": f"Significantly {direction} ({zscore:+.1f} SD from baseline)",
                    "severity": "high" if abs(zscore) > 3 else "medium"
                })

    # HRV anomalies (consecutive days of decline)
    if "hrv" in daily_metrics.columns and "hrv" in baselines:
        hrv = daily_metrics["hrv"].dropna()
        baseline = baselines["hrv"]
        drop_threshold = thresholds.get("hrv_drop_threshold", 0.15)
        consecutive_days = thresholds.get("hrv_consecutive_days", 3)

        # Check for sustained drops
        recent = hrv.tail(consecutive_days)
        if len(recent) >= consecutive_days:
            recent_mean = recent.mean()
            if recent_mean < baseline["recent_mean"] * (1 - drop_threshold):
                anomalies.append({
                    "date": recent.index[-1],
                    "metric": "HRV",
                    "value": f"{recent_mean:.0f} ms",
                    "description": f"Sustained drop over {consecutive_days} days (>{drop_threshold*100:.0f}% below baseline)",
                    "severity": "high"
                })

    # VO2 max decline
    if "vo2_max" in daily_metrics.columns and "vo2_max" in baselines:
        vo2 = daily_metrics["vo2_max"].dropna()
        decline_threshold = thresholds.get("vo2_decline_threshold", 2.0)
        window_days = thresholds.get("vo2_decline_window_days", 30)

        if len(vo2) > window_days:
            old_mean = vo2.iloc[-window_days*2:-window_days].mean() if len(vo2) > window_days*2 else vo2.iloc[:-window_days].mean()
            recent_mean = vo2.tail(window_days).mean()

            if old_mean - recent_mean > decline_threshold:
                anomalies.append({
                    "date": vo2.index[-1],
                    "metric": "VO2 Max",
                    "value": f"{recent_mean:.1f}",
                    "description": f"Declined by {old_mean - recent_mean:.1f} over past {window_days} days",
                    "severity": "medium"
                })

    # Sleep efficiency anomalies
    if not sleep_df.empty and "sleep_efficiency" in sleep_df.columns:
        efficiency_threshold = thresholds.get("sleep_efficiency_threshold", 0.75)
        consecutive_nights = thresholds.get("sleep_consecutive_nights", 5)

        eff = sleep_df["sleep_efficiency"].dropna()
        recent = eff.tail(consecutive_nights)

        if len(recent) >= consecutive_nights and (recent < efficiency_threshold).all():
            anomalies.append({
                "date": recent.index[-1],
                "metric": "Sleep Efficiency",
                "value": f"{recent.mean()*100:.0f}%",
                "description": f"Below {efficiency_threshold*100:.0f}% for {consecutive_nights}+ consecutive nights",
                "severity": "medium"
            })

    return sorted(anomalies, key=lambda x: x["date"], reverse=True)


def calculate_week_summary(daily_metrics: pd.DataFrame,
                           daily_load: pd.DataFrame,
                           sleep_df: pd.DataFrame,
                           workouts_df: pd.DataFrame,
                           readiness: pd.DataFrame,
                           week_start: datetime) -> dict:
    """
    Calculate summary statistics for a given week.
    """
    week_end = week_start + timedelta(days=7)

    summary = {
        "week_start": week_start,
        "week_end": week_end,
    }

    # Filter to week
    def filter_week(df):
        if df.empty:
            return df
        return df[(df.index >= week_start) & (df.index < week_end)]

    week_metrics = filter_week(daily_metrics)
    week_load = filter_week(daily_load)
    week_sleep = filter_week(sleep_df)
    week_readiness = filter_week(readiness)

    # Cardiac metrics
    if not week_metrics.empty:
        if "resting_hr" in week_metrics.columns:
            summary["resting_hr_avg"] = week_metrics["resting_hr"].mean()
        if "hrv" in week_metrics.columns:
            summary["hrv_avg"] = week_metrics["hrv"].mean()
        if "vo2_max" in week_metrics.columns:
            summary["vo2_max"] = week_metrics["vo2_max"].dropna().iloc[-1] if not week_metrics["vo2_max"].dropna().empty else None

    # Activity metrics
    if not week_metrics.empty:
        if "steps" in week_metrics.columns:
            summary["steps_avg"] = week_metrics["steps"].mean()
            summary["steps_total"] = week_metrics["steps"].sum()
        if "distance_walk_run" in week_metrics.columns:
            summary["distance_avg"] = week_metrics["distance_walk_run"].mean()
            summary["distance_total"] = week_metrics["distance_walk_run"].sum()
        if "active_calories" in week_metrics.columns:
            summary["active_calories_avg"] = week_metrics["active_calories"].mean()
            summary["active_calories_total"] = week_metrics["active_calories"].sum()

    # Training load
    if not week_load.empty:
        summary["total_tss"] = week_load["tss"].sum()
        summary["total_trimp"] = week_load["trimp"].sum()
        summary["total_duration"] = week_load["duration_minutes"].sum()
        summary["workout_count"] = int(week_load["workout_count"].sum())
        if "acwr" in week_load.columns:
            summary["acwr"] = week_load["acwr"].dropna().iloc[-1] if not week_load["acwr"].dropna().empty else None

    # Sleep
    if not week_sleep.empty:
        summary["sleep_avg"] = week_sleep["total_sleep"].mean()
        summary["sleep_efficiency_avg"] = week_sleep["sleep_efficiency"].mean()
        if "deep_sleep" in week_sleep.columns:
            summary["deep_sleep_avg"] = week_sleep["deep_sleep"].mean()
        if "rem_sleep" in week_sleep.columns:
            summary["rem_sleep_avg"] = week_sleep["rem_sleep"].mean()
        if "sleep_debt" in week_sleep.columns:
            summary["sleep_debt"] = week_sleep["sleep_debt"].iloc[-1]

    # Readiness
    if not week_readiness.empty and "readiness_score" in week_readiness.columns:
        summary["readiness_avg"] = week_readiness["readiness_score"].mean()
        # Most recent status
        recent_status = week_readiness["readiness_status"].dropna()
        summary["readiness_status"] = recent_status.iloc[-1] if not recent_status.empty else None

    return summary


def calculate_month_summary(daily_metrics: pd.DataFrame,
                            daily_load: pd.DataFrame,
                            sleep_df: pd.DataFrame,
                            workouts_df: pd.DataFrame,
                            readiness: pd.DataFrame,
                            month_start: datetime) -> dict:
    """
    Calculate summary statistics for a given month.
    """
    # Get month end
    if month_start.month == 12:
        month_end = datetime(month_start.year + 1, 1, 1)
    else:
        month_end = datetime(month_start.year, month_start.month + 1, 1)

    summary = {
        "month_start": month_start,
        "month_end": month_end,
    }

    # Filter to month
    def filter_month(df):
        if df.empty:
            return df
        return df[(df.index >= month_start) & (df.index < month_end)]

    month_metrics = filter_month(daily_metrics)
    month_load = filter_month(daily_load)
    month_sleep = filter_month(sleep_df)
    month_readiness = filter_month(readiness)

    # Cardiac metrics with statistics
    for metric in ["resting_hr", "hrv", "vo2_max"]:
        if not month_metrics.empty and metric in month_metrics.columns:
            data = month_metrics[metric].dropna()
            if not data.empty:
                summary[f"{metric}_mean"] = data.mean()
                summary[f"{metric}_min"] = data.min()
                summary[f"{metric}_max"] = data.max()
                summary[f"{metric}_std"] = data.std()
                summary[f"{metric}_p25"] = data.quantile(0.25)
                summary[f"{metric}_p75"] = data.quantile(0.75)

    # Training load totals and averages
    if not month_load.empty:
        summary["total_tss"] = month_load["tss"].sum()
        summary["avg_daily_tss"] = month_load["tss"].mean()
        summary["total_duration_hours"] = month_load["duration_minutes"].sum() / 60
        summary["workout_count"] = int(month_load["workout_count"].sum())
        summary["training_days"] = int((month_load["workout_count"] > 0).sum())

    # Sleep statistics
    if not month_sleep.empty:
        for metric in ["total_sleep", "sleep_efficiency", "deep_sleep", "rem_sleep"]:
            if metric in month_sleep.columns:
                data = month_sleep[metric].dropna()
                if not data.empty:
                    summary[f"{metric}_mean"] = data.mean()
                    summary[f"{metric}_std"] = data.std()

    # Readiness average
    if not month_readiness.empty and "readiness_score" in month_readiness.columns:
        summary["readiness_mean"] = month_readiness["readiness_score"].mean()

    # Activity metrics
    if not month_metrics.empty:
        if "steps" in month_metrics.columns:
            data = month_metrics["steps"].dropna()
            if not data.empty:
                summary["steps_mean"] = data.mean()
                summary["steps_total"] = data.sum()
                summary["steps_max"] = data.max()
        if "distance_walk_run" in month_metrics.columns:
            data = month_metrics["distance_walk_run"].dropna()
            if not data.empty:
                summary["distance_mean"] = data.mean()
                summary["distance_total"] = data.sum()
        if "active_calories" in month_metrics.columns:
            data = month_metrics["active_calories"].dropna()
            if not data.empty:
                summary["active_calories_mean"] = data.mean()
                summary["active_calories_total"] = data.sum()

    return summary
