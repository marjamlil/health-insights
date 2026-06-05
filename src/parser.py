"""
HealthKit XML Parser

Parses Apple Health export.xml and extracts relevant health data into pandas DataFrames.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from typing import Optional, Union, Dict
import pandas as pd
import numpy as np


# HealthKit quantity type identifiers we care about
QUANTITY_TYPES = {
    "HKQuantityTypeIdentifierHeartRate": "heart_rate",
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_hr",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv",
    "HKQuantityTypeIdentifierVO2Max": "vo2_max",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "active_calories",
    "HKQuantityTypeIdentifierBasalEnergyBurned": "basal_calories",
    "HKQuantityTypeIdentifierStepCount": "steps",
    "HKQuantityTypeIdentifierDistanceWalkingRunning": "distance_walk_run",
    "HKQuantityTypeIdentifierDistanceCycling": "distance_cycling",
    "HKQuantityTypeIdentifierDistanceSwimming": "distance_swimming",
    "HKQuantityTypeIdentifierRespiratoryRate": "respiratory_rate",
}

# Workout type mapping
WORKOUT_TYPES = {
    "HKWorkoutActivityTypeRunning": "Running",
    "HKWorkoutActivityTypeCycling": "Cycling",
    "HKWorkoutActivityTypeSwimming": "Swimming",
    "HKWorkoutActivityTypeWalking": "Walking",
    "HKWorkoutActivityTypeHiking": "Hiking",
    "HKWorkoutActivityTypeTraditionalStrengthTraining": "Strength",
    "HKWorkoutActivityTypeFunctionalStrengthTraining": "Strength",
    "HKWorkoutActivityTypeHighIntensityIntervalTraining": "HIIT",
    "HKWorkoutActivityTypeCoreTraining": "Core",
    "HKWorkoutActivityTypeYoga": "Yoga",
    "HKWorkoutActivityTypePilates": "Pilates",
    "HKWorkoutActivityTypeElliptical": "Elliptical",
    "HKWorkoutActivityTypeRowing": "Rowing",
    "HKWorkoutActivityTypeCrossTraining": "Cross Training",
    "HKWorkoutActivityTypeMixedCardio": "Cardio",
    "HKWorkoutActivityTypeSoccer": "Football",
    "HKWorkoutActivityTypeBasketball": "Basketball",
    "HKWorkoutActivityTypeTennis": "Tennis",
    "HKWorkoutActivityTypeBadminton": "Badminton",
    "HKWorkoutActivityTypeGolf": "Golf",
    "HKWorkoutActivityTypeDownhillSkiing": "Skiing",
    "HKWorkoutActivityTypeSnowSports": "Skiing",
    "HKWorkoutActivityTypeCrossCountrySkiing": "Skiing",
    "HKWorkoutActivityTypeOther": "Other",
}


def parse_datetime(date_str: str) -> datetime:
    """Parse HealthKit datetime string."""
    # Format: 2023-05-15 08:30:00 +0100
    try:
        return datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def parse_export(export_path: Union[str, Path]) -> Dict[str, pd.DataFrame]:
    """
    Parse a HealthKit export.xml file and return DataFrames for each data type.

    Args:
        export_path: Path to export.xml file

    Returns:
        Dictionary with keys: 'records', 'workouts', 'sleep'
    """
    export_path = Path(export_path)
    if not export_path.exists():
        raise FileNotFoundError(f"Export file not found: {export_path}")

    print(f"Parsing HealthKit export: {export_path}")
    print("This may take a few minutes for large exports...")

    # Parse XML iteratively to handle large files
    records = []
    workouts = []
    sleep_records = []

    context = ET.iterparse(str(export_path), events=("end",))

    record_count = 0
    for event, elem in context:
        if elem.tag == "Record":
            record_type = elem.get("type", "")

            # Handle quantity records
            if record_type in QUANTITY_TYPES:
                record = {
                    "type": QUANTITY_TYPES[record_type],
                    "value": float(elem.get("value", 0)),
                    "unit": elem.get("unit", ""),
                    "start_date": parse_datetime(elem.get("startDate")),
                    "end_date": parse_datetime(elem.get("endDate")),
                    "source": elem.get("sourceName", ""),
                }
                records.append(record)

            # Handle sleep records
            elif record_type == "HKCategoryTypeIdentifierSleepAnalysis":
                value = elem.get("value", "")
                sleep_record = {
                    "start_date": parse_datetime(elem.get("startDate")),
                    "end_date": parse_datetime(elem.get("endDate")),
                    "value": value,
                    "source": elem.get("sourceName", ""),
                }
                sleep_records.append(sleep_record)

            record_count += 1
            if record_count % 100000 == 0:
                print(f"  Processed {record_count:,} records...")

            elem.clear()

        elif elem.tag == "Workout":
            workout_type = elem.get("workoutActivityType", "")

            # Extract workout statistics
            stats = {}
            for stat in elem.findall(".//WorkoutStatistics"):
                stat_type = stat.get("type", "")
                if "HeartRate" in stat_type:
                    if "Average" in stat_type or stat.get("average"):
                        stats["avg_hr"] = float(stat.get("average", stat.get("sum", 0)))
                    if "Maximum" in stat_type or stat.get("maximum"):
                        stats["max_hr"] = float(stat.get("maximum", 0))
                    if "Minimum" in stat_type or stat.get("minimum"):
                        stats["min_hr"] = float(stat.get("minimum", 0))
                elif "ActiveEnergyBurned" in stat_type:
                    stats["calories"] = float(stat.get("sum", 0))
                elif "Distance" in stat_type:
                    stats["distance"] = float(stat.get("sum", 0))

            workout = {
                "type": WORKOUT_TYPES.get(workout_type, workout_type.replace("HKWorkoutActivityType", "")),
                "start_date": parse_datetime(elem.get("startDate")),
                "end_date": parse_datetime(elem.get("endDate")),
                "duration_minutes": float(elem.get("duration", 0)),
                "calories": stats.get("calories", float(elem.get("totalEnergyBurned", 0))),
                "distance": stats.get("distance", float(elem.get("totalDistance", 0))),
                "avg_hr": stats.get("avg_hr"),
                "max_hr": stats.get("max_hr"),
                "min_hr": stats.get("min_hr"),
                "source": elem.get("sourceName", ""),
            }
            workouts.append(workout)
            elem.clear()

    print(f"Parsing complete. Found {len(records):,} health records, {len(workouts):,} workouts, {len(sleep_records):,} sleep records.")

    # Convert to DataFrames
    records_df = pd.DataFrame(records)
    workouts_df = pd.DataFrame(workouts)
    sleep_df = pd.DataFrame(sleep_records)

    # Set datetime index
    if not records_df.empty:
        records_df = records_df.dropna(subset=["start_date"])
        records_df = records_df.sort_values("start_date")

    if not workouts_df.empty:
        workouts_df = workouts_df.dropna(subset=["start_date"])
        workouts_df = workouts_df.sort_values("start_date")
        # Dedupe identical rows (sync issues can log the same workout twice)
        before = len(workouts_df)
        workouts_df = workouts_df.drop_duplicates(
            subset=["start_date", "type", "duration_minutes", "source"]
        )
        if len(workouts_df) < before:
            print(f"Removed {before - len(workouts_df)} duplicate workout rows.")

    if not sleep_df.empty:
        sleep_df = sleep_df.dropna(subset=["start_date"])
        sleep_df = sleep_df.sort_values("start_date")

    return {
        "records": records_df,
        "workouts": workouts_df,
        "sleep": sleep_df,
    }


def extract_daily_metrics(records_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate records into daily metrics.

    Returns DataFrame with one row per day, columns for each metric type.
    """
    if records_df.empty:
        return pd.DataFrame()

    df = records_df.copy()
    df["date"] = df["start_date"].dt.date

    # Group by date and type, aggregate appropriately
    daily_data = {}

    for metric_type in df["type"].unique():
        metric_df = df[df["type"] == metric_type]

        if metric_type in ["resting_hr", "hrv", "vo2_max", "respiratory_rate"]:
            # Take daily mean for these
            daily = metric_df.groupby("date")["value"].mean()
        elif metric_type == "heart_rate":
            # For raw HR, we'll compute min/mean/max
            daily = metric_df.groupby("date")["value"].agg(["min", "mean", "max"])
            daily.columns = [f"hr_{c}" for c in daily.columns]
            for col in daily.columns:
                daily_data[col] = daily[col]
            continue
        elif metric_type in ["active_calories", "basal_calories", "steps"]:
            # Sum for cumulative metrics
            daily = metric_df.groupby("date")["value"].sum()
        elif metric_type.startswith("distance"):
            # Sum distances
            daily = metric_df.groupby("date")["value"].sum()
        else:
            daily = metric_df.groupby("date")["value"].mean()

        daily_data[metric_type] = daily

    result = pd.DataFrame(daily_data)
    result.index = pd.to_datetime(result.index)
    result = result.sort_index()

    return result


