"""Format-independent well-log models."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from math import prod
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING

from wellio.exceptions import WellioError
from wellio.models.formats import WellLogFormat

if TYPE_CHECKING:
    import pandas as pd


class IndexKind(StrEnum):
    """Meaning of a dataset's primary index curve."""

    DEPTH = "depth"
    TIME = "time"
    OTHER = "other"


@dataclass(slots=True)
class SampleAxis:
    """One native per-sample dimension without inferred semantics."""

    name: str | None = None
    identifier: str | None = None
    unit: str | None = None
    property_type: str | None = None
    coordinates: tuple[object, ...] = ()
    spacing: object | None = None
    native: object | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class Curve:
    """A named sequence of well-log values."""

    mnemonic: str
    values: Sequence[object] = field(default_factory=list)
    unit: str | None = None
    description: str | None = None
    original_mnemonic: str | None = None
    sample_shape: tuple[int, ...] = ()
    sample_axes: tuple[SampleAxis, ...] = ()
    element_limit: tuple[int, ...] = ()
    origin: int | None = None
    copy_number: int | None = None
    native: object | None = None
    data_type: str | None = None

    @property
    def is_scalar(self) -> bool:
        """Return whether each curve sample contains one value."""

        return not self.sample_shape or prod(self.sample_shape) == 1


@dataclass(slots=True)
class MetadataItem:
    """One ordered item from a native metadata section."""

    mnemonic: str
    value: object = None
    unit: str | None = None
    description: str | None = None
    original_mnemonic: str | None = None


@dataclass(slots=True)
class MetadataSection:
    """An ordered metadata section containing items or native text."""

    name: str
    items: list[MetadataItem] = field(default_factory=list)
    text: str | None = None


@dataclass(slots=True)
class Dataset:
    """Normalized well-log data with access to its native representation."""

    source: Path
    format: WellLogFormat
    name: str | None = None
    curves: list[Curve] = field(default_factory=list)
    index: Curve | None = None
    index_kind: IndexKind | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    sections: list[MetadataSection] = field(default_factory=list)
    native: object | None = None

    @property
    def curve_count(self) -> int:
        """Return the number of curves, including the index curve."""

        return len(self.curves)

    @property
    def row_count(self) -> int:
        """Return the number of indexed data rows."""

        if self.index is not None:
            return len(self.index.values)
        if self.curves:
            return len(self.curves[0].values)
        return 0

    def get_curve(self, name: str) -> Curve:
        """Resolve a curve by unique or unambiguous original mnemonic."""

        normalized_name = name.casefold()
        exact_matches = [
            curve
            for curve in self.curves
            if curve.mnemonic.casefold() == normalized_name
        ]
        if len(exact_matches) == 1:
            return exact_matches[0]

        original_matches = [
            curve
            for curve in self.curves
            if (curve.original_mnemonic or curve.mnemonic).casefold() == normalized_name
        ]
        if len(original_matches) == 1:
            return original_matches[0]
        if len(original_matches) > 1:
            choices = ", ".join(curve.mnemonic for curve in original_matches)
            raise ValueError(
                f"Curve name {name!r} is ambiguous; choose one of: {choices}"
            )
        raise ValueError(f"Curve not found: {name}")

    def to_dataframe(self, curves: Sequence[str] | None = None) -> "pd.DataFrame":
        """Return selected curves as a lazily created Pandas DataFrame."""

        import pandas as pd

        selected = (
            [
                curve
                for curve in self.curves
                if curve.is_scalar and curve is not self.index
            ]
            if curves is None
            else [self.get_curve(name) for name in curves]
        )
        unique_curves: list[Curve] = []
        seen: set[str] = set()
        for curve in selected:
            key = curve.mnemonic.casefold()
            if key not in seen:
                unique_curves.append(curve)
                seen.add(key)

        tabular_curves = list(unique_curves)
        if self.index is not None and self.index not in tabular_curves:
            tabular_curves.append(self.index)
        multidimensional = [curve for curve in tabular_curves if not curve.is_scalar]
        if multidimensional:
            details = ", ".join(
                f"{curve.mnemonic} shape={curve.sample_shape}"
                for curve in multidimensional
            )
            raise ValueError(
                f"Multidimensional curves cannot be exported as tabular data: {details}"
            )

        expected_rows = self.row_count
        for curve in unique_curves:
            if len(curve.values) != expected_rows:
                raise ValueError(
                    f"Curve {curve.mnemonic!r} has {len(curve.values)} rows; "
                    f"expected {expected_rows}"
                )

        data = {
            curve.mnemonic: curve.values
            for curve in unique_curves
            if curve is not self.index
        }
        frame = pd.DataFrame(data)
        if self.index is not None:
            frame.index = pd.Index(self.index.values, name=self.index.mnemonic)
        else:
            frame.index = pd.RangeIndex(expected_rows, name="ROW")
        return frame


@dataclass(slots=True)
class LogicalFile:
    """One logical file containing ordered frame datasets."""

    name: str
    frames: list[Dataset] = field(default_factory=list)
    native: object | None = None


@dataclass(slots=True)
class WellLogFile:
    """A physical well-log file that may own an open native resource."""

    source: Path
    format: WellLogFormat
    logical_files: list[LogicalFile] = field(default_factory=list)
    native: object | None = None
    _closer: Callable[[], None] | None = field(default=None, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    @property
    def closed(self) -> bool:
        """Return whether this file's native resource has been closed."""

        return self._closed

    def close(self) -> None:
        """Close the native file resource once."""

        if self._closed:
            return
        if self._closer is not None:
            self._closer()
        self._closed = True

    def __enter__(self) -> "WellLogFile":
        if self._closed:
            raise WellioError(f"Well-log file is closed: {self.source}")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def get_dataset(
        self,
        logical_file: int | None = None,
        frame: int | None = None,
    ) -> Dataset:
        """Select one frame dataset by zero-based indexes."""

        if self._closed:
            raise WellioError(f"Well-log file is closed: {self.source}")
        logical_index = _resolve_selection(
            logical_file,
            len(self.logical_files),
            "logical file",
        )
        logical = self.logical_files[logical_index]
        frame_index = _resolve_selection(frame, len(logical.frames), "frame")
        return logical.frames[frame_index]


def _resolve_selection(value: int | None, count: int, label: str) -> int:
    if count == 0:
        raise ValueError(f"No {label}s are available")
    choices = f"0 to {count - 1}"
    if value is None:
        if count == 1:
            return 0
        raise ValueError(
            f"{count} {label}s are available; choose one by index ({choices})"
        )
    if value < 0 or value >= count:
        raise ValueError(
            f"{label.title()} index {value} is out of range; choose {choices}"
        )
    return value
