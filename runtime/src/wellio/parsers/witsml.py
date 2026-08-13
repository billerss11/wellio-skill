"""Offline WITSML 1.4.1.1 log parser."""

from __future__ import annotations

from collections import Counter, defaultdict
from math import prod
from pathlib import Path
from xml.etree.ElementTree import Element, ParseError

from defusedxml import ElementTree as DefusedElementTree
from defusedxml.common import DefusedXmlException

from wellio.exceptions import WellioError
from wellio.models import (
    Curve,
    Dataset,
    IndexKind,
    LogicalFile,
    SampleAxis,
    WellLogFile,
    WellLogFormat,
)

WITSML_NAMESPACE = "http://www.witsml.org/schemas/1series"
WITSML_VERSION = "1.4.1.1"

_INTEGER_TYPES = {"byte", "int", "long", "short"}
_FLOAT_TYPES = {"double", "float"}
_TEXT_TYPES = {"date time", "string", "string16", "string40", "unknown"}
_MISSING = object()


def _tag(name: str) -> str:
    return f"{{{WITSML_NAMESPACE}}}{name}"


def _children(parent: Element, name: str) -> list[Element]:
    return list(parent.findall(_tag(name)))


def _child(parent: Element, name: str) -> Element | None:
    return parent.find(_tag(name))


def _text(parent: Element, name: str) -> str | None:
    element = _child(parent, name)
    if element is None or element.text is None:
        return None
    value = element.text.strip()
    return value or None


def _required_text(parent: Element, name: str, context: str) -> str:
    value = _text(parent, name)
    if value is None:
        raise WellioError(f"{context} is missing required {name}")
    return value


def _required_element_text(parent: Element, name: str, context: str) -> str:
    element = _child(parent, name)
    if element is None:
        raise WellioError(f"{context} is missing required {name}")
    return (element.text or "").strip()


def _curve_null_token(parent: Element) -> object:
    element = _child(parent, "nullValue")
    if element is None:
        return _MISSING
    return (element.text or "").strip()


def _element_unit(parent: Element, name: str) -> str | None:
    element = _child(parent, name)
    if element is None:
        return None
    return _clean(element.attrib.get("uom"))


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _index_kind(index_type: str) -> IndexKind:
    normalized = index_type.casefold()
    if "depth" in normalized:
        return IndexKind.DEPTH
    if "time" in normalized or "date" in normalized:
        return IndexKind.TIME
    return IndexKind.OTHER


def _coordinate_tokens(axis: Element, name: str) -> tuple[str, ...]:
    value = _text(axis, name)
    return tuple(value.split()) if value is not None else ()


def _numeric_coordinates(
    tokens: tuple[str, ...],
    count: int,
    axis_context: str,
) -> tuple[tuple[object, ...], object | None, str | None]:
    try:
        declared = tuple(float(token) for token in tokens)
    except ValueError:
        return (), None, f"{axis_context} has non-numeric doubleValues"
    if len(declared) > count:
        return declared, None, (
            f"{axis_context} declares {len(declared)} coordinates for count {count}"
        )
    if len(declared) == count:
        spacing = declared[-1] - declared[-2] if len(declared) >= 2 else None
        return declared, spacing, None
    if len(declared) < 2:
        return declared, None, (
            f"{axis_context} needs at least two numeric coordinates to expand "
            f"to count {count}"
        )
    spacing = declared[-1] - declared[-2]
    expanded = list(declared)
    while len(expanded) < count:
        expanded.append(expanded[-1] + spacing)
    return tuple(expanded), spacing, None


