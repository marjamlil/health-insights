//
//  ReadinessEngine.swift
//  HealthInsights
//
//  Swift port of the readiness calculation in src/metrics.py
//  (calculate_readiness_score): HRV and resting-HR z-scores against a
//  rolling personal baseline, combined into a 0–100 score with
//  green/amber/red status. Pure logic — no HealthKit imports — so it
//  stays unit-testable.
//

import Foundation

struct DailyMetric {
    let date: Date
    let hrv: Double?        // SDNN, ms
    let restingHR: Double?  // bpm
}

enum ReadinessStatus: String {
    case green, amber, red

    init(score: Double) {
        switch score {
        case 60...: self = .green
        case 40..<60: self = .amber
        default: self = .red
        }
    }

    var headline: String {
        switch self {
        case .green: return "Ready to train"
        case .amber: return "Take it steady"
        case .red: return "Recovery day"
        }
    }
}

struct ReadinessResult {
    let date: Date
    let score: Double
    let status: ReadinessStatus
    let hrvZScore: Double?
    let rhrZScore: Double?
}

enum ReadinessEngine {

    static let baselineWindowDays = 30
    static let minimumDataPoints = 7

    /// Compute readiness for the most recent day in `metrics`.
    /// Mirrors metrics.py: z-score against the rolling window,
    /// clipped to ±2 SD, mapped to 50 ± 25 points per component.
    static func readiness(for metrics: [DailyMetric]) -> ReadinessResult? {
        let sorted = metrics.sorted { $0.date < $1.date }
        guard let today = sorted.last else { return nil }

        let window = Array(sorted.suffix(baselineWindowDays))

        var componentScores: [Double] = []
        var hrvZ: Double?
        var rhrZ: Double?

        // HRV component: higher than baseline = good
        let hrvValues = window.compactMap(\.hrv)
        if let todayHRV = today.hrv, hrvValues.count >= minimumDataPoints {
            let z = zScore(value: todayHRV, population: hrvValues)
            hrvZ = z
            componentScores.append(50 + clip(z, -2, 2) * 25)
        }

        // Resting HR component: lower than baseline = good
        let rhrValues = window.compactMap(\.restingHR)
        if let todayRHR = today.restingHR, rhrValues.count >= minimumDataPoints {
            let z = zScore(value: todayRHR, population: rhrValues)
            rhrZ = z
            componentScores.append(50 - clip(z, -2, 2) * 25)
        }

        guard !componentScores.isEmpty else { return nil }

        let score = componentScores.reduce(0, +) / Double(componentScores.count)
        return ReadinessResult(
            date: today.date,
            score: score,
            status: ReadinessStatus(score: score),
            hrvZScore: hrvZ,
            rhrZScore: rhrZ
        )
    }

    /// Readiness for every day that has enough trailing history —
    /// used for the 30-day trend chart.
    static func readinessSeries(for metrics: [DailyMetric]) -> [ReadinessResult] {
        let sorted = metrics.sorted { $0.date < $1.date }
        guard sorted.count > minimumDataPoints else { return [] }

        return (minimumDataPoints..<sorted.count).compactMap { i in
            readiness(for: Array(sorted[...i]))
        }
    }

    // MARK: - Maths

    static func zScore(value: Double, population: [Double]) -> Double {
        let mean = population.reduce(0, +) / Double(population.count)
        let variance = population
            .map { ($0 - mean) * ($0 - mean) }
            .reduce(0, +) / Double(population.count - 1)  // sample SD, like pandas
        let sd = sqrt(variance)
        guard sd > 0 else { return 0 }  // metrics.py replaces 0 std with 1; z=0 equivalent here
        return (value - mean) / sd
    }

    static func clip(_ value: Double, _ lower: Double, _ upper: Double) -> Double {
        min(max(value, lower), upper)
    }
}
