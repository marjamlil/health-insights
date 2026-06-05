"""
Report generation entry points.

The weekly and monthly reports live in their own modules (report_weekly,
report_monthly) and share the report_style design system. This module just
re-exports the two generators so callers (cli.py) have a stable import.
"""

from .report_weekly import generate_weekly_report
from .report_monthly import generate_monthly_report

__all__ = ["generate_weekly_report", "generate_monthly_report"]
