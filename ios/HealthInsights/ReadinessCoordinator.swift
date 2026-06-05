//
//  ReadinessCoordinator.swift
//  HealthInsights
//
//  Orchestrates the daily cycle: fetch metrics → compute readiness →
//  persist for the widget → notify. Called on app launch, from the
//  HealthKit observer, and from the manual refresh control.
//

import Foundation
import WidgetKit

@MainActor
final class ReadinessCoordinator: ObservableObject {

    static let shared = ReadinessCoordinator()

    /// Shared with the widget via an App Group container.
    static let appGroupID = "group.com.marklilburn.healthinsights"

    @Published var today: ReadinessResult?
    @Published var series: [ReadinessResult] = []
    @Published var lastError: String?

    func refresh() async {
        do {
            let metrics = try await HealthKitManager.shared.fetchDailyMetrics()
            guard let result = ReadinessEngine.readiness(for: metrics) else {
                lastError = "Not enough data yet — need \(ReadinessEngine.minimumDataPoints)+ days of HRV or resting HR."
                return
            }
            today = result
            series = ReadinessEngine.readinessSeries(for: metrics)
            lastError = nil

            persistForWidget(result)
            await NotificationManager.shared.notifyIfNeeded(for: result)
        } catch {
            lastError = error.localizedDescription
        }
    }

    // MARK: - Widget handoff

    private func persistForWidget(_ result: ReadinessResult) {
        let defaults = UserDefaults(suiteName: Self.appGroupID)
        defaults?.set(result.score, forKey: "readiness.score")
        defaults?.set(result.status.rawValue, forKey: "readiness.status")
        defaults?.set(result.date, forKey: "readiness.date")
        WidgetCenter.shared.reloadAllTimelines()
    }
}
