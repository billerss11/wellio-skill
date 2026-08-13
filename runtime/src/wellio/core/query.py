"""Reusable curve selection, slicing, and summary services."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING

from wellio.models import Curve, Dataset, IndexKind

if TYPE_CHECKING:
    import pandas as pd


@dataclass(slots=True)
class CurveSummary:
    """Human-readable statistics for one selected curve interval."""

    curve: Curve
    index_start: object
    index_stop: object
    total_points: int
    valid_points: int
    missing_points: int
    completeness: float
    first_value: object
    last_value: object
    is_numeric: bool
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    median: float | None = None
    standard_deviation: float | None = None
    unique_values: int | None = None


def parse_row_slice(value: str) -> slice:
    """Parse a nonnegative, half-open ``START:STOP`` row slice."""

    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("Row slice must use START:STOP syntax")

    bounds: list[int | None] = []
    for part in parts:
        if not part:
            bounds.append(None)
            continue
        try:
            bound = int(part)
        except ValueError as exc:
            raise ValueError("Row slice bounds must be integers") from exc
        if bound < 0:
            raise ValueError("Row slice bounds cannot be negative")
        bounds.append(bound)

    start, stop = bounds
    if start is not None and stop is not None and start > stop:
        raise ValueError("Row slice start cannot be greater than stop")
    return slice(start, stop)


def select_dataframe(
    dataset: Dataset,
    curves: Sequence[str] | None = None,
    *,
    start: str | None = None,
    stop: str | None = None,
    rows: slice | None = None,
) -> "pd.DataFrame":
    """Select curves and an optional row or primary-index interval."""

    if rows is not None and (start is not None or stop is not None):
        raise ValueError("Row slicing cannot be combined with index bounds")

    frame = dataset.to_dataframe(curves)
    if rows is not None:
        selected = frame.iloc[rows]
    elif start is not None or stop is not None:
        selected = _select_index_range(dataset, frame, start=start, stop=stop)
    else:
        selected = frame

    if len(selected.index) == 0:
        raise ValueError("The selected range contains no data rows")
    return selected


def summarize_curve(
    dataset: Dataset,
    curve_name: str,
    *,
    start: str | None = None,
    stop: str | None = None,
    rows: slice | None = None,
) -> tuple[CurveSummary, "pd.DataFrame"]:
    """Return a curve summary and its selected one-curve DataFrame."""

    import pandas as pd

    curve = dataset.get_curve(curve_name)
    frame = select_dataframe(
        dataset,
        [curve.mnemonic],
        start=start,
        stop=stop,
        rows=rows,
    )
    if curve is dataset.index:
        series = pd.Series(
            frame.index.to_numpy(), index=frame.index, name=curve.mnemonic
        )
    else:
        series = frame[curve.mnemonic]

    valid = series.dropna()
    total_points = len(series)
    valid_points = len(valid)
    summary = CurveSummary(
        curve=curve,
        index_start=_python_scalar(frame.index[0]),
        index_stop=_python_scalar(frame.index[-1]),
        total_points=total_points,
        valid_points=valid_points,
        missing_points=total_points - valid_points,
        completeness=(valid_points / total_points) * 100,
        first_value=_python_scalar(series.iloc[0]),
        last_value=_python_scalar(series.iloc[-1]),
        is_numeric=pd.api.types.is_numeric_dtype(series.dtype),
    )

    if summary.is_numeric:
        summary.minimum = _optional_float(valid.min())
        summary.maximum = _optional_float(valid.max())
        summary.mean = _optional_float(valid.mean())
        summary.median = _optional_float(valid.median())
        summary.standard_deviation = _optional_float(valid.std())
    else:
        summary.unique_values = int(valid.nunique())
    return summary, frame


def _select_index_range(
    dataset: Dataset,
    frame: "pd.DataFrame",
    *,
    start: str | None,
    stop: str | None,
) -> "pd.DataFrame":
    """Apply inclusive numeric or timestamp bounds to a DataFrame index."""

    import pandas as pd

    index = frame.index
    if pd.api.types.is_numeric_dtype(index.dtype):
        lower = _numeric_bound(start)
        upper = _numeric_bound(stop)
        comparable_index = index
    elif dataset.index_kind is IndexKind.TIME:
        comparable_index = pd.to_datetime(index, format="mixed", errors="coerce")
        if comparable_index.isna().any():
            raise ValueError("The time index contains values that cannot be parsed")
        lower = _time_bound(start)
        upper = _time_bound(stop)
    else:
        raise ValueError(
            "Index-range slicing requires a numeric or timestamp index; use --rows"
        )

    if lower is not None and upper is not None and lower > upper:
        raise ValueError("Index start cannot be greater than stop")

    mask = pd.Series(True, index=frame.index)
    if lower is not None:
        mask &= comparable_index >= lower
    if upper is not None:
        mask &= comparable_index <= upper
    return frame.loc[mask.to_numpy()]


def _numeric_bound(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        bound = float(value)
    except ValueError as exc:
        raise ValueError(f"Index bound must be numeric: {value}") from exc
    if not isfinite(bound):
        raise ValueError(f"Index bound must be finite: {value}")
    return bound


def _time_bound(value: str | None) -> "pd.Timestamp | None":
    import pandas as pd

    if value is None:
        return None
    try:
        return pd.to_datetime(value, format="mixed", errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Time bound cannot be parsed: {value}") from exc


def _python_scalar(value: object) -> object:
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return item_method()
        except ValueError:
            pass
    return value


def _optional_float(value: object) -> float | None:
    import pandas as pd

    if pd.isna(value):
        return None
    return float(value)
