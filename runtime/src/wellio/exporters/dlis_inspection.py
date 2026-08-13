"""Exhaustive, sample-free DLIS metadata inspection."""

from __future__ import annotations

import base64
import math
import warnings
from collections import Counter
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

from wellio.exceptions import WellioError
from wellio.models import WellLogFile


def dlis_inspection_payload(
    well_file: WellLogFile,
    logical_file: int | None = None,
) -> dict[str, object]:
    """Return all DLIS metadata without reading frame curve arrays."""

    if well_file.closed:
        raise WellioError(f"Well-log file is closed: {well_file.source}")
    indexed_logical_files = list(enumerate(well_file.logical_files))
    if logical_file is not None:
        if not well_file.logical_files:
            raise ValueError("No logical files are available")
        if logical_file < 0 or logical_file >= len(well_file.logical_files):
            choices = f"0 to {len(well_file.logical_files) - 1}"
            raise ValueError(
                f"Logical file index {logical_file} is out of range; choose {choices}"
            )
        indexed_logical_files = [(logical_file, well_file.logical_files[logical_file])]

    logical_payloads: list[dict[str, object]] = []
    for logical_index, logical in indexed_logical_files:
        native_objects = sorted(
            logical.native.find(".*"),
            key=lambda item: (
                str(item.type),
                str(item.name),
                int(item.origin),
                int(item.copynumber),
            ),
        )
        counts = Counter(str(item.type) for item in native_objects)
        fileheader = getattr(logical.native, "fileheader", None)
        logical_payloads.append(
            {
                "index": logical_index,
                "name": logical.name,
                "fingerprint": getattr(fileheader, "fingerprint", None),
                "object_counts": dict(sorted(counts.items())),
                "frames": [
                    _frame_payload(frame_index, dataset)
                    for frame_index, dataset in enumerate(logical.frames)
                ],
                "objects": [_object_payload(item) for item in native_objects],
            }
        )

    return {
        "source": str(well_file.source),
        "format": well_file.format.value,
        "logical_files": logical_payloads,
    }


def _frame_payload(frame_index: int, dataset: Any) -> dict[str, object]:
    index = dataset.index
    return {
        "index": frame_index,
        "name": dataset.name,
        "row_count": None,
        "index_metadata": (
            {
                "mnemonic": index.mnemonic,
                "original_mnemonic": index.original_mnemonic,
                "kind": dataset.index_kind.value if dataset.index_kind else None,
                "type": dataset.metadata.get("index_type"),
                "direction": dataset.metadata.get("direction"),
                "spacing": _json_safe(dataset.metadata.get("spacing")),
                "unit": index.unit,
            }
            if index is not None
            else None
        ),
        "channel_count": dataset.curve_count,
        "channels": [
            {
                "mnemonic": curve.mnemonic,
                "original_mnemonic": curve.original_mnemonic,
                "origin": curve.origin,
                "copy_number": curve.copy_number,
                "fingerprint": getattr(curve.native, "fingerprint", None),
                "unit": curve.unit,
                "description": curve.description,
                "sample_shape": list(curve.sample_shape),
                "is_scalar": curve.is_scalar,
            }
            for curve in dataset.curves
        ],
    }


def _object_payload(item: Any) -> dict[str, object]:
    return {
        "type": str(item.type),
        "name": str(item.name),
        "origin": int(item.origin),
        "copy_number": int(item.copynumber),
        "fingerprint": str(item.fingerprint),
        "attributes": [
            _attribute_payload(item.attic, attribute_name)
            for attribute_name in sorted(item.attic.keys())
        ],
    }


def _attribute_payload(attic: Any, attribute_name: str) -> dict[str, object]:
    attribute = attic[attribute_name]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UnicodeWarning)
        value = attribute.value
    return {
        "name": attribute_name,
        "units": _json_safe(attribute.units),
        "values": _json_safe(value),
    }


def dlis_inspection_text(
    well_file: WellLogFile,
    logical_file: int | None = None,
) -> str:
    """Render exhaustive DLIS metadata as readable terminal text."""

    payload = dlis_inspection_payload(well_file, logical_file)
    lines = [
        f"File: {payload['source']}",
        "Format: DLIS",
    ]
    for logical in payload["logical_files"]:
        lines.extend(
            (
                "",
                f"Logical file [{logical['index']}]: {logical['name']}",
                f"Fingerprint: {logical['fingerprint'] or 'Not available'}",
                "Object counts: "
                + ", ".join(
                    f"{name}={count}"
                    for name, count in logical["object_counts"].items()
                ),
                "Frames:",
            )
        )
        for frame in logical["frames"]:
            lines.append(
                f"- [{frame['index']}] {frame['name']}; rows=Not loaded; "
                f"channels={frame['channel_count']}; "
                f"index={_text_value(frame['index_metadata'])}"
            )
            for channel in frame["channels"]:
                lines.append(
                    f"  - {channel['mnemonic']}; original="
                    f"{channel['original_mnemonic']}; unit="
                    f"{channel['unit'] or 'Not available'}; "
                    f"sample_shape={tuple(channel['sample_shape'])}"
                )
        lines.append("Objects:")
        for item in logical["objects"]:
            lines.append(
                f"- {item['type']} {item['name']} "
                f"(origin={item['origin']}, copy={item['copy_number']}, "
                f"fingerprint={item['fingerprint']})"
            )
            for attribute in item["attributes"]:
                lines.append(
                    f"  - {attribute['name']}; units="
                    f"{_text_value(attribute['units'])}; "
                    f"values={_text_value(attribute['values'])}"
                )
    return "\n".join(lines) + "\n"


def _json_safe(value: object) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {
            "type": "bytes",
            "base64": base64.b64encode(value).decode("ascii"),
        }
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_json_safe(item) for item in sorted(value, key=repr)]

    type_name = f"{type(value).__module__}.{type(value).__name__}"
    if type(value).__module__ == "dlisio.core" and hasattr(value, "id"):
        return {
            "type": type_name,
            "id": str(value.id),
            "origin": int(value.origin),
            "copy_number": int(value.copynumber),
        }
    if type(value).__module__ == "dlisio.core" and hasattr(value, "name"):
        return {
            "type": type_name,
            "object_type": str(value.type),
            "name": _json_safe(value.name),
            "fingerprint": str(value.fingerprint),
        }

    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            return _json_safe(tolist())
        except (TypeError, ValueError):
            pass
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _json_safe(item_method())
        except (TypeError, ValueError):
            pass
    return {"type": type_name, "value": str(value)}


def _text_value(value: object) -> str:
    if value is None or value == "":
        return "Not available"
    return str(value)
