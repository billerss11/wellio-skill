"""Public API for Wellio."""

from wellio.core import (
    CurveSummary,
    FormatDetector,
    detect_format,
    open_file,
    open_log,
    parse_row_slice,
    select_dataframe,
    summarize_curve,
)
from wellio.exceptions import WellioError
from wellio.models import (
    Curve,
    Dataset,
    IndexKind,
    LogicalFile,
    MetadataItem,
    MetadataSection,
    WellLogFile,
    WellLogFormat,
)

__all__ = [
    "Curve",
    "CurveSummary",
    "Dataset",
    "FormatDetector",
    "IndexKind",
    "LogicalFile",
    "MetadataItem",
    "MetadataSection",
    "WellioError",
    "WellLogFile",
    "WellLogFormat",
    "detect_format",
    "open_file",
    "open_log",
    "parse_row_slice",
    "select_dataframe",
    "summarize_curve",
]

__version__ = "0.1.0"
