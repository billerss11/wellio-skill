"""Consumer-neutral serialization for scalar and N-dimensional curves."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, time
from io import StringIO
from itertools import product
from math import prod
from numbers import Integral, Real
from typing import TYPE_CHECKING

from wellio.core import DataSelection, SelectedCurve
from wellio.models import Curve, SampleAxis

if TYPE_CHECKING:
    import pyarrow as pa

SCHEMA_ID = "wellio.structured.v1"


@dataclass(slots=True)
class _ResolvedAxis:
    dimension_id: str
    source_name: str | None
    identifier: str | None
    size: int
    unit: str | None
    coordinates: tuple[object, ...]
    coordinate_source: str
    declared_coordinates: tuple[object, ...]
    declared_spacing: object | None
    property_type: str | None
    source_metadata: dict[str, object]


def structured_json(selection: DataSelection) -> str:
    """Serialize selected scalar and array curves as structured JSON."""

    return json.dumps(
        structured_payload(selection),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ) + "\n"


def structured_payload(selection: DataSelection) -> dict[str, object]:
    """Build the versioned, dimension-aware structured payload."""

    dataset = selection.dataset
    index = dataset.index
    index_name = index.mnemonic if index is not None else "ROW"
    index_values = [_data_value(value, index_name) for value in selection.index_values]
    dimensions: list[dict[str, object]] = [
        {
            "id": "frame_index",
            "role": "frame_index",
            "source_name": index_name,
            "axis_identifier": None,
            "size": len(selection.row_positions),
            "unit": index.unit if index is not None else None,
            "coordinates": index_values,
            "coordinate_source": "recorded" if index is not None else "position",
            "declared_coordinates": index_values,
            "declared_spacing": dataset.metadata.get("spacing"),
        }
    ]
    curves: list[dict[str, object]] = []

    for selected in selection.curves:
        curve = selected.curve
        sample_shape = _effective_shape(curve)
        axes = _resolve_axes(curve, sample_shape)
        dimensions.extend(_axis_payload(axis) for axis in axes)
        values = [
            _normalized_sample(sample, sample_shape, curve.mnemonic)
            for sample in selected.values
        ]
        curves.append(
            {
                "mnemonic": curve.mnemonic,
                "original_mnemonic": curve.original_mnemonic or curve.mnemonic,
                "unit": curve.unit,
                "description": curve.description,
                "data_type": _data_type(selected),
                "dimensions": ["frame_index", *(axis.dimension_id for axis in axes)],
                "sample_shape": list(sample_shape),
                "declared_sample_shape": list(curve.sample_shape),
                "shape": [len(selection.row_positions), *sample_shape],
                "element_limit": list(curve.element_limit),
                "origin": curve.origin,
                "copy_number": curve.copy_number,
                "values": values,
            }
        )

    return {
        "schema": SCHEMA_ID,
        "source": {
            "path": str(dataset.source),
            "format": dataset.format.value,
        },
        "dataset": {
            "name": dataset.name,
            "logical_file": dataset.metadata.get("logical_file"),
            "logical_file_index": dataset.metadata.get("logical_file_index"),
            "frame_index": dataset.metadata.get("frame_index"),
            "log_index": dataset.metadata.get("log_index"),
        },
        "row_positions": list(selection.row_positions),
        "primary_index": {
            "name": index_name,
            "kind": (
                dataset.index_kind.value if dataset.index_kind is not None else None
            ),
            "unit": index.unit if index is not None else None,
            "direction": dataset.metadata.get("direction"),
            "values": index_values,
        },
        "dimensions": dimensions,
        "curves": curves,
    }


def long_csv(selection: DataSelection) -> str:
    """Serialize one CSV row per scalar curve element."""

    selected_axes = [
        _resolve_axes(item.curve, _effective_shape(item.curve))
        for item in selection.curves
    ]
    max_rank = max((len(axes) for axes in selected_axes), default=0)
    fields = [
        "row_position",
        "index_name",
        "index_value",
        "index_unit",
        "curve",
        "original_mnemonic",
        "curve_unit",
        "curve_description",
        "data_type",
        "sample_shape",
        "rank",
    ]
    for axis_index in range(max_rank):
        prefix = f"axis_{axis_index}"
        fields.extend(
            [
                f"{prefix}_id",
                f"{prefix}_name",
                f"{prefix}_unit",
                f"{prefix}_position",
                f"{prefix}_coordinate",
            ]
        )
    fields.append("value")

    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    dataset = selection.dataset
    index = dataset.index
    index_name = index.mnemonic if index is not None else "ROW"
    index_unit = index.unit if index is not None else None

    for selected, axes in zip(selection.curves, selected_axes, strict=True):
        curve = selected.curve
        shape = _effective_shape(curve)
        for row_position, index_value, sample in zip(
            selection.row_positions,
            selection.index_values,
            selected.values,
            strict=True,
        ):
            normalized = _normalized_sample(sample, shape, curve.mnemonic)
            axis_positions = (
                product(*(range(size) for size in shape)) if shape else [()]
            )
            for positions in axis_positions:
                value = _nested_value(normalized, positions)
                record: dict[str, object] = {
                    "row_position": row_position,
                    "index_name": index_name,
                    "index_value": _csv_value(index_value),
                    "index_unit": index_unit or "",
                    "curve": curve.mnemonic,
                    "original_mnemonic": curve.original_mnemonic or curve.mnemonic,
                    "curve_unit": curve.unit or "",
                    "curve_description": curve.description or "",
                    "data_type": _data_type(selected),
                    "sample_shape": json.dumps(list(shape), separators=(",", ":")),
                    "rank": len(shape),
                    "value": _csv_value(value),
                }
                for axis_index, (axis, position) in enumerate(
                    zip(axes, positions, strict=True)
                ):
                    prefix = f"axis_{axis_index}"
                    record[f"{prefix}_id"] = axis.dimension_id
                    record[f"{prefix}_name"] = axis.source_name or ""
                    record[f"{prefix}_unit"] = axis.unit or ""
                    record[f"{prefix}_position"] = position
                    record[f"{prefix}_coordinate"] = _csv_value(
                        axis.coordinates[position]
                    )
                writer.writerow(record)
    return stream.getvalue()


def selection_parquet(selection: DataSelection) -> bytes:
    """Serialize a mixed scalar/array selection as an Arrow Parquet table."""

    import pyarrow as pa
    import pyarrow.parquet as pq

    dataset = selection.dataset
    index = dataset.index
    index_name = index.mnemonic if index is not None else "ROW"
    arrays: list[pa.Array] = [
        pa.array([_arrow_value(value) for value in selection.index_values])
    ]
    fields: list[pa.Field] = [
        pa.field(
            index_name,
            arrays[0].type,
            metadata={
                b"wellio": _metadata_bytes(
                    {
                        "schema": SCHEMA_ID,
                        "role": "frame_index",
                        "unit": index.unit if index is not None else None,
                        "kind": (
                            dataset.index_kind.value
                            if dataset.index_kind is not None
                            else None
                        ),
                    }
                )
            },
        )
    ]

    for selected in selection.curves:
        curve = selected.curve
        if curve is index:
            continue
        shape = _effective_shape(curve)
        axes = _resolve_axes(curve, shape)
        samples = [
            _normalized_sample(sample, shape, curve.mnemonic)
            for sample in selected.values
        ]
        if shape:
            value_type = _arrow_scalar_type(selected, samples)
            try:
                if _contains_null_list(samples, len(shape)):
                    arrow_type: pa.DataType = value_type
                    for _ in shape:
                        arrow_type = pa.list_(arrow_type)
                    array = pa.array(samples, type=arrow_type)
                    parquet_shape_encoding = "variable-list-for-null-samples"
                else:
                    array = _fixed_size_list_array(samples, shape, value_type)
                    parquet_shape_encoding = "fixed-size-list"
            except (pa.ArrowException, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Curve {curve.mnemonic!r} cannot be converted to Parquet: {exc}"
                ) from exc
        else:
            parquet_shape_encoding = "primitive"
            try:
                array = pa.array([_arrow_value(sample) for sample in samples])
            except (pa.ArrowException, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Curve {curve.mnemonic!r} cannot be converted to Parquet: {exc}"
                ) from exc

        field_metadata = {
            "schema": SCHEMA_ID,
            "mnemonic": curve.mnemonic,
            "original_mnemonic": curve.original_mnemonic or curve.mnemonic,
            "unit": curve.unit,
            "description": curve.description,
            "data_type": _data_type(selected),
            "sample_shape": list(shape),
            "declared_sample_shape": list(curve.sample_shape),
            "dimensions": [_axis_payload(axis) for axis in axes],
            "element_limit": list(curve.element_limit),
            "parquet_shape_encoding": parquet_shape_encoding,
        }
        arrays.append(array)
        fields.append(
            pa.field(
                curve.mnemonic,
                array.type,
                metadata={b"wellio": _metadata_bytes(field_metadata)},
            )
        )

    schema_metadata = _metadata_bytes(
        {
            "schema": SCHEMA_ID,
            "source": str(dataset.source),
            "format": dataset.format.value,
            "dataset": dataset.name,
            "row_positions": list(selection.row_positions),
        }
    )
    table = pa.Table.from_arrays(
        arrays,
        schema=pa.schema(fields, metadata={b"wellio": schema_metadata}),
    )
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink)
    return sink.getvalue().to_pybytes()


def _fixed_size_list_array(
    values: list[object],
    shape: tuple[int, ...],
    value_type: "pa.DataType",
) -> "pa.Array":
    """Build dense fixed-size children so null outer samples round trip."""

    import pyarrow as pa

    size = shape[0]
    flattened: list[object] = []
    null_mask: list[bool] = []
    for value in values:
        is_null = value is None
        null_mask.append(is_null)
        if is_null:
            flattened.extend([None] * size)
            continue
        items = list(value)  # type: ignore[arg-type]
        if len(items) != size:
            raise ValueError(f"List has {len(items)} values; expected {size}")
        flattened.extend(items)

    child = (
        _fixed_size_list_array(flattened, shape[1:], value_type)
        if len(shape) > 1
        else pa.array([_arrow_value(value) for value in flattened], type=value_type)
    )
    return pa.FixedSizeListArray.from_arrays(
        child,
        size,
        mask=pa.array(null_mask),
    )


def _contains_null_list(values: list[object], rank: int) -> bool:
    if rank == 0:
        return False
    for value in values:
        if value is None:
            return True
        if rank > 1 and _contains_null_list(list(value), rank - 1):  # type: ignore[arg-type]
            return True
    return False


def array_preview(selection: DataSelection) -> str:
    """Format a bounded text preview for exactly one array curve."""

    if len(selection.curves) != 1:
        raise ValueError("Array preview requires exactly one selected curve")
    selected = selection.curves[0]
    curve = selected.curve
    shape = _effective_shape(curve)
    if not shape:
        raise ValueError(f"Curve {curve.mnemonic!r} is scalar")
    axes = _resolve_axes(curve, shape)
    index = selection.dataset.index
    index_name = index.mnemonic if index is not None else "ROW"
    index_unit = f" {index.unit}" if index is not None and index.unit else ""
    lines = [
        f"Curve: {curve.mnemonic}",
        f"Original mnemonic: {curve.original_mnemonic or curve.mnemonic}",
        f"Unit: {curve.unit or '-'}",
        f"Data type: {_data_type(selected)}",
        f"Sample shape: {shape}",
        (
            f"Selected {index_name}{index_unit}: "
            f"{_display_value(selection.index_values[0])} to "
            f"{_display_value(selection.index_values[-1])} "
            f"({len(selection.row_positions)} rows)"
        ),
        f"Selected data shape: ({len(selection.row_positions)}, "
        + ", ".join(str(size) for size in shape)
        + ")",
        "Sample axes:",
    ]
    for axis_index, axis in enumerate(axes):
        label = axis.source_name or axis.identifier or f"axis {axis_index}"
        unit = f", unit={axis.unit}" if axis.unit else ""
        lines.append(
            f"  [{axis_index}] {label}: size={axis.size}{unit}, "
            f"coordinates={axis.coordinate_source}"
        )

    first = _normalized_sample(selected.values[0], shape, curve.mnemonic)
    last = _normalized_sample(selected.values[-1], shape, curve.mnemonic)
    lines.append(f"First sample: {_bounded_flat_values(first)}")
    lines.append(f"Last sample: {_bounded_flat_values(last)}")
    return "\n".join(lines)


def _resolve_axes(curve: Curve, shape: tuple[int, ...]) -> tuple[_ResolvedAxis, ...]:
    if len(curve.sample_axes) > len(shape):
        raise ValueError(
            f"Curve {curve.mnemonic!r} declares {len(curve.sample_axes)} axes "
            f"for sample shape {shape}"
        )

    resolved: list[_ResolvedAxis] = []
    for axis_index, size in enumerate(shape):
        native_axis = (
            curve.sample_axes[axis_index]
            if axis_index < len(curve.sample_axes)
            else SampleAxis()
        )
        errors = native_axis.metadata.get("validation_errors", [])
        if errors:
            message = "; ".join(str(error) for error in errors)
            raise ValueError(f"Curve {curve.mnemonic!r}: {message}")
        if len(native_axis.coordinates) > size:
            raise ValueError(
                f"Curve {curve.mnemonic!r} axis {axis_index} declares "
                f"{len(native_axis.coordinates)} coordinates for size {size}"
            )
        coordinates, source = _axis_coordinates(native_axis, size)
        declared = native_axis.metadata.get(
            "declared_coordinates", native_axis.coordinates
        )
        resolved.append(
            _ResolvedAxis(
                dimension_id=f"{curve.mnemonic}.axis{axis_index}",
                source_name=native_axis.name,
                identifier=native_axis.identifier,
                size=size,
                unit=native_axis.unit,
                coordinates=coordinates,
                coordinate_source=source,
                declared_coordinates=tuple(declared or ()),
                declared_spacing=native_axis.metadata.get(
                    "declared_spacing", native_axis.spacing
                ),
                property_type=native_axis.property_type,
                source_metadata=native_axis.metadata,
            )
        )
    return tuple(resolved)


def _axis_coordinates(axis: SampleAxis, size: int) -> tuple[tuple[object, ...], str]:
    coordinates = tuple(axis.coordinates)
    declared_source = axis.metadata.get("coordinate_source")
    if len(coordinates) == size:
        source = str(declared_source or "recorded")
        return coordinates, source

    spacing = axis.spacing
    if coordinates and isinstance(spacing, Real):
        start = coordinates[0]
        if isinstance(start, Real):
            expected = tuple(start + position * spacing for position in range(size))
            consistent = all(
                isinstance(value, Real)
                and math.isclose(float(value), float(expected[position]))
                for position, value in enumerate(coordinates)
                if position < size
            )
            if consistent:
                return expected, "derived"
    return tuple(range(size)), "position"


def _axis_payload(axis: _ResolvedAxis) -> dict[str, object]:
    return {
        "id": axis.dimension_id,
        "role": "sample_axis",
        "source_name": axis.source_name,
        "axis_identifier": axis.identifier,
        "size": axis.size,
        "unit": axis.unit,
        "property_type": axis.property_type,
        "coordinates": [
            _data_value(value, axis.dimension_id) for value in axis.coordinates
        ],
        "coordinate_source": axis.coordinate_source,
        "declared_coordinates": [
            _metadata_value(value) for value in axis.declared_coordinates
        ],
        "declared_spacing": _metadata_value(axis.declared_spacing),
        "source_metadata": _metadata_value(axis.source_metadata),
    }


def _effective_shape(curve: Curve) -> tuple[int, ...]:
    return () if curve.is_scalar else curve.sample_shape


def _normalized_sample(
    sample: object,
    shape: tuple[int, ...],
    curve_name: str,
) -> object:
    if not shape:
        if _is_missing(sample):
            return None
        array_shape = getattr(sample, "shape", None)
        if array_shape and prod(array_shape) == 1:
            return _data_value(sample.reshape(-1)[0], curve_name)  # type: ignore[attr-defined]
        return _data_value(sample, curve_name)
    if _is_missing(sample):
        return None

    import numpy as np

    try:
        if np.ma.isMaskedArray(sample):
            sample = sample.filled(float("nan"))
        array = np.asarray(sample, dtype=object)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Curve {curve_name!r} contains an unsupported array sample: {exc}"
        ) from exc
    expected_count = prod(shape)
    if array.size != expected_count:
        raise ValueError(
            f"Curve {curve_name!r} sample has {array.size} values; "
            f"expected {expected_count} for shape {shape}"
        )
    return _data_value(array.reshape(shape, order="C").tolist(), curve_name)


def _nested_value(sample: object, positions: tuple[int, ...]) -> object:
    if sample is None:
        return None
    value = sample
    for position in positions:
        value = value[position]  # type: ignore[index]
    return value


def _data_type(selected: SelectedCurve) -> str:
    if selected.curve.data_type:
        return selected.curve.data_type
    try:
        import numpy as np

        dtype = np.asarray(selected.values).dtype
        if dtype.name != "object":
            return dtype.name
    except (TypeError, ValueError):
        pass
    for sample in selected.values:
        for value in _flatten(sample):
            if not _is_missing(value):
                return type(value).__name__
    return "unknown"


def _arrow_scalar_type(selected: SelectedCurve, samples: list[object]) -> "pa.DataType":
    import pyarrow as pa

    data_type = (selected.curve.data_type or "").casefold()
    if data_type in {"byte", "int", "long", "short"}:
        return pa.int64()
    if data_type in {"double", "float"}:
        return pa.float64()
    if data_type in {"date time", "string", "string16", "string40", "unknown"}:
        return pa.string()
    try:
        import numpy as np

        dtype = np.asarray(selected.values).dtype
        if dtype.name != "object":
            return pa.from_numpy_dtype(dtype)
    except (TypeError, ValueError, pa.ArrowNotImplementedError):
        pass
    values = [_arrow_value(value) for sample in samples for value in _flatten(sample)]
    values = [value for value in values if value is not None]
    if not values:
        return pa.string()
    try:
        return pa.array(values).type
    except (pa.ArrowException, TypeError, ValueError) as exc:
        raise ValueError(
            f"Curve {selected.curve.mnemonic!r} has unsupported element values: {exc}"
        ) from exc


def _data_value(value: object, context: str) -> object:
    if _is_missing(value):
        return None
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _data_value(item(), context)
        except ValueError:
            pass
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, bool):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return [_data_value(item, context) for item in value]
    raise ValueError(
        f"{context!r} contains unsupported value type {type(value).__name__}"
    )


def _metadata_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): _metadata_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_metadata_value(item) for item in value]
    try:
        return _data_value(value, "metadata")
    except ValueError:
        return str(value)


def _metadata_bytes(value: object) -> bytes:
    return json.dumps(
        _metadata_value(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        import numpy as np

        if np.ma.is_masked(value):
            return True
    except TypeError:
        pass
    if isinstance(value, Real) and not isinstance(value, bool):
        return not math.isfinite(float(value))
    return False


def _arrow_value(value: object) -> object:
    return _data_value(value, "Arrow value")


def _csv_value(value: object) -> object:
    normalized = _data_value(value, "CSV value")
    return "" if normalized is None else normalized


def _flatten(value: object):  # type: ignore[no-untyped-def]
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _flatten(item)
    elif hasattr(value, "flat"):
        yield from value.flat  # type: ignore[attr-defined]
    else:
        yield value


def _display_value(value: object) -> str:
    normalized = _data_value(value, "display value")
    return "null" if normalized is None else str(normalized)


def _bounded_flat_values(sample: object) -> str:
    if sample is None:
        return "null"
    values = list(_flatten(sample))
    shown = ", ".join(_display_value(value) for value in values[:12])
    suffix = ", ..." if len(values) > 12 else ""
    return f"[{shown}{suffix}]"