def _sample_axes(
    curve_element: Element,
    context: str,
) -> tuple[tuple[int, ...], tuple[SampleAxis, ...]]:
    axes: list[tuple[int, int, SampleAxis]] = []
    order_errors: list[str] = []
    for axis_index, axis in enumerate(_children(curve_element, "axisDefinition")):
        axis_context = f"{context} axisDefinition {axis_index}"
        try:
            order = int(_required_text(axis, "order", axis_context))
            count = int(_required_text(axis, "count", axis_context))
        except ValueError as exc:
            raise WellioError(
                f"{axis_context} order and count must be integers"
            ) from exc
        if count < 1:
            raise WellioError(f"{axis_context} count must be positive")
        if order < 1:
            order_errors.append(f"{axis_context} order must be positive")

        numeric_tokens = _coordinate_tokens(axis, "doubleValues")
        string_tokens = _coordinate_tokens(axis, "stringValues")
        coordinate_error: str | None = None
        coordinate_source = "position"
        spacing: object | None = None
        coordinates: tuple[object, ...] = ()
        declared_coordinates: tuple[object, ...] = ()
        if numeric_tokens and string_tokens:
            coordinate_error = (
                f"{axis_context} declares both doubleValues and stringValues"
            )
        elif numeric_tokens:
            declared_coordinates = numeric_tokens
            coordinates, spacing, coordinate_error = _numeric_coordinates(
                numeric_tokens, count, axis_context
            )
            coordinate_source = (
                "recorded" if len(numeric_tokens) == count else "derived"
            )
        elif string_tokens:
            declared_coordinates = string_tokens
            coordinates = string_tokens
            coordinate_source = "recorded"
            if len(string_tokens) != count:
                coordinate_error = (
                    f"{axis_context} declares {len(string_tokens)} string "
                    f"coordinates for count {count}"
                )

        errors = [error for error in (coordinate_error,) if error is not None]
        axes.append(
            (
                order,
                count,
                SampleAxis(
                    name=_text(axis, "name"),
                    identifier=_text(axis, "uid") or _clean(axis.attrib.get("uid")),
                    unit=_text(axis, "uom") or _clean(axis.attrib.get("uom")),
                    property_type=_text(axis, "propertyType"),
                    coordinates=coordinates,
                    spacing=spacing,
                    native=axis,
                    metadata={
                        "order": order,
                        "count": count,
                        "declared_coordinates": declared_coordinates,
                        "coordinate_source": coordinate_source,
                        "validation_errors": errors,
                    },
                ),
            )
        )

    orders = [order for order, _, _ in axes]
    if len(orders) != len(set(orders)):
        order_errors.append(f"{context} has duplicate array-axis order values")
    if orders and sorted(orders) != list(range(1, len(orders) + 1)):
        order_errors.append(
            f"{context} array-axis order values must be contiguous from 1"
        )

    ordered = sorted(axes, key=lambda item: item[0])
    if order_errors and ordered:
        ordered[0][2].metadata["validation_errors"].extend(order_errors)
    return (
        tuple(count for _, count, _ in ordered),
        tuple(axis for _, _, axis in ordered),
    )


def _unique_curve_names(original_names: list[str]) -> list[str]:
    counts = Counter(name.casefold() for name in original_names)
    occurrences: defaultdict[str, int] = defaultdict(int)
    used: set[str] = set()
    names: list[str] = []

    for original in original_names:
        key = original.casefold()
        occurrences[key] += 1
        candidate = (
            f"{original}:{occurrences[key]}" if counts[key] > 1 else original
        )
        suffix = 2
        unique = candidate
        while unique.casefold() in used:
            unique = f"{candidate}:{suffix}"
            suffix += 1
        used.add(unique.casefold())
        names.append(unique)
    return names


def _curve_definitions(
    native_log: Element,
    log_context: str,
) -> tuple[list[Curve], list[object]]:
    elements = _children(native_log, "logCurveInfo")
    originals = [
        _required_text(element, "mnemonic", f"{log_context} curve {index}")
        for index, element in enumerate(elements)
    ]
    unique_names = _unique_curve_names(originals)
    curves: list[Curve] = []
    null_tokens: list[object] = []

    for index, (element, original, mnemonic) in enumerate(
        zip(elements, originals, unique_names, strict=True)
    ):
        context = f"{log_context} curve {original!r} at position {index}"
        data_type = _required_text(element, "typeLogData", context).casefold()
        if data_type not in _INTEGER_TYPES | _FLOAT_TYPES | _TEXT_TYPES:
            raise WellioError(f"{context} has unsupported typeLogData {data_type!r}")
        sample_shape, sample_axes = _sample_axes(element, context)
        curves.append(
            Curve(
                mnemonic=mnemonic,
                original_mnemonic=original,
                values=[],
                unit=_text(element, "unit"),
                description=_text(element, "curveDescription"),
                data_type=data_type,
                sample_shape=sample_shape,
                sample_axes=sample_axes,
                native=element,
            )
        )
        null_tokens.append(_curve_null_token(element))

    if not curves:
        raise WellioError(f"{log_context} contains no logCurveInfo definitions")
    return curves, null_tokens