def process_sleep_data(sleep_df: pd.DataFrame) -> pd.DataFrame:
    """
    Process sleep records into nightly sleep metrics.

    Returns DataFrame with one row per night, with sleep duration,
    time in bed, efficiency, and stage breakdown.
    """
    if sleep_df.empty:
        return pd.DataFrame()

    df = sleep_df.copy()

    # Determine sleep date (use start date, but if after midnight, assign to previous day)
    df["sleep_date"] = df["start_date"].apply(
        lambda x: x.date() if x.hour >= 18 else (x - pd.Timedelta(days=1)).date()
    )

    # Calculate duration for each record
    df["duration_hours"] = (df["end_date"] - df["start_date"]).dt.total_seconds() / 3600

    # Map sleep values to categories
    # HKCategoryValueSleepAnalysis values:
    # InBed = 0, Asleep = 1, Awake = 2,
    # AsleepCore = 3, AsleepDeep = 4, AsleepREM = 5
    sleep_stage_map = {
        "HKCategoryValueSleepAnalysisInBed": "in_bed",
        "HKCategoryValueSleepAnalysisAsleep": "asleep",
        "HKCategoryValueSleepAnalysisAwake": "awake",
        "HKCategoryValueSleepAnalysisAsleepCore": "light",
        "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
        "HKCategoryValueSleepAnalysisAsleepREM": "rem",
    }
    df["stage"] = df["value"].map(sleep_stage_map).fillna("unknown")

    # Aggregate by night
    nightly = []
    for date, group in df.groupby("sleep_date"):
        night_data = {"date": date}

        # Calculate sleep stages
        deep_sleep = group[group["stage"] == "deep"]["duration_hours"].sum()
        rem_sleep = group[group["stage"] == "rem"]["duration_hours"].sum()
        light_sleep = group[group["stage"] == "light"]["duration_hours"].sum()
        awake_time = group[group["stage"] == "awake"]["duration_hours"].sum()
        generic_asleep = group[group["stage"] == "asleep"]["duration_hours"].sum()
        explicit_in_bed = group[group["stage"] == "in_bed"]["duration_hours"].sum()

        # Total sleep = all sleep stages
        total_sleep = deep_sleep + rem_sleep + light_sleep + generic_asleep

        # Determine time_in_bed and whether data is estimated
        has_stage_data = (deep_sleep + rem_sleep + light_sleep) > 0

        # Consolidated sleep window: first record start → last record end.
        # Apple Watch only records once it detects sleep, so this is the honest
        # "tracked sleep" period (not "lights out → alarm").
        sleep_window = (group["end_date"].max() - group["start_date"].min()).total_seconds() / 3600

        # Total sleep: prefer stage sum when stages exist; don't double-count generic Asleep.
        if has_stage_data:
            total_sleep = deep_sleep + rem_sleep + light_sleep
            night_data["estimated"] = False
        elif generic_asleep > 0:
            total_sleep = generic_asleep
            night_data["estimated"] = False
        elif explicit_in_bed > 0:
            total_sleep = explicit_in_bed * 0.90
            night_data["estimated"] = True
        else:
            total_sleep = 0
            night_data["estimated"] = True

        night_data["time_in_bed"] = sleep_window
        night_data["total_sleep"] = total_sleep
        night_data["deep_sleep"] = deep_sleep
        night_data["rem_sleep"] = rem_sleep
        night_data["light_sleep"] = light_sleep
        night_data["awake_time"] = awake_time

        # Efficiency = sleep stages / consolidated window. No cap — let the value be honest.
        if sleep_window > 0 and total_sleep > 0:
            night_data["sleep_efficiency"] = total_sleep / sleep_window
        else:
            night_data["sleep_efficiency"] = None

        # Bedtime and wake time
        night_data["bedtime"] = group["start_date"].min()
        night_data["wake_time"] = group["end_date"].max()

        nightly.append(night_data)

    result = pd.DataFrame(nightly)
    if not result.empty:
        result["date"] = pd.to_datetime(result["date"])
        result = result.set_index("date").sort_index()

    return result


