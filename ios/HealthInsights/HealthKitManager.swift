//
//  HealthKitManager.swift
//  HealthInsights
//
//  Reads HRV (SDNN) and resting heart rate from HealthKit, aggregated
//  to daily values, and registers for background delivery so readiness
//  recomputes when overnight data lands.
//

import Foundation
import HealthKit

@MainActor
final class HealthKitManager: ObservableObject {

    static let shared = HealthKitManager()

    private let store = HKHealthStore()

    private let hrvType = HKQuantityType(.heartRateVariabilitySDNN)
    private let rhrType = HKQuantityType(.restingHeartRate)

    @Published var authorised = false

    // MARK: - Authorisation

    func requestAuthorisation() async throws {
        guard HKHealthStore.isHealthDataAvailable() else {
            throw HealthKitError.unavailable
        }
        try await store.requestAuthorization(toShare: [], read: [hrvType, rhrType])
        authorised = true
    }

    // MARK: - Daily metrics

    /// Fetch the last `days` of daily HRV and resting HR.
    /// HRV: mean of the day's SDNN samples (Apple logs several overnight).
    /// Resting HR: Apple writes one summary sample per day; we take the mean.
    func fetchDailyMetrics(days: Int = 37) async throws -> [DailyMetric] {
        let calendar = Calendar.current
        let end = calendar.startOfDay(for: .now).addingTimeInterval(86_400)
        guard let start = calendar.date(byAdding: .day, value: -days, to: end) else {
            return []
        }

        async let hrvByDay = dailyAverages(for: hrvType, unit: .secondUnit(with: .milli), from: start, to: end)
        async let rhrByDay = dailyAverages(for: rhrType, unit: HKUnit.count().unitDivided(by: .minute()), from: start, to: end)

        let (hrv, rhr) = try await (hrvByDay, rhrByDay)

        let allDates = Set(hrv.keys).union(rhr.keys)
        return allDates.sorted().map { date in
            DailyMetric(date: date, hrv: hrv[date], restingHR: rhr[date])
        }
    }

    private func dailyAverages(for type: HKQuantityType,
                               unit: HKUnit,
                               from start: Date,
                               to end: Date) async throws -> [Date: Double] {
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end)

        return try await withCheckedThrowingContinuation { continuation in
            let query = HKStatisticsCollectionQuery(
                quantityType: type,
                quantitySamplePredicate: predicate,
                options: .discreteAverage,
                anchorDate: Calendar.current.startOfDay(for: start),
                intervalComponents: DateComponents(day: 1)
            )
            query.initialResultsHandler = { _, results, error in
                if let error {
                    continuation.resume(throwing: error)
                    return
                }
                var byDay: [Date: Double] = [:]
                results?.enumerateStatistics(from: start, to: end) { stats, _ in
                    if let avg = stats.averageQuantity() {
                        byDay[stats.startDate] = avg.doubleValue(for: unit)
                    }
                }
                continuation.resume(returning: byDay)
            }
            store.execute(query)
        }
    }

    // MARK: - Background delivery

    /// Ask HealthKit to wake the app when new HRV data arrives
    /// (typically once overnight data syncs from the watch).
    func enableBackgroundDelivery() {
        store.enableBackgroundDelivery(for: hrvType, frequency: .daily) { _, _ in }

        let query = HKObserverQuery(sampleType: hrvType, predicate: nil) { _, completion, _ in
            Task { @MainActor in
                await ReadinessCoordinator.shared.refresh()
                completion()
            }
        }
        store.execute(query)
    }

    enum HealthKitError: Error {
        case unavailable
    }
}
