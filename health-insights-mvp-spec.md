# Health Insights MVP Specification

## Overview

A personal health analytics tool that processes Apple HealthKit data and generates actionable insights through weekly and monthly PDF reports. The tool goes beyond standard Apple Health metrics to provide derived insights, trend analysis, anomaly detection, and training load monitoring.

---

## User Profile

- **User:** Mark Lilburn
- **Data source:** Apple Watch (since May 2023, ~2.5 years history)
- **Primary fitness goal:** Endurance improvement (aerobic capacity)
- **Workout variety:** Running, cycling, swimming, HIIT, strength training, sports
- **Technical context:** Technical engineer mindset, not a developer; B-Secur PM (biosensing algorithms)
- **Health context:** Standard healthy adult, no conditions requiring special handling

---

## Data Access

### MVP Approach
- **Manual export** from Apple Health app
- Export full history as XML/ZIP
- Process locally on Mac

### Export Location
```
~/Documents/health-reports/exports/
```

### Future Enhancement (v2)
- Build minimal iOS connector app, or
- Integrate Health Auto Export with automated sync

---

## Storage Structure

```
~/Documents/health-reports/
├── exports/           # Raw HealthKit XML exports
├── data/              # Processed/cleaned data (CSV/JSON)
├── reports/           # Generated PDF reports
│   ├── weekly/
│   └── monthly/
└── config/            # User settings, targets, baselines
```

---

## Report Types

### Weekly Summary Report

**Format:** Single-page dense dashboard (PDF)
**Cadence:** Every Monday (scheduled) + on-demand
**Style:** Clean, minimal, Apple Health-like aesthetic

**Content sections:**

1. **Quick Status** (top of page)
   - Readiness indicator (green/amber/red based on HRV + resting HR)
   - Week summary: "Training load: moderate | Sleep: good | Recovery: optimal"
   - Any anomalies flagged (conservative threshold)

2. **Cardiac Health**
   - Resting HR: weekly average vs baseline vs population norm
   - HRV: weekly average + trend arrow (up/down/stable)
   - VO2 max: current value + trend vs target (if set)

3. **Training Load**
   - Weekly TSS/TRIMP score
   - Acute:Chronic workload ratio (with injury risk zone indicator)
   - HR zone distribution (% time in each zone)
   - Workout count and total duration

4. **Sleep**
   - Average sleep duration vs baseline
   - Sleep efficiency %
   - Deep sleep + REM averages
   - Sleep debt indicator

5. **Week-over-Week Comparison**
   - Key metrics vs previous week (delta indicators)
   - Trend direction for core metrics

### Monthly Deep-Dive Report

**Format:** Multi-page PDF (executive summary + detail sections)
**Cadence:** 1st of each month (scheduled) + on-demand
**Style:** Clean, minimal, Apple Health-like aesthetic

**Content sections:**

1. **Executive Summary** (page 1)
   - Month overview: key wins, concerns, recommendations
   - 3-5 bullet points of actionable insights
   - Overall health trajectory (improving/stable/declining)

2. **Cardiac Health Analysis** (pages 2-3)
   - 30-day trend charts: resting HR, HRV, VO2 max
   - HR recovery analysis (post-workout recovery curves)
   - Resting HR vs training load correlation
   - Month statistics: mean, range, percentiles
   - Comparison to previous month and same month last year

3. **Training Analysis** (pages 3-4)
   - Monthly training load trend
   - Acute:Chronic ratio progression
   - Workout breakdown by type
   - Volume trends with periodisation notes
   - TSS/TRIMP distribution

4. **Sleep Analysis** (pages 4-5)
   - 30-day sleep trend charts
   - Sleep stage distribution (deep, REM, light)
   - Sleep efficiency trends
   - Sleep vs recovery correlation analysis
   - Sleep debt running total
   - Consistency score (bedtime/wake time regularity)

5. **Anomaly Log** (page 5-6)
   - Notable events highlighted with dates
   - Unusual readings explained
   - Pattern breaks flagged

6. **Comparative Benchmarking** (page 6)
   - Month vs previous month
   - Month vs same period last year (if available)
   - Progress toward targets (if set)
   - Personal bests/notable achievements

7. **Recommendations** (final page)
   - Specific actionable guidance for next month
   - Areas to focus on
   - Suggested adjustments based on data

---

## Core Metrics & Derived Insights

### From HealthKit (Raw Data)

| Category | Metrics |
|----------|---------|
| Heart | Resting heart rate, heart rate samples, HRV (SDNN), VO2 max |
| Sleep | Sleep analysis (in bed, asleep, stages), sleep duration |
| Activity | Active calories, basal calories, step count, distance |
| Workouts | Type, duration, HR data, calories, distance (where applicable) |

### Derived Metrics (Calculated)