def _curve_positions(curves: list[Curve]) -> dict[str, list[int]]:
    positions: defaultdict[str, list[int]] = defaultdict(list)
    for index, curve in enumerate(curves):
        positions[(curve.original_mnemonic or curve.mnemonic).casefold()].append(index)
    return dict(positions)


def _block_curve_indexes(
    mnemonics: list[str],
    positions: dict[str, list[int]],
    context: str,
) -> list[int]:
    occurrences: defaultdict[str, int] = defaultdict(int)
    indexes: list[int] = []
    for mnemonic in mnemonics:
        key = mnemonic.casefold()
        occurrence = occurrences[key]
        occurrences[key] += 1
        candidates = positions.get(key, [])
        if occurrence >= len(candidates):
            raise WellioError(
                f"{context} references undeclared curve mnemonic {mnemonic!r}"
            )
        indexes.append(candidates[occurrence])
    return indexes


def _is_null(value: str, curve_null: object, log_null: str | None) -> bool:
    if not value:
        return True
    null_token = curve_null if curve_null is not _MISSING else log_null
    return null_token is not None and value == null_token


def _scalar_value(value: str, data_type: str, context: str) -> object:
    try:
        if data_type in _INTEGER_TYPES:
            return int(value)
        if data_type in _FLOAT_TYPES:
            return float(value)
        return value
    except ValueError as exc:
        raise WellioError(
            f"{context} value {value!r} is not valid for {data_type}"
        ) from exc


def _curve_value(
    raw_value: str,
    curve: Curve,
    curve_null: object,
    log_null: str | None,
    context: str,
) -> object:
    value = raw_value.strip()
    if _is_null(value, curve_null, log_null):
        return None

    sample_count = prod(curve.sample_shape) if curve.sample_shape else 1
    if sample_count == 1:
        return _scalar_value(value, curve.data_type or "unknown", context)

    values = value.split()
    if len(values) != sample_count:
        raise WellioError(
            f"{context} has {len(values)} array values; expected {sample_count}"
        )
    flat_values = tuple(
        (
            None
            if _is_null(item, curve_null, log_null)
            else _scalar_value(item, curve.data_type or "unknown", context)
        )
        for item in values
    )
    return _reshape_sample(flat_values, curve.sample_shape)


def _reshape_sample(
    values: tuple[object, ...],
    shape: tuple[int, ...],
) -> tuple[object, ...]:
    """Reshape flat WITSML values in C order (order 1 is slowest)."""

    if len(shape) <= 1:
        return values
    chunk_size = prod(shape[1:])
    return tuple(
        _reshape_sample(values[offset : offset + chunk_size], shape[1:])
        for offset in range(0, len(values), chunk_size)
    )


def _load_data(
    native_log: Element,
    curves: list[Curve],
    curve_nulls: list[object],
    log_null: str | None,
    delimiter: str,
    log_context: str,
) -> None:
    positions = _curve_positions(curves)
    for block_index, block in enumerate(_children(native_log, "logData")):
        context = f"{log_context} logData block {block_index}"
        mnemonics = [
            value.strip()
            for value in _required_text(block, "mnemonicList", context).split(",")
        ]
        units_text = _required_element_text(block, "unitList", context)
        units = [value.strip() or None for value in units_text.split(",")]
        if len(units) != len(mnemonics):
            raise WellioError(
                f"{context} has {len(mnemonics)} mnemonics but {len(units)} units"
            )

        curve_indexes = _block_curve_indexes(mnemonics, positions, context)
        for mnemonic, unit, curve_index in zip(
            mnemonics, units, curve_indexes, strict=True
        ):
            curve = curves[curve_index]
            if curve.unit is not None and unit is not None and curve.unit != unit:
                raise WellioError(
                    f"{context} unit {unit!r} for {mnemonic!r} does not match "
                    f"declared unit {curve.unit!r}"
                )
            if curve.unit is None:
                curve.unit = unit

        for row_index, row in enumerate(_children(block, "data")):
            raw_row = row.text or ""
            values = raw_row.split(delimiter)
            if len(values) != len(mnemonics):
                raise WellioError(
                    f"{context} row {row_index} has {len(values)} values; "
                    f"expected {len(mnemonics)}"
                )
            for curve in curves:
                curve.values.append(None)
            for raw_value, curve_index in zip(values, curve_indexes, strict=True):
                curve = curves[curve_index]
                curve.values[-1] = _curve_value(
                    raw_value,
                    curve,
                    curve_nulls[curve_index],
                    log_null,
                    f"{context} row {row_index} curve "
                    f"{curve.original_mnemonic!r}",
                )


