"""
Health Insights Setup

Install with: pip install -e .
"""

from setuptools import setup, find_packages

setup(
    name="health-insights",
    version="0.1.0",
    description="Personal health analytics from Apple HealthKit data",
    author="Mark Lilburn",
    packages=find_packages(),
    package_dir={"": "."},
    py_modules=["src.parser", "src.metrics", "src.reports", "src.cli"],
    install_requires=[
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "matplotlib>=3.7.0",
        "seaborn>=0.12.0",
        "reportlab>=4.0.0",
        "click>=8.1.0",
        "pyyaml>=6.0.0",
        "python-dateutil>=2.8.0",
    ],
    entry_points={
        "console_scripts": [
            "health-report=src.cli:main",
        ],
    },
    python_requires=">=3.9",
)
