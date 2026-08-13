"""Supported well-log formats."""

from enum import StrEnum


class WellLogFormat(StrEnum):
    """Formats recognized by Wellio."""

    LAS = "las"
    DLIS = "dlis"
    WITSML = "witsml"
    UNKNOWN = "unknown"