| Metric | Description | Calculation Approach |
|--------|-------------|---------------------|
| **Training Stress Score (TSS)** | Workout intensity quantification | Based on HR zones, duration, intensity factor |
| **TRIMP** | Training impulse | HR-based load calculation |
| **Acute:Chronic Workload Ratio** | Injury risk indicator | 7-day load / 28-day rolling average |
| **Readiness Score** | Daily recovery status | Composite of HRV, resting HR vs baseline |
| **HR Recovery** | Post-workout recovery rate | HR drop at 1min, 2min post-workout |
| **Sleep Efficiency** | Quality of time in bed | Time asleep / time in bed |
| **Sleep Debt** | Cumulative under-sleep | Difference from baseline need, rolling sum |
| **HR Zone Distribution** | Training intensity profile | % time in each zone per workout/week |

### Baseline Approach

- **Primary:** Learn personal baselines from user's historical data
- **Secondary:** Display population norms for context
- **Adaptation:** Baselines update as more data is collected (rolling windows)

### Anomaly Detection

**Sensitivity:** Conservative (high confidence, fewer false positives)

**Triggers:**
- Resting HR: >2 standard deviations from 30-day rolling baseline
- HRV: Significant drop (>15%) from baseline over 3+ consecutive days
- Sleep: Efficiency <75% for 5+ consecutive nights
- VO2 max: Decline of >2 points over 30 days despite maintained training

**Output:** Flag in report with date, metric, deviation from normal

---

## Goal Tracking

### Optional Targets (User-Configurable)

```yaml
# Example config
targets:
  vo2_max: 50
  resting_hr: 55  # lower is better
  weekly_training_hours: 6
  sleep_duration: 7.5
```

### Trend Display

- Always show trend direction (improving/stable/declining)
- If target set: show progress toward target
- If no target: show trajectory and historical context

---

## Data Handling

### Missing Data

- Flag gaps clearly in reports
- Continue analysis with available data
- Note data completeness % for each metric
- Do not interpolate (keep data honest)

### External Factors

- MVP: HealthKit data only
- No manual annotations in v1
- No weather integration in v1

---

## Technical Implementation

### Language/Framework

- **Python** (data analysis, report generation)
- **pandas** for data manipulation
- **matplotlib/seaborn** for charts (clean, minimal style)
- **ReportLab** or **WeasyPrint** for PDF generation

### Trigger Methods

1. **CLI commands:**
   ```bash
   health-report weekly          # Generate weekly report
   health-report monthly         # Generate monthly report
   health-report import <file>   # Import new HealthKit export
   ```

2. **Scheduled (cron/launchd):**
   - Weekly: Monday 7:00 AM
   - Monthly: 1st of month 7:00 AM

### Processing Pipeline

1. **Import:** Parse HealthKit XML export
2. **Clean:** Handle data types, missing values, duplicates
3. **Store:** Save processed data to CSV/JSON
4. **Analyse:** Calculate derived metrics
5. **Detect:** Run anomaly detection
6. **Generate:** Create PDF report
7. **Archive:** Store report in dated folder

---

## MVP Success Criteria

The MVP is complete when:

1. **Weekly report** generates successfully with:
   - Readiness indicator
   - Cardiac metrics (resting HR, HRV, VO2 max)
   - Training load (TSS/TRIMP, acute:chronic ratio)
   - Sleep summary
   - Week-over-week comparison

2. **Monthly report** generates successfully with:
   - Executive summary
   - 30-day trend charts for all key metrics
   - Anomaly log
   - Comparative benchmarking (month-over-month)
   - Actionable recommendations

3. **Both reports:**
   - Generate via CLI command
   - Can be scheduled via cron
   - Use personal baselines with population norm context
   - Flag anomalies conservatively
   - Clean, Apple Health-like visual style

4. **Data pipeline:**
   - Successfully parses HealthKit XML export
   - Handles 2.5 years of historical data
   - Stores processed data for incremental updates

---

## Future Enhancements (Post-MVP)

| Priority | Enhancement |
|----------|-------------|
| High | iOS connector app for automated data sync |
| High | Year-over-year comparison in reports |
| Medium | Manual annotations for context (travel, illness) |
| Medium | Interactive dashboard (web-based) |
| Low | Weather data integration |
| Low | Export to other formats (HTML, Notion) |

---

## Open Questions

None - spec is complete based on requirements interview.

---

## Appendix: HealthKit Data Types

Key HKQuantityType identifiers to extract:

```
HKQuantityTypeIdentifierHeartRate
HKQuantityTypeIdentifierRestingHeartRate
HKQuantityTypeIdentifierHeartRateVariabilitySDNN
HKQuantityTypeIdentifierVO2Max
HKQuantityTypeIdentifierActiveEnergyBurned
HKQuantityTypeIdentifierBasalEnergyBurned
HKQuantityTypeIdentifierStepCount
HKQuantityTypeIdentifierDistanceWalkingRunning
HKQuantityTypeIdentifierDistanceCycling
HKQuantityTypeIdentifierDistanceSwimming
HKQuantityTypeIdentifierRespiratoryRate
```

Key HKCategoryType identifiers:

```
HKCategoryTypeIdentifierSleepAnalysis
```

Workout data:

```
HKWorkout (with associated HKWorkoutActivityType)
```

---

*Spec version: 1.0*
*Created: 2025-01-29*
*Author: Claude (from requirements interview with Mark Lilburn)*
