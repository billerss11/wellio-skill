"""LAS parser adapter backed by lasio."""

from pathlib import Path
from typing import Any

import lasio

from wellio.models import (
    Curve,
    Dataset,
    IndexKind,
    MetadataItem,
    MetadataSection,
    WellLogFormat,
)

_METADATA_ALIASES = {
    "well_name": ("WELL",),
    "api": ("API",),
    "uwi": ("UWI",),
    "company": ("COMP", "COMPANY"),
    "service_company": ("SRVC", "LCNM", "SERVICE_COMPANY"),
    "field": ("FLD", "FIELD"),
    "location": ("LOC", "LOCATION"),
    "county": ("CNTY", "COUNTY"),
    "state_province": ("STAT", "PROV", "STATE", "PROVINCE"),
    "country": ("CTRY", "COUNTRY"),
    "latitude": ("LATI", "LAT", "LATITUDE"),
    "longitude": ("LONG", "LON", "LONGITUDE"),
    "date": ("DATE",),
    "datum": ("PDAT", "DATUM"),
}

_DEPTH_MNEMONICS = {"DEPT", "DEPTH", "MD", "MEASURED_DEPTH"}
_TIME_MNEMONICS = {"TIME", "DATE", "DATETIME", "TIMESTAMP"}
_DEPTH_UNITS = {"F", "FT", "FEET", "M", "METRE", "METRES", "METER", "METERS"}
_TIME_UNITS = {
    "H",
    "HR",
    "HOUR",
    "HOURS",
    "MIN",
    "MN",
    "MS",
    "MSEC",
    "S",
    "SEC",
    "SECOND",
    "SECONDS",
}


def read_las(path: str | Path) -> Dataset:
    """Read a LAS file into the common Wellio dataset model."""

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Well-log file does not exist: {source}")
    if not source.is_file():
        raise IsADirectoryError(f"Well-log path is not a file: {source}")

    native = _read_native(source)
    curves = [_to_curve(curve) for curve in native.curves]
    index = curves[0] if curves else None

    return Dataset(
        source=source,
        format=WellLogFormat.LAS,
        curves=curves,
        index=index,
        index_kind=_classify_index(index),
        metadata=_extract_metadata(native),
        sections=_extract_sections(native),
        native=native,
    )


def _read_native(source: Path) -> lasio.LASFile:
    """Prefer lossless UTF-8, then retain lasio's legacy-file fallback."""

    try:
        return lasio.read(
            source,
            mnemonic_case="preserve",
            encoding="utf-8-sig",
            encoding_errors="strict",
        )
    except UnicodeDecodeError:
        return lasio.read(source, mnemonic_case="preserve")


def _to_curve(curve: Any) -> Curve:
    """Convert a lasio curve without copying its data array."""

    mnemonic = str(curve.mnemonic)
    return Curve(
        mnemonic=mnemonic,
        original_mnemonic=str(getattr(curve, "original_mnemonic", None) or mnemonic),
        unit=str(curve.unit) if curve.unit else None,
        description=str(curve.descr) if curve.descr else None,
        values=curve.data,
        sample_shape=(1,),
        native=curve,
    )


def _classify_index(index: Curve | None) -> IndexKind | None:
    """Classify a LAS index from its original mnemonic and unit."""

    if index is None:
        return None

    mnemonic = (index.original_mnemonic or index.mnemonic).upper()
    unit = (index.unit or "").upper()

    if mnemonic in _TIME_MNEMONICS:
        return IndexKind.TIME
    if mnemonic in _DEPTH_MNEMONICS:
        return IndexKind.DEPTH
    if unit in _TIME_UNITS:
        return IndexKind.TIME
    if unit in _DEPTH_UNITS:
        return IndexKind.DEPTH
    return IndexKind.OTHER


def _extract_metadata(native: lasio.LASFile) -> dict[str, object]:
    """Extract common metadata while retaining the native LAS sections."""

    null_value = _header_value(native, ("NULL",), ("Well",), None)
    metadata = {
        key: _header_value(
            native,
            aliases,
            ("Well", "Parameter"),
            null_value,
        )
        for key, aliases in _METADATA_ALIASES.items()
    }
    metadata["operator"] = (
        _header_value(
            native,
            ("OPER", "OPERATOR"),
            ("Well", "Parameter"),
            null_value,
        )
        or metadata["company"]
    )
    metadata.update(
        {
            "las_version": _header_value(native, ("VERS",), ("Version",), null_value),
            "wrap": _header_value(native, ("WRAP",), ("Version",), null_value),
            "delimiter": _header_value(native, ("DLM",), ("Version",), null_value),
            "null_value": _to_python_scalar(null_value),
        }
    )
    return metadata


def _extract_sections(native: lasio.LASFile) -> list[MetadataSection]:
    """Preserve every lasio section item in native order."""

    sections: list[MetadataSection] = []
    for section_name, native_section in native.sections.items():
        if isinstance(native_section, str):
            sections.append(MetadataSection(name=section_name, text=native_section))
            continue

        items: list[MetadataItem] = []
        try:
            iterator = iter(native_section)
        except TypeError as exc:
            raise TypeError(
                f"Unsupported LAS section {section_name!r}: "
                f"{type(native_section).__name__}"
            ) from exc

        for native_item in iterator:
            if not hasattr(native_item, "mnemonic"):
                raise TypeError(
                    f"Unsupported item in LAS section {section_name!r}: "
                    f"{type(native_item).__name__}"
                )
            mnemonic = str(native_item.mnemonic)
            original = getattr(native_item, "original_mnemonic", None)
            unit = getattr(native_item, "unit", None)
            description = getattr(native_item, "descr", None)
            items.append(
                MetadataItem(
                    mnemonic=mnemonic,
                    original_mnemonic=str(original) if original is not None else None,
                    value=_to_python_scalar(getattr(native_item, "value", None)),
                    unit=str(unit) if unit is not None else None,
                    description=(str(description) if description is not None else None),
                )
            )
        sections.append(MetadataSection(name=section_name, items=items))
    return sections


def _header_value(
    native: lasio.LASFile,
    aliases: tuple[str, ...],
    section_names: tuple[str, ...],
    null_value: object,
) -> object | None:
    """Find the first non-empty header value matching the aliases."""

    alias_set = {alias.upper() for alias in aliases}
    for section_name in section_names:
        section = native.sections.get(section_name)
        if section is None or isinstance(section, str):
            continue
        for item in section:
            original = getattr(item, "original_mnemonic", None)
            mnemonic = str(original or getattr(item, "mnemonic", "")).upper()
            if mnemonic not in alias_set:
                continue
            value = _to_python_scalar(getattr(item, "value", None))
            if _is_missing_header_value(value, null_value):
                continue
            return value
    return None


def _to_python_scalar(value: object) -> object:
    """Convert NumPy-like scalar header values to ordinary Python values."""

    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return item_method()
        except ValueError:
            pass
    return value


def _is_missing_header_value(value: object, null_value: object) -> bool:
    """Return whether a normalized header value represents missing data."""

    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    try:
        if bool(value != value):
            return True
    except (TypeError, ValueError):
        pass
    if null_value is None:
        return False
    try:
        return bool(value == _to_python_scalar(null_value))
    except (TypeError, ValueError):
        return False
