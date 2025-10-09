"""Domain-level utilities for the EDA application."""

from .analysis import (
    coerce_numeric,
    dataframe_signature,
    eda_overview,
    compute_advanced_analysis,
    detect_clusters,
    detect_outliers,
    detect_temporal_patterns,
    identify_value_frequencies,
    summarize_relationships,
    OUTLIER_SUGGESTIONS,
    readable_dtype,
)
from .charts import ChartSpec, extract_chart_spec_from_text, normalize_chart_spec

__all__ = [
    "coerce_numeric",
    "dataframe_signature",
    "eda_overview",
    "compute_advanced_analysis",
    "detect_clusters",
    "detect_outliers",
    "detect_temporal_patterns",
    "identify_value_frequencies",
    "summarize_relationships",
    "OUTLIER_SUGGESTIONS",
    "readable_dtype",
    "ChartSpec",
    "extract_chart_spec_from_text",
    "normalize_chart_spec",
]
