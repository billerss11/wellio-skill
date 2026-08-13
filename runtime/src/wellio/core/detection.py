"""Well-log format detection."""

from pathlib import Path

from wellio.models import WellLogFormat


class FormatDetector:
    """Detect a supported well-log format from a file path."""

    _FORMATS_BY_SUFFIX = {
        ".las": WellLogFormat.LAS,
        ".dlis": WellLogFormat.DLIS,
        ".witsml": WellLogFormat.WITSML,
        ".xml": WellLogFormat.WITSML,
    }

    def detect(self, path: str | Path) -> WellLogFormat:
        """Return the format associated with *path*, or ``UNKNOWN``."""

        suffix = Path(path).suffix.lower()
        return self._FORMATS_BY_SUFFIX.get(suffix, WellLogFormat.UNKNOWN)


_default_detector = FormatDetector()


def detect_format(path: str | Path) -> WellLogFormat:
    """Detect a well-log format using the default detector."""

    return _default_detector.detect(path)
