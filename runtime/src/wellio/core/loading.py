"""Format-independent well-log loading."""

from pathlib import Path

from wellio.core.detection import detect_format
from wellio.models import Dataset, LogicalFile, WellLogFile, WellLogFormat
from wellio.parsers import read_dlis, read_las, read_witsml


def _validated_source(path: str | Path) -> Path:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Well-log file does not exist: {source}")
    if not source.is_file():
        raise IsADirectoryError(f"Well-log path is not a file: {source}")
    return source


def open_file(path: str | Path) -> WellLogFile:
    """Open a physical well-log file as a context-managed hierarchy."""

    source = _validated_source(path)
    file_format = detect_format(source)
    if file_format is WellLogFormat.LAS:
        dataset = read_las(source)
        return WellLogFile(
            source=source,
            format=WellLogFormat.LAS,
            logical_files=[
                LogicalFile(
                    name=source.stem,
                    frames=[dataset],
                    native=dataset.native,
                )
            ],
            native=dataset.native,
        )
    if file_format is WellLogFormat.DLIS:
        return read_dlis(source)
    if file_format is WellLogFormat.WITSML:
        return read_witsml(source)
    if file_format is WellLogFormat.UNKNOWN:
        raise ValueError(f"Unsupported well-log format: {source.suffix or '(none)'}")
    raise ValueError(
        f"Reading {file_format.value.upper()} files is not implemented yet"
    )


def open_log(path: str | Path) -> Dataset:
    """Open a single-dataset LAS or WITSML file."""

    source = _validated_source(path)
    file_format = detect_format(source)
    if file_format is WellLogFormat.LAS:
        return read_las(source)
    if file_format is WellLogFormat.DLIS:
        raise ValueError(
            "DLIS files require managed resources; use "
            f"`with open_file({str(source)!r}) as well_file:`"
        )
    if file_format is WellLogFormat.WITSML:
        well_file = read_witsml(source)
        if len(well_file.logical_files) != 1:
            raise ValueError(
                f"WITSML file contains {len(well_file.logical_files)} logs; use "
                f"`with open_file({str(source)!r}) as well_file:` and select "
                "one with `get_dataset(logical_file=INDEX)`"
            )
        return well_file.logical_files[0].frames[0]
    if file_format is WellLogFormat.UNKNOWN:
        raise ValueError(f"Unsupported well-log format: {source.suffix or '(none)'}")
    raise ValueError(
        f"Reading {file_format.value.upper()} files is not implemented yet"
    )
