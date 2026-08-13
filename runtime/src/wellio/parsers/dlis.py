"""DLIS parser adapter built on dlisio."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from dlisio import dlis

from wellio.exceptions import WellioError
from wellio.models import (
    Curve,
    Dataset,
    IndexKind,
    LogicalFile,
    WellLogFile,
    WellLogFormat,
)


class _DlisResource:
    def __init__(self, physical: Any, source: Path) -> None:
        self.physical = physical
        self.source = source
        self.closed = False

    def ensure_open(self) -> None:
        if self.closed:
            raise WellioError(f"Well-log file is closed: {self.source}")

    def close(self) -> None:
        if not self.closed:
            self.physical.close()
            self.closed = True


class _DlisFrameData:
    def __init__(self, resource: _DlisResource, frame: Any) -> None:
        self.resource = resource
        self.frame = frame
        self._array: Any | None = None

    def field(self, name: str) -> Any:
        self.resource.ensure_open()
        if self._array is None:
            self._array = self.frame.curves(strict=False)
        return self._array[name]


class _DlisCurveValues(Sequence[object]):
    def __init__(self, frame_data: _DlisFrameData, field_name: str) -> None:
        self._frame_data = frame_data
        self._field_name = field_name

    def _values(self) -> Any:
        return self._frame_data.field(self._field_name)

    def __len__(self) -> int:
        return len(self._values())

    def __getitem__(self, index: int | slice) -> object:
        return self._values()[index]

    def __iter__(self) -> Iterator[object]:
        return iter(self._values())

    def __array__(self, dtype: Any = None, copy: bool | None = None) -> Any:
        import numpy as np

        values = self._values()
        if copy is None:
            return np.asarray(values, dtype=dtype)
        return np.array(values, dtype=dtype, copy=copy)


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _index_kind(index_type: object) -> IndexKind | None:
    normalized = str(index_type or "").upper()
    if "DEPTH" in normalized:
        return IndexKind.DEPTH
    if "TIME" in normalized:
        return IndexKind.TIME
    return IndexKind.OTHER if normalized else None


def _frame_dataset(
    source: Path,
    logical_name: str,
    native_frame: Any,
    resource: _DlisResource,
) -> Dataset:
    dtype_names = [
        name
        for name in (native_frame.dtype(strict=False).names or ())
        if name.upper() != "FRAMENO"
    ]
    channels = list(native_frame.channels)
    if len(dtype_names) != len(channels):
        raise WellioError(
            f"DLIS frame {native_frame.name!r} exposes {len(channels)} channels "
            f"but {len(dtype_names)} curve fields"
        )

    frame_data = _DlisFrameData(resource, native_frame)
    curves = [
        Curve(
            mnemonic=field_name,
            original_mnemonic=str(channel.name),
            values=_DlisCurveValues(frame_data, field_name),
            unit=_clean_text(getattr(channel, "units", None)),
            description=_clean_text(getattr(channel, "long_name", None)),
            sample_shape=tuple(int(size) for size in channel.dimension),
            origin=int(channel.origin),
            copy_number=int(channel.copynumber),
            native=channel,
        )
        for field_name, channel in zip(dtype_names, channels, strict=True)
    ]
    index_name = str(getattr(native_frame, "index", "") or "")
    index_curve = next(
        (
            curve
            for curve in curves
            if (curve.original_mnemonic or curve.mnemonic) == index_name
        ),
        None,
    )
    index_type = getattr(native_frame, "index_type", None)

    return Dataset(
        source=source,
        format=WellLogFormat.DLIS,
        name=str(native_frame.name),
        curves=curves,
        index=index_curve,
        index_kind=_index_kind(index_type),
        metadata={
            "logical_file": logical_name,
            "index_type": _clean_text(index_type),
            "direction": _clean_text(getattr(native_frame, "direction", None)),
            "spacing": getattr(native_frame, "spacing", None),
        },
        native=native_frame,
    )


def _logical_name(native_logical_file: Any, index: int) -> str:
    fileheader = getattr(native_logical_file, "fileheader", None)
    for value in (
        getattr(fileheader, "id", None),
        getattr(fileheader, "name", None),
    ):
        cleaned = _clean_text(value)
        if cleaned is not None:
            return cleaned
    return f"logical-file-{index}"


def read_dlis(path: str | Path) -> WellLogFile:
    """Read a DLIS physical file without loading its frame curve arrays."""

    source = Path(path)
    try:
        physical = dlis.load(source)
    except Exception as exc:
        raise WellioError(f"Could not read DLIS file {source}: {exc}") from exc

    resource = _DlisResource(physical, source)
    try:
        logical_files: list[LogicalFile] = []
        for logical_index, native_logical in enumerate(physical):
            logical_name = _logical_name(native_logical, logical_index)
            frames = [
                _frame_dataset(source, logical_name, frame, resource)
                for frame in native_logical.frames
            ]
            logical_files.append(
                LogicalFile(
                    name=logical_name,
                    frames=frames,
                    native=native_logical,
                )
            )
        return WellLogFile(
            source=source,
            format=WellLogFormat.DLIS,
            logical_files=logical_files,
            native=physical,
            _closer=resource.close,
        )
    except Exception as exc:
        resource.close()
        if isinstance(exc, WellioError):
            raise
        raise WellioError(f"Could not read DLIS file {source}: {exc}") from exc