def _dataset(source: Path, native_log: Element, log_index: int) -> Dataset:
    log_name = _text(native_log, "name")
    log_uid = _clean(native_log.attrib.get("uid"))
    name = log_name or log_uid or f"log-{log_index}"
    context = f"WITSML log [{log_index}] {name!r}"
    index_type = _required_text(native_log, "indexType", context)
    index_name = _required_text(native_log, "indexCurve", context)
    delimiter = _text(native_log, "dataDelimiter") or ","
    if len(delimiter) > 2:
        raise WellioError(f"{context} dataDelimiter must contain at most 2 characters")

    curves, curve_nulls = _curve_definitions(native_log, context)
    index_matches = [
        curve
        for curve in curves
        if (curve.original_mnemonic or curve.mnemonic).casefold()
        == index_name.casefold()
    ]
    if len(index_matches) != 1:
        raise WellioError(
            f"{context} indexCurve {index_name!r} must match exactly one curve"
        )

    log_null = _text(native_log, "nullValue")
    _load_data(
        native_log,
        curves,
        curve_nulls,
        log_null,
        delimiter,
        context,
    )

    return Dataset(
        source=source,
        format=WellLogFormat.WITSML,
        name=name,
        curves=curves,
        index=index_matches[0],
        index_kind=_index_kind(index_type),
        metadata={
            "witsml_version": WITSML_VERSION,
            "log_index": log_index,
            "log_uid": log_uid,
            "well_uid": _clean(native_log.attrib.get("uidWell")),
            "wellbore_uid": _clean(native_log.attrib.get("uidWellbore")),
            "well_name": _text(native_log, "nameWell"),
            "wellbore_name": _text(native_log, "nameWellbore"),
            "log_name": log_name,
            "service_company": _text(native_log, "serviceCompany"),
            "run_number": _text(native_log, "runNumber"),
            "creation_date": _text(native_log, "creationDate"),
            "description": _text(native_log, "description"),
            "index_type": index_type,
            "direction": _text(native_log, "direction"),
            "start_index": _text(native_log, "startIndex")
            or _text(native_log, "startDateTimeIndex"),
            "start_index_unit": _element_unit(native_log, "startIndex"),
            "end_index": _text(native_log, "endIndex")
            or _text(native_log, "endDateTimeIndex"),
            "end_index_unit": _element_unit(native_log, "endIndex"),
            "step_increment": _text(native_log, "stepIncrement"),
            "step_increment_unit": _element_unit(native_log, "stepIncrement"),
            "null_value": log_null,
            "data_delimiter": delimiter,
        },
        native=native_log,
    )


def read_witsml(path: str | Path) -> WellLogFile:
    """Read an offline WITSML 1.4.1.1 log document."""

    source = Path(path)
    try:
        parsed = DefusedElementTree.parse(source)
    except (ParseError, DefusedXmlException, OSError) as exc:
        raise WellioError(f"Could not read WITSML file {source}: {exc}") from exc

    root = parsed.getroot()
    if root.tag != _tag("logs"):
        raise WellioError(
            f"Unsupported WITSML root in {source}; expected 1series logs"
        )
    version = _clean(root.attrib.get("version"))
    if version != WITSML_VERSION:
        raise WellioError(
            f"Unsupported WITSML version in {source}: {version or 'missing'}; "
            f"expected {WITSML_VERSION}"
        )

    native_logs = _children(root, "log")
    if not native_logs:
        raise WellioError(f"WITSML document contains no logs: {source}")

    logical_files: list[LogicalFile] = []
    try:
        for log_index, native_log in enumerate(native_logs):
            dataset = _dataset(source, native_log, log_index)
            logical_files.append(
                LogicalFile(
                    name=dataset.name or f"log-{log_index}",
                    frames=[dataset],
                    native=native_log,
                )
            )
    except WellioError:
        raise
    except Exception as exc:
        raise WellioError(f"Could not read WITSML file {source}: {exc}") from exc

    return WellLogFile(
        source=source,
        format=WellLogFormat.WITSML,
        logical_files=logical_files,
        native=parsed,
    )
