"""Complete text and JSON inspection of normalized well-log metadata."""

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

from wellio.exporters.dlis_inspection import (
    dlis_inspection_payload,
    dlis_inspection_text,
)
from wellio.exporters.witsml_inspection import (
    witsml_inspection_payload,
    witsml_inspection_text,
)
from wellio.models import Dataset, WellLogFile, WellLogFormat


def inspection_payload(
    dataset: Dataset | WellLogFile,
    logical_file: int | None = None,
) -> dict[str, object]:
    """Build a JSON-safe, ordered representation of parsed dataset metadata."""

    if isinstance(dataset, WellLogFile):
        if dataset.format is WellLogFormat.DLIS:
            return dlis_inspection_payload(dataset, logical_file)
        if dataset.format is WellLogFormat.WITSML:
            return witsml_inspection_payload(dataset, logical_file)
        dataset = dataset.get_dataset(logical_file, None)

    index = dataset.index
    return {
        "source": str(dataset.source),
        "format": dataset.format.value,
        "row_count": dataset.row_count,
        "curve_count": dataset.curve_count,
        "index": (
            {
                "mnemonic": index.mnemonic,
                "original_mnemonic": index.original_mnemonic,
                "kind": dataset.index_kind.value if dataset.index_kind else None,
                "unit": index.unit,
                "description": index.description,
                "first": _json_safe(index.values[0]) if len(index.values) else None,
                "last": _json_safe(index.values[-1]) if len(index.values) else None,
            }
            if index is not None
            else None
        ),
        "normalized_metadata": {
            key: _json_safe(value) for key, value in dataset.metadata.items()
        },
        "sections": [
            (
                {"name": section.name, "kind": "text", "text": section.text}
                if section.text is not None
                else {
                    "name": section.name,
                    "kind": "items",
                    "items": [
                        {
                            "mnemonic": item.mnemonic,
                            "original_mnemonic": item.original_mnemonic,
                            "value": _json_safe(item.value),
                            "unit": item.unit,
                            "description": item.description,
                        }
                        for item in section.items
                    ],
                }
            )
            for section in dataset.sections
        ],
    }


def inspection_json(
    dataset: Dataset | WellLogFile,
    logical_file: int | None = None,
) -> str:
    """Serialize complete parsed metadata as readable JSON."""

    return (
        json.dumps(
            inspection_payload(dataset, logical_file),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


def inspection_text(
    dataset: Dataset | WellLogFile,
    logical_file: int | None = None,
) -> str:
    """Serialize complete parsed metadata as readable terminal text."""

    if isinstance(dataset, WellLogFile) and dataset.format is WellLogFormat.DLIS:
        return dlis_inspection_text(dataset, logical_file)
    if isinstance(dataset, WellLogFile) and dataset.format is WellLogFormat.WITSML:
        return witsml_inspection_text(dataset, logical_file)
    if isinstance(dataset, WellLogFile):
        dataset = dataset.get_dataset(logical_file, None)

    lines = [
        f"File: {dataset.source}",
        f"Format: {dataset.format.value.upper()}",
        f"Rows: {dataset.row_count}",
        f"Curves: {dataset.curve_count}",
        "",
        "Normalized metadata:",
    ]
    lines.extend(
        f"- {key}: {_text_value(value)}" for key, value in dataset.metadata.items()
    )
    lines.extend(("", "Native sections:"))

    for section in dataset.sections:
        lines.extend(("", f"[{section.name}]"))
        if section.text is not None:
            lines.append(section.text)
            continue
        for position, item in enumerate(section.items, start=1):
            original = (
                f"; original={item.original_mnemonic}"
                if item.original_mnemonic and item.original_mnemonic != item.mnemonic
                else ""
            )
            lines.append(
                f"{position}. {item.mnemonic}{original}; "
                f"value={_text_value(item.value)}; unit={_text_value(item.unit)}; "
                f"description={_text_value(item.description)}"
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
    if isinstance(value, (date, datetime, Path)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]

    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _json_safe(item_method())
        except ValueError:
            pass
    raise TypeError(f"Unsupported metadata value type: {type(value).__name__}")


def _text_value(value: object) -> str:
    if value is None or (isinstance(value, str) and not value):
        return "Not available"
    return str(value)
