"""Generate synthetic sample data so the pipeline runs without a real HealthKit export.

Produces six months of plausible daily metrics, workouts and sleep for a
fictional recreational runner, written to sample_data/. Deterministic
(seeded) so the demo report is reproducible.

Usage:
    python scripts/generate_sample_data.py
    health-report weekly --output reports/sample-weekly.pdf   # after pointing
                                                              # paths.data at sample_data/
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.metrics import calculate_trimp, calculate_training_stress_score  # noqa: E402

RNG = np.random.default_rng(42)
OUT_DIR = Path(__file__).parent.parent / "sample_data"

START = datetime(2026, 1, 1)
DAYS = 180

# Fictional athlete profile
BASE_RESTING_HR = 56.0
BASE_HRV = 52.0
BASE_VO2 = 44.0
MAX_HR = 188


def daily_metrics() -> pd.DataFrame:
    dates = [START + timedelta(days=i) for i in range(DAYS)]
    t = np.arange(DAYS)

    # Slow fitness improvement + weekly rhythm + noise
    fitness_trend = np.linspace(0, 1, DAYS)
    weekly = np.sin(2 * np.pi * t / 7)

    resting_hr = BASE_RESTING_HR - 2.5 * fitness_trend + 1.2 * weekly + RNG.normal(0, 1.4, DAYS)
    hrv = BASE_HRV + 6 * fitness_trend - 2.0 * weekly + RNG.normal(0, 5.5, DAYS)
    vo2 = BASE_VO2 + 1.8 * fitness_trend + RNG.normal(0, 0.35, DAYS)

    # A rough week in March: illness suppresses HRV, raises resting HR
    rough = (t >= 70) & (t < 78)
    resting_hr[rough] += np.linspace(4, 1, rough.sum())
    hrv[rough] -= np.linspace(12, 3, rough.sum())

    steps = np.clip(RNG.normal(9000, 2600, DAYS), 1500, 22000)
    active_cal = np.clip(RNG.normal(520, 180, DAYS), 120, 1400)

    return pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "steps": steps.round(0),
        "distance_walk_run": (steps / 1320).round(2),
        "hr_min": (resting_hr - RNG.uniform(2, 5, DAYS)).round(0),
        "hr_mean": (resting_hr + RNG.uniform(18, 26, DAYS)).round(0),
        "hr_max": (resting_hr + RNG.uniform(70, 105, DAYS)).round(0),
        "active_calories": active_cal.round(0),
        "basal_calories": RNG.normal(1750, 40, DAYS).round(0),
        "resting_hr": resting_hr.round(0),
        "hrv": hrv.round(1),
        "vo2_max": vo2.round(1),
        "respiratory_rate": RNG.normal(14.5, 0.7, DAYS).round(1),
        "distance_swimming": 0.0,
        "distance_cycling": 0.0,
    })


def workouts() -> pd.DataFrame:
    rows = []
    # (type, avg_hr mean, avg_hr sd) — spread across zones like a real training mix
    session_types = [
        ("Running", 152, 8),                       # tempo run
        ("Running", 134, 7),                       # easy run
        ("Running", 162, 6),                       # intervals
        ("Cycling", 128, 9),                       # endurance ride
        ("FunctionalStrengthTraining", 118, 8),    # gym
    ]
    for i in range(DAYS):
        day = START + timedelta(days=i)
        # ~4 sessions a week, none during the rough patch
        if 70 <= i < 78 or RNG.random() > 0.57:
            continue
        wtype, hr_mean, hr_sd = session_types[RNG.integers(0, len(session_types))]
        duration = float(np.clip(RNG.normal(48, 16), 20, 120))
        avg_hr = float(np.clip(RNG.normal(hr_mean, hr_sd), 105, 175))
        # TRIMP/TSS are stored at import time in the real pipeline, so the
        # sample data carries real values computed with the same formula
        trimp = calculate_trimp(duration, avg_hr, max_hr=MAX_HR,
                                resting_hr=BASE_RESTING_HR)
        tss = calculate_training_stress_score(trimp)
        start_t = day.replace(hour=int(RNG.integers(6, 19)), minute=int(RNG.integers(0, 59)))
        rows.append({
            "type": wtype,
            "start_date": start_t.strftime("%Y-%m-%d %H:%M:%S"),
            "end_date": (start_t + timedelta(minutes=duration)).strftime("%Y-%m-%d %H:%M:%S"),
            "duration_minutes": round(duration, 1),
            "calories": round(duration * RNG.uniform(7, 11), 0),
            "distance": round(duration / 5.6, 2) if wtype == "Running" else round(duration / 2.1, 2),
            "avg_hr": round(avg_hr, 0),
            "max_hr": round(min(avg_hr + RNG.uniform(15, 30), MAX_HR), 0),
            "min_hr": round(avg_hr - RNG.uniform(25, 40), 0),
            "source": "Apple Watch",
            "trimp": round(trimp, 1),
            "tss": round(tss, 1),
            "intensity_factor": round(avg_hr / (MAX_HR * 0.85), 2),
        })
    return pd.DataFrame(rows)


def sleep() -> pd.DataFrame:
    rows = []
    for i in range(DAYS):
        day = START + timedelta(days=i)
        time_in_bed = float(np.clip(RNG.normal(7.9, 0.8), 5.0, 10.0))
        efficiency = float(np.clip(RNG.normal(0.91, 0.04), 0.72, 0.98))
        # Poorer sleep during the rough patch
        if 70 <= i < 78:
            time_in_bed = max(5.0, time_in_bed - 1.2)
            efficiency = max(0.70, efficiency - 0.12)
        total = time_in_bed * efficiency
        bedtime = day.replace(hour=23, minute=int(RNG.integers(0, 59)))
        rows.append({
            "date": day.strftime("%Y-%m-%d"),
            "estimated": False,
            "time_in_bed": round(time_in_bed, 2),
            "total_sleep": round(total, 2),
            "deep_sleep": round(total * RNG.uniform(0.13, 0.20), 2),
            "rem_sleep": round(total * RNG.uniform(0.18, 0.26), 2),
            "light_sleep": round(total * RNG.uniform(0.50, 0.62), 2),
            "awake_time": round(time_in_bed - total, 2),
            "sleep_efficiency": round(efficiency, 2),
            "bedtime": bedtime.strftime("%Y-%m-%d %H:%M:%S"),
            "wake_time": (bedtime + timedelta(hours=time_in_bed)).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return pd.DataFrame(rows)


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    daily_metrics().to_csv(OUT_DIR / "daily_metrics.csv", index=False)
    workouts().to_csv(OUT_DIR / "workouts.csv")
    sleep().to_csv(OUT_DIR / "sleep.csv", index=False)
    print(f"Sample data written to {OUT_DIR}/ "
          f"({DAYS} days, {len(workouts())} workouts)")


if __name__ == "__main__":
    main()
