//
//  ContentView.swift
//  HealthInsights
//
//  Today's readiness front and centre, 30-day trend below.
//

import SwiftUI
import Charts

struct ContentView: View {

    @StateObject private var coordinator = ReadinessCoordinator.shared
    @StateObject private var health = HealthKitManager.shared

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    if let today = coordinator.today {
                        ReadinessRing(result: today)
                        componentRow(for: today)
                    } else if let error = coordinator.lastError {
                        ContentUnavailableView(
                            "No readiness yet",
                            systemImage: "heart.text.square",
                            description: Text(error)
                        )
                    } else {
                        ProgressView("Reading Health data…")
                            .padding(.top, 80)
                    }

                    if coordinator.series.count > 1 {
                        trendChart
                    }
                }
                .padding()
            }
            .navigationTitle("Readiness")
            .toolbar {
                Button {
                    Task { await coordinator.refresh() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
            }
        }
        .task {
            try? await health.requestAuthorisation()
            await NotificationManager.shared.requestAuthorisation()
            await coordinator.refresh()
            health.enableBackgroundDelivery()
        }
    }

    private func componentRow(for result: ReadinessResult) -> some View {
        HStack(spacing: 12) {
            if let z = result.hrvZScore {
                ComponentCard(title: "HRV", zScore: z, goodWhenHigh: true)
            }
            if let z = result.rhrZScore {
                ComponentCard(title: "Resting HR", zScore: -z, goodWhenHigh: true)
            }
        }
    }

    private var trendChart: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("30-day trend")
                .font(.headline)
            Chart(coordinator.series.suffix(30), id: \.date) { point in
                LineMark(
                    x: .value("Date", point.date),
                    y: .value("Readiness", point.score)
                )
                .foregroundStyle(.teal)
                .interpolationMethod(.monotone)

                AreaMark(
                    x: .value("Date", point.date),
                    y: .value("Readiness", point.score)
                )
                .foregroundStyle(.teal.opacity(0.12))
                .interpolationMethod(.monotone)
            }
            .chartYScale(domain: 0...100)
            .frame(height: 160)
        }
        .padding()
        .background(.quaternary.opacity(0.3), in: RoundedRectangle(cornerRadius: 16))
    }
}

// MARK: - Components

struct ReadinessRing: View {
    let result: ReadinessResult

    var body: some View {
        VStack(spacing: 12) {
            ZStack {
                Circle()
                    .stroke(.quaternary, lineWidth: 14)
                Circle()
                    .trim(from: 0, to: result.score / 100)
                    .stroke(result.status.colour, style: StrokeStyle(lineWidth: 14, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                VStack {
                    Text("\(Int(result.score.rounded()))")
                        .font(.system(size: 56, weight: .bold, design: .rounded))
                    Text(result.status.headline)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(width: 220, height: 220)

            Text(result.date, style: .date)
                .font(.footnote)
                .foregroundStyle(.tertiary)
        }
    }
}

struct ComponentCard: View {
    let title: String
    let zScore: Double      // normalised so positive = good
    let goodWhenHigh: Bool

    var body: some View {
        VStack(spacing: 4) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(zScore >= 0 ? "▲" : "▼")
                .foregroundStyle(zScore >= 0 ? .green : .orange)
            Text(String(format: "%+.1f SD", zScore))
                .font(.callout.monospacedDigit())
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(.quaternary.opacity(0.3), in: RoundedRectangle(cornerRadius: 12))
    }
}

extension ReadinessStatus {
    var colour: Color {
        switch self {
        case .green: return .green
        case .amber: return .orange
        case .red: return .red
        }
    }
}

#Preview {
    ContentView()
}
