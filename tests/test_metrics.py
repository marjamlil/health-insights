"""Unit tests for the derived-metric calculation core (src/metrics.py)."""

import numpy as np
import pandas as pd
import pytest

from src.metrics import (
    calculate_acute_chronic_ratio,
    calculate_daily_training_load,
    calculate_hr_zone_distribution,
    calculate_personal_baselines,
    calculate_readiness_score,
    calculate_sleep_debt,
    calculate_training_stress_score,
    calculate_trimp,
    estimate_max_hr,
    get_hr_zone,
)

CONFIG = {
    "hr_zones": {
        "zone1": [0.50, 0.60],
        "zone2": [0.60, 0.70],
        "zone3": [0.70, 0.80],
        "zone4": [0.80, 0.90],
        "zone5": [0.90, 1.00],
    },
    "baselines": {"rolling_window_days": 30, "min_data_points": 7},
}


class TestTrimp:
    def test_matches_banister_formula(self):
        # 60 min at 160 bpm, max 190, resting 50:
        # HRR = (160-50)/(190-50) = 0.7857
        hrr = (160 - 50) / (190 - 50)
        expected = 60 * hrr * np.exp(1.92 * hrr)
        assert calculate_trimp(60, 160, 190, 50) == pytest.approx(expected)

    def test_zero_when_avg_hr_at_or_below_resting(self):
        assert calculate_trimp(60, 50, 190, 50) == 0
        assert calculate_trimp(60, 45, 190, 50) == 0

    def test_zero_for_missing_hr(self):
        assert calculate_trimp(60, np.nan, 190, 50) == 0

    def test_female_weighting_is_lower(self):
        male = calculate_trimp(60, 150, 190, 50, gender="male")
        female = calculate_trimp(60, 150, 190, 50, gender="female")
        assert female < male

    def test_monotonic_in_intensity(self):
        easy = calculate_trimp(60, 120, 190, 50)
        hard = calculate_trimp(60, 170, 190, 50)
        assert hard > easy

    def test_hrr_clamped_above_max(self):
        # avg_hr above max_hr clamps HRR at 1, not beyond
        at_max = calculate_trimp(60, 190, 190, 50)
        above_max = calculate_trimp(60, 210, 190, 50)
        assert above_max == pytest.approx(at_max)


class TestTss:
    def test_threshold_hour_is_100(self):
        assert calculate_training_stress_score(100, threshold_trimp=100) == 100

    def test_scales_linearly(self):
        assert calculate_training_stress_score(50) == pytest.approx(50)
        assert calculate_training_stress_score(200) == pytest.approx(200)


class TestDailyTrainingLoad:
    def test_groups_same_day_workouts(self):
        workouts = pd.DataFrame({
            "start_date": ["2026-01-05 07:00:00", "2026-01-05 18:00:00", "2026-01-06 07:00:00"],
            "trimp": [80.0, 40.0, 100.0],
            "tss": [80.0, 40.0, 100.0],
            "duration_minutes": [45.0, 30.0, 60.0],
            "calories": [400.0, 250.0, 550.0],
            "type": ["Running", "Cycling", "Running"],
        })
        daily = calculate_daily_training_load(workouts)
        assert len(daily) == 2
        assert daily.iloc[0]["tss"] == 120.0
        assert daily.iloc[0]["workout_count"] == 2

    def test_empty_input(self):
        assert calculate_daily_training_load(pd.DataFrame()).empty


class TestAcuteChronicRatio:
    @staticmethod
    def _constant_load(days: int, tss: float = 100.0) -> pd.DataFrame:
        idx = pd.date_range("2026-01-01", periods=days)
        return pd.DataFrame({"tss": tss}, index=idx)

    def test_steady_training_gives_ratio_of_one(self):
        result = calculate_acute_chronic_ratio(self._constant_load(35))
        assert result["acwr"].iloc[-1] == pytest.approx(1.0)

    def test_sudden_ramp_raises_ratio(self):
        load = self._constant_load(35, tss=50.0)
        load.iloc[-7:] = 150.0  # tripled load in the final week
        result = calculate_acute_chronic_ratio(load)
        assert result["acwr"].iloc[-1] > 1.4  # injury-risk territory

    def test_rest_days_filled_as_zero(self):
        # Workouts only on two days, 10 days apart — gap days count as rest
        idx = pd.to_datetime(["2026-01-01", "2026-01-11"])
        load = pd.DataFrame(
            {"tss": [100.0, 100.0]}, index=idx
        )
        result = calculate_acute_chronic_ratio(load)
        assert len(result) == 11  # full date range reindexed


