//
//  NotificationManager.swift
//  HealthInsights
//
//  Local notifications only — nothing leaves the device. One readiness
//  notification per day, fired when fresh overnight data produces a
//  score. iPhone notifications mirror to Apple Watch automatically.
//

import Foundation
import UserNotifications

@MainActor
final class NotificationManager {

    static let shared = NotificationManager()

    private let lastNotifiedKey = "notifications.lastNotifiedDay"

    func requestAuthorisation() async {
        let centre = UNUserNotificationCenter.current()
        _ = try? await centre.requestAuthorization(options: [.alert, .sound, .badge])
    }

    /// Notify once per calendar day, when a readiness result is available.
    func notifyIfNeeded(for result: ReadinessResult) async {
        let dayKey = ISO8601DateFormatter.dayOnly.string(from: result.date)
        let defaults = UserDefaults.standard
        guard defaults.string(forKey: lastNotifiedKey) != dayKey else { return }

        let content = UNMutableNotificationContent()
        content.title = "Readiness \(Int(result.score.rounded())) — \(result.status.headline)"
        content.body = body(for: result)
        content.sound = .default

        let request = UNNotificationRequest(
            identifier: "readiness-\(dayKey)",
            content: content,
            trigger: nil  // deliver immediately; we're called when data lands
        )

        do {
            try await UNUserNotificationCenter.current().add(request)
            defaults.set(dayKey, forKey: lastNotifiedKey)
        } catch {
            // Notification permission denied — nothing to do
        }
    }

    private func body(for result: ReadinessResult) -> String {
        var parts: [String] = []
        if let z = result.hrvZScore {
            parts.append(z >= 0 ? "HRV above baseline" : "HRV below baseline")
        }
        if let z = result.rhrZScore {
            parts.append(z <= 0 ? "resting HR below baseline" : "resting HR elevated")
        }
        return parts.isEmpty ? "Based on your 30-day baseline." : parts.joined(separator: ", ").capitalisedFirst + "."
    }
}

private extension ISO8601DateFormatter {
    static let dayOnly: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withFullDate]
        return f
    }()
}

private extension String {
    var capitalisedFirst: String {
        prefix(1).uppercased() + dropFirst()
    }
}