def backfill_workout_hr(workouts_df: pd.DataFrame,
                         records_df: pd.DataFrame) -> pd.DataFrame:
    """
    For workouts with no avg_hr (e.g. Strava-logged via watch but HR stripped on sync),
    derive avg_hr / max_hr / min_hr from raw HKQuantityTypeIdentifierHeartRate samples
    falling inside the workout window. Uses real measured HR — no estimation.
    """
    if workouts_df.empty or records_df.empty:
        return workouts_df

    hr = records_df[records_df["type"] == "heart_rate"][["start_date", "value"]]
    if hr.empty:
        return workouts_df

    hr = hr.sort_values("start_date").reset_index(drop=True)
    hr_times = hr["start_date"].values
    hr_values = hr["value"].values

    df = workouts_df.copy()
    needs_hr = df["avg_hr"].isna()
    if not needs_hr.any():
        return df

    print(f"  Backfilling HR for {int(needs_hr.sum())} workouts from raw samples...")
    backfilled = 0

    for idx in df.index[needs_hr]:
        start = df.at[idx, "start_date"]
        end = df.at[idx, "end_date"]
        if pd.isna(start) or pd.isna(end):
            continue
        s_dt = pd.Timestamp(start).to_datetime64()
        e_dt = pd.Timestamp(end).to_datetime64()
        s_idx = np.searchsorted(hr_times, s_dt, side="left")
        e_idx = np.searchsorted(hr_times, e_dt, side="right")
        if e_idx > s_idx:
            window = hr_values[s_idx:e_idx]
            df.at[idx, "avg_hr"] = float(window.mean())
            df.at[idx, "max_hr"] = float(window.max())
            df.at[idx, "min_hr"] = float(window.min())
            backfilled += 1

    missing = int(needs_hr.sum()) - backfilled
    print(f"  HR backfilled for {backfilled} workouts ({missing} had no HR samples in window).")
    return df


def save_processed_data(data: dict, output_dir: Union[str, Path]):
    """Save processed DataFrames to CSV files."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, df in data.items():
        if not df.empty:
            filepath = output_dir / f"{name}.csv"
            df.to_csv(filepath)
            print(f"Saved {name} to {filepath}")


def load_processed_data(data_dir: Union[str, Path]) -> Dict[str, pd.DataFrame]:
    """Load previously processed data from CSV files."""
    data_dir = Path(data_dir)
    data = {}

    for csv_file in data_dir.glob("*.csv"):
        name = csv_file.stem
        df = pd.read_csv(csv_file, index_col=0, parse_dates=True)
        data[name] = df
        print(f"Loaded {name}: {len(df)} records")

    return data
