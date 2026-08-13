"""Core services shared by all Wellio interfaces."""

from wellio.core.detection import FormatDetector, detect_format
from wellio.core.loading import open_file, open_log
from wellio.core.query import (
    CurveSummary,
    parse_row_slice,
    select_dataframe,
    summarize_curve,
)

__all__ = [
    "CurveSummary",
    "FormatDetector",
    "detect_format",
    "open_file",
    "open_log",
    "parse_row_slice",
    "select_dataframe",
    "summarize_curve",
]
