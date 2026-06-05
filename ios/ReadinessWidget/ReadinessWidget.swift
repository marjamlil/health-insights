//
//  ReadinessWidget.swift
//  ReadinessWidget
//
//  Home-screen widget showing today's readiness score and status colour.
//  Reads the latest result from the shared App Group container; the app
//  refreshes it whenever HealthKit delivers new data.
//

import SwiftUI
import WidgetKit

struct ReadinessEntry: TimelineEntry {
    let date: Date
    let score: Double?
    let status: String
}

struct ReadinessProvider: TimelineProvider {

    private let appGroupID = "group.com.marklilburn.healthinsights"

    func placeholder(in context: Context) -> ReadinessEntry {
        ReadinessEntry(date: .now, score: 72, status: "green")
    }

    func getSnapshot(in context: Context, completion: @escaping (ReadinessEntry) -> Void) {
        completion(latest())
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<ReadinessEntry>) -> Void) {
        // The app pushes updates via WidgetCenter when new data lands;
        // schedule a fallback refresh for tomorrow morning regardless.
        let tomorrow = Calendar.current.nextDate(
            after: .now,
            matching: DateComponents(hour: 8),
            matchingPolicy: .nextTime
        ) ?? .now.addingTimeInterval(43_200)
        completion(Timeline(entries: [latest()], policy: .after(tomorrow)))
    }

    private func latest() -> ReadinessEntry {
        let defaults = UserDefaults(suiteName: appGroupID)
        let score = defaults?.object(forKey: "readiness.score") as? Double
        let status = defaults?.string(forKey: "readiness.status") ?? "amber"
        let date = defaults?.object(forKey: "readiness.date") as? Date ?? .now
        return ReadinessEntry(date: date, score: score, status: status)
    }
}

struct ReadinessWidgetView: View {
    let entry: ReadinessEntry

    private var colour: Color {
        switch entry.status {
        case "green": return .green
        case "red": return .red
        default: return .orange
        }
    }

    var body: some View {
        VStack(spacing: 6) {
            Text("READINESS")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            if let score = entry.score {
                Text("\(Int(score.rounded()))")
                    .font(.system(size: 40, weight: .bold, design: .rounded))
                    .foregroundStyle(colour)
                Circle()
                    .fill(colour)
                    .frame(width: 8, height: 8)
            } else {
                Text("—")
                    .font(.system(size: 40, weight: .bold, design: .rounded))
                    .foregroundStyle(.secondary)
                Text("Open the app")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .containerBackground(for: .widget) {
            Color(.systemBackground)
        }
    }
}

struct ReadinessWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "ReadinessWidget", provider: ReadinessProvider()) { entry in
            ReadinessWidgetView(entry: entry)
        }
        .configurationDisplayName("Readiness")
        .description("Today's recovery readiness from your HRV and resting HR.")
        .supportedFamilies([.systemSmall])
    }
}

@main
struct ReadinessWidgetBundle: WidgetBundle {
    var body: some Widget {
        ReadinessWidget()
    }
}
