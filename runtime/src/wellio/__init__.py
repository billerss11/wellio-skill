"""Public API for Wellio."""

from wellio.core import (
    CurveSummary,
    DataSelection,
    FormatDetector,
    SelectedCurve,
    detect_format,
    open_file,
    open_log,
    parse_row_slice,
    select_data,
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
    SampleAxis,
    WellLogFile,
    WellLogFormat,
)

__all__ = [
    "Curve",
    "CurveSummary",
    "DataSelection",
    "Dataset",
    "FormatDetector",
    "IndexKind",
    "LogicalFile",
    "MetadataItem",
    "MetadataSection",
    "SampleAxis",
    "SelectedCurve",
    "WellioError",
    "WellLogFile",
    "WellLogFormat",
    "detect_format",
    "open_file",
    "open_log",
    "parse_row_slice",
    "select_data",
    "select_dataframe",
    "summarize_curve",
]

__version__ = "0.2.0"
