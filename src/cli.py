"""
Health Insights CLI

Command-line interface for importing data and generating reports.
"""

import click
from pathlib import Path
from datetime import datetime, timedelta
import yaml
import sys

from . import parser
from . import metrics
from . import reports


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


def load_config() -> dict:
    """Load configuration from settings.yaml."""
    config_path = get_project_root() / "config" / "settings.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


def expand_path(path: str) -> Path:
    """Expand ~ in paths."""
    return Path(path).expanduser()


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Health Insights - Personal health analytics from Apple HealthKit data."""
    pass


@cli.command()
@click.argument('export_file', type=click.Path(exists=True))
@click.option('--output-dir', '-o', default=None,
              help='Output directory for processed data')
def import_data(export_file: str, output_dir: str):
    """
    Import and process a HealthKit export file.

    EXPORT_FILE: Path to the export.xml file from Apple Health export.
    """
    config = load_config()
    export_path = Path(export_file)

    # Determine output directory
    if output_dir:
        data_dir = expand_path(output_dir)
    else:
        data_dir = expand_path(config.get('paths', {}).get('data',
                               str(get_project_root() / 'data')))

    click.echo(f"Importing HealthKit export from: {export_path}")
    click.echo(f"Output directory: {data_dir}")

    # Parse the export
    try:
        raw_data = parser.parse_export(export_path)
    except Exception as e:
        click.echo(f"Error parsing export: {e}", err=True)
        sys.exit(1)

    # Backfill missing workout HR from raw HR samples in the export
    click.echo("\nBackfilling workout HR from raw samples...")
    raw_data['workouts'] = parser.backfill_workout_hr(
        raw_data['workouts'], raw_data['records']
    )

    # Process records into daily metrics
    click.echo("\nProcessing daily metrics...")
    daily_metrics = parser.extract_daily_metrics(raw_data['records'])

    # Process sleep data
    click.echo("Processing sleep data...")
    sleep_df = parser.process_sleep_data(raw_data['sleep'])

    # Calculate workout metrics
    click.echo("Calculating workout metrics...")
    workouts_df = metrics.calculate_workout_metrics(
        raw_data['workouts'], daily_metrics, config
    )

    # Save processed data
    click.echo("\nSaving processed data...")
    processed_data = {
        'daily_metrics': daily_metrics,
        'sleep': sleep_df,
        'workouts': workouts_df,
    }
    parser.save_processed_data(processed_data, data_dir)

    click.echo(f"\nImport complete!")
    click.echo(f"  Daily metrics: {len(daily_metrics)} days")
    click.echo(f"  Sleep records: {len(sleep_df)} nights")
    click.echo(f"  Workouts: {len(workouts_df)} sessions")


@cli.command()
@click.option('--date', '-d', default=None,
              help='Week ending date (YYYY-MM-DD). Default: current week.')
@click.option('--output', '-o', default=None,
              help='Output path for PDF report')
@click.option('--data-dir', default=None,
              help='Override the data directory (e.g. sample_data)')
def weekly(date: str, output: str, data_dir: str):
    """
    Generate a weekly health summary report.
    """
    config = load_config()
    if data_dir:
        data_dir = expand_path(data_dir)
    else:
        data_dir = expand_path(config.get('paths', {}).get('data',
                               str(get_project_root() / 'data')))
    reports_dir = expand_path(config.get('paths', {}).get('reports',
                              str(get_project_root() / 'reports')))

    # Determine week dates
    if date:
        week_end = datetime.strptime(date, '%Y-%m-%d')
    else:
        # Default to the most recent completed Mon-Sun week.
        # If today is Sunday, the week ends today; otherwise step back to last Sunday.
        today = datetime.now()
        days_back_to_sunday = (today.weekday() + 1) % 7
        week_end = today - timedelta(days=days_back_to_sunday)

    week_start = week_end - timedelta(days=6)
    week_start = datetime(week_start.year, week_start.month, week_start.day)
    week_end = datetime(week_end.year, week_end.month, week_end.day) + timedelta(days=1)

    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_start

    click.echo(f"Generating weekly report for: {week_start.strftime('%d %b')} - {(week_end - timedelta(days=1)).strftime('%d %b %Y')}")

    # Load processed data
    click.echo("Loading data...")
    try:
        data = parser.load_processed_data(data_dir)
    except Exception as e:
        click.echo(f"Error loading data: {e}", err=True)
        click.echo("Have you run 'health-report import' first?", err=True)
        sys.exit(1)

    daily_metrics = data.get('daily_metrics', parser.pd.DataFrame())
    sleep_df = data.get('sleep', parser.pd.DataFrame())
    workouts_df = data.get('workouts', parser.pd.DataFrame())

    if daily_metrics.empty:
        click.echo("No data found. Please import a HealthKit export first.", err=True)
        sys.exit(1)

    # Calculate derived metrics
    click.echo("Calculating metrics...")

    # Daily training load
    daily_load = metrics.calculate_daily_training_load(workouts_df)
    if not daily_load.empty:
        daily_load = metrics.calculate_acute_chronic_ratio(daily_load)

    # Sleep debt
    if not sleep_df.empty:
        sleep_df = metrics.calculate_sleep_debt(sleep_df)

    # Readiness scores
    readiness = metrics.calculate_readiness_score(daily_metrics, config)

    # Personal baselines
    baselines = metrics.calculate_personal_baselines(daily_metrics, config)

    # Detect anomalies (filter to recent)
    anomalies = metrics.detect_anomalies(daily_metrics, sleep_df, baselines, config)
    week_anomalies = [a for a in anomalies
                      if a['date'] >= week_start and a['date'] < week_end]

    # Calculate summaries
    week_summary = metrics.calculate_week_summary(
        daily_metrics, daily_load, sleep_df, workouts_df, readiness, week_start
    )
    prev_week_summary = metrics.calculate_week_summary(
        daily_metrics, daily_load, sleep_df, workouts_df, readiness, prev_week_start
    )

    # Determine output path
    if output:
        output_path = Path(output)
    else:
        filename = f"weekly_{week_start.strftime('%Y-%m-%d')}.pdf"
        output_path = reports_dir / "weekly" / filename

    # Generate report
    click.echo("Generating report...")
    reports.generate_weekly_report(
        week_summary=week_summary,
        prev_week_summary=prev_week_summary,
        daily_metrics=daily_metrics,
        daily_load=daily_load,
        sleep_df=sleep_df,
        workouts_df=workouts_df,
        readiness=readiness,
        anomalies=week_anomalies,
        baselines=baselines,
        config=config,
        output_path=output_path
    )

    click.echo(f"\nReport saved to: {output_path}")


@cli.command()
@click.option('--date', '-d', default=None,
              help='Month (YYYY-MM). Default: current month.')
@click.option('--output', '-o', default=None,
              help='Output path for PDF report')
@click.option('--data-dir', default=None,
              help='Override the data directory (e.g. sample_data)')
def monthly(date: str, output: str, data_dir: str):
    """
    Generate a monthly health deep-dive report.
    """
    config = load_config()
    if data_dir:
        data_dir = expand_path(data_dir)
    else:
        data_dir = expand_path(config.get('paths', {}).get('data',
                               str(get_project_root() / 'data')))
    reports_dir = expand_path(config.get('paths', {}).get('reports',
                              str(get_project_root() / 'reports')))

    # Determine month dates
    if date:
        month_start = datetime.strptime(date + '-01', '%Y-%m-%d')
    else:
        today = datetime.now()
        month_start = datetime(today.year, today.month, 1)

    # Previous month
    if month_start.month == 1:
        prev_month_start = datetime(month_start.year - 1, 12, 1)
    else:
        prev_month_start = datetime(month_start.year, month_start.month - 1, 1)

    click.echo(f"Generating monthly report for: {month_start.strftime('%B %Y')}")

    # Load processed data
    click.echo("Loading data...")
    try:
        data = parser.load_processed_data(data_dir)
    except Exception as e:
        click.echo(f"Error loading data: {e}", err=True)
        click.echo("Have you run 'health-report import' first?", err=True)
        sys.exit(1)

    daily_metrics = data.get('daily_metrics', parser.pd.DataFrame())
    sleep_df = data.get('sleep', parser.pd.DataFrame())
    workouts_df = data.get('workouts', parser.pd.DataFrame())

    if daily_metrics.empty:
        click.echo("No data found. Please import a HealthKit export first.", err=True)
        sys.exit(1)

    # Calculate derived metrics
    click.echo("Calculating metrics...")

    # Daily training load
    daily_load = metrics.calculate_daily_training_load(workouts_df)
    if not daily_load.empty:
        daily_load = metrics.calculate_acute_chronic_ratio(daily_load)

    # Sleep debt
    if not sleep_df.empty:
        sleep_df = metrics.calculate_sleep_debt(sleep_df)

    # Readiness scores
    readiness = metrics.calculate_readiness_score(daily_metrics, config)

    # Personal baselines
    baselines = metrics.calculate_personal_baselines(daily_metrics, config)

    # Detect anomalies
    anomalies = metrics.detect_anomalies(daily_metrics, sleep_df, baselines, config)

    # Calculate summaries
    month_summary = metrics.calculate_month_summary(
        daily_metrics, daily_load, sleep_df, workouts_df, readiness, month_start
    )
    prev_month_summary = metrics.calculate_month_summary(
        daily_metrics, daily_load, sleep_df, workouts_df, readiness, prev_month_start
    )

    # Determine output path
    if output:
        output_path = Path(output)
    else:
        filename = f"monthly_{month_start.strftime('%Y-%m')}.pdf"
        output_path = reports_dir / "monthly" / filename

    # Generate report
    click.echo("Generating report...")
    reports.generate_monthly_report(
        month_summary=month_summary,
        prev_month_summary=prev_month_summary,
        daily_metrics=daily_metrics,
        daily_load=daily_load,
        sleep_df=sleep_df,
        workouts_df=workouts_df,
        readiness=readiness,
        anomalies=anomalies,
        baselines=baselines,
        config=config,
        output_path=output_path
    )

    click.echo(f"\nReport saved to: {output_path}")


@cli.command()
def status():
    """
    Show status of imported data and recent reports.
    """
    config = load_config()
    data_dir = expand_path(config.get('paths', {}).get('data',
                           str(get_project_root() / 'data')))
    reports_dir = expand_path(config.get('paths', {}).get('reports',
                              str(get_project_root() / 'reports')))

    click.echo("Health Insights Status\n")

    # Check for processed data
    click.echo("Data:")
    if data_dir.exists():
        csv_files = list(data_dir.glob('*.csv'))
        if csv_files:
            for f in csv_files:
                # Get file stats
                stat = f.stat()
                mod_time = datetime.fromtimestamp(stat.st_mtime)
                click.echo(f"  {f.name}: {stat.st_size / 1024:.1f} KB "
                          f"(updated {mod_time.strftime('%d %b %Y %H:%M')})")
        else:
            click.echo("  No processed data found. Run 'health-report import' first.")
    else:
        click.echo(f"  Data directory not found: {data_dir}")

    # Check for recent reports
    click.echo("\nRecent Reports:")
    if reports_dir.exists():
        pdf_files = sorted(reports_dir.rglob('*.pdf'), key=lambda x: x.stat().st_mtime, reverse=True)
        if pdf_files:
            for f in pdf_files[:5]:  # Show last 5
                mod_time = datetime.fromtimestamp(f.stat().st_mtime)
                click.echo(f"  {f.name}: {mod_time.strftime('%d %b %Y %H:%M')}")
        else:
            click.echo("  No reports found.")
    else:
        click.echo(f"  Reports directory not found: {reports_dir}")


@cli.command()
def schedule_info():
    """
    Show information about scheduling automatic reports.
    """
    click.echo("""
Scheduling Automatic Reports
============================

To automatically generate reports on a schedule, add these to your crontab:

1. Open crontab for editing:
   crontab -e

2. Add these lines (adjust paths as needed):

   # Weekly report - every Monday at 7:00 AM
   0 7 * * 1 cd /path/to/health-insights && ~/.local/bin/health-report weekly

   # Monthly report - 1st of each month at 7:00 AM
   0 7 1 * * cd /path/to/health-insights && ~/.local/bin/health-report monthly

Alternative: Using launchd (macOS native)
-----------------------------------------

Create ~/Library/LaunchAgents/com.health-insights.weekly.plist:

<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.health-insights.weekly</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/health-report</string>
        <string>weekly</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>1</integer>
        <key>Hour</key>
        <integer>7</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>WorkingDirectory</key>
    <string>/path/to/health-insights</string>
</dict>
</plist>

Then load it:
   launchctl load ~/Library/LaunchAgents/com.health-insights.weekly.plist
""")


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == '__main__':
    main()