class TestReadinessScore:
    @staticmethod
    def _stable_metrics(days: int = 40) -> pd.DataFrame:
        rng = np.random.default_rng(7)
        return pd.DataFrame({
            "hrv": 50 + rng.normal(0, 2, days),
            "resting_hr": 55 + rng.normal(0, 1, days),
        })

    def test_stable_metrics_average_near_50(self):
        # Individual days swing with z-score noise; the average of a stable
        # series should sit near the 50-point baseline.
        result = calculate_readiness_score(self._stable_metrics(), CONFIG)
        recent = result["readiness_score"].dropna().tail(10)
        assert 40 < recent.mean() < 60

    def test_hrv_spike_raises_score(self):
        df = self._stable_metrics()
        df.loc[df.index[-1], "hrv"] = 75  # well above baseline
        df.loc[df.index[-1], "resting_hr"] = 50  # well below baseline
        result = calculate_readiness_score(df, CONFIG)
        assert result["readiness_score"].iloc[-1] > 60
        assert result["readiness_status"].iloc[-1] == "green"

    def test_suppressed_recovery_flags_red(self):
        df = self._stable_metrics()
        df.loc[df.index[-1], "hrv"] = 30   # crashed HRV
        df.loc[df.index[-1], "resting_hr"] = 68  # elevated resting HR
        result = calculate_readiness_score(df, CONFIG)
        assert result["readiness_score"].iloc[-1] < 40
        assert result["readiness_status"].iloc[-1] == "red"

    def test_empty_input(self):
        assert calculate_readiness_score(pd.DataFrame(), CONFIG).empty


class TestSleepDebt:
    def test_accumulates_deficit(self):
        sleep = pd.DataFrame({"total_sleep": [6.5, 6.5, 6.5, 6.5]})
        result = calculate_sleep_debt(sleep, target_hours=7.5)
        assert result["sleep_debt"].iloc[-1] == pytest.approx(-4.0)

    def test_surplus_offsets_debt(self):
        sleep = pd.DataFrame({"total_sleep": [6.5, 8.5]})
        result = calculate_sleep_debt(sleep, target_hours=7.5)
        assert result["sleep_debt"].iloc[-1] == pytest.approx(0.0)

    def test_debt_capped_at_20_hours(self):
        sleep = pd.DataFrame({"total_sleep": [4.0] * 30})  # -3.5/night
        result = calculate_sleep_debt(sleep, target_hours=7.5)
        assert result["sleep_debt"].min() == -20


class TestPersonalBaselines:
    def test_requires_minimum_data_points(self):
        df = pd.DataFrame({"resting_hr": [55, 56, 57]})  # < 7 points
        assert "resting_hr" not in calculate_personal_baselines(df, CONFIG)

    def test_computes_expected_statistics(self):
        values = [50.0, 52.0, 54.0, 56.0, 58.0, 60.0, 62.0, 64.0]
        df = pd.DataFrame({"hrv": values})
        baselines = calculate_personal_baselines(df, CONFIG)
        assert baselines["hrv"]["mean"] == pytest.approx(np.mean(values))
        assert baselines["hrv"]["min"] == 50.0
        assert baselines["hrv"]["max"] == 64.0


class TestHrZones:
    def test_tanaka_estimate(self):
        assert estimate_max_hr(35) == pytest.approx(208 - 0.7 * 35)

    def test_zone_boundaries(self):
        zones = CONFIG["hr_zones"]
        max_hr = 180.0
        assert get_hr_zone(100, max_hr, zones) == 1   # 56%
        assert get_hr_zone(120, max_hr, zones) == 2   # 67%
        assert get_hr_zone(135, max_hr, zones) == 3   # 75%
        assert get_hr_zone(150, max_hr, zones) == 4   # 83%
        assert get_hr_zone(170, max_hr, zones) == 5   # 94%

    def test_zone_distribution_percentages(self):
        workouts = pd.DataFrame({
            "avg_hr": [100.0, 150.0],          # zone 1 and zone 4 at max_hr 180
            "duration_minutes": [60.0, 60.0],
        })
        config = {"hr_zones": {**CONFIG["hr_zones"], "max_hr": 180}}
        dist = calculate_hr_zone_distribution(workouts, config)
        assert dist[1] == pytest.approx(50.0)
        assert dist[4] == pytest.approx(50.0)
        assert dist[5] == 0.0
