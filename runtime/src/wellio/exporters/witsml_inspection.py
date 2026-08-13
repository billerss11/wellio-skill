"""Text and JSON-safe inspection for WITSML 1.4.1.1 logs."""

import math
from datetime import date, datetime
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element, ElementTree

from wellio.exceptions import WellioError
from wellio.models import WellLogFile
from wellio.parsers.witsml import WITSML_NAMESPACE, WITSML_VERSION


def _split_tag(tag: str) -> tuple[str | None, str]:
    if tag.startswith("{") and "}" in tag:
        namespace, name = tag[1:].split("}", 1)
        return namespace, name
    return None, tag


def _name(element: Element) -> str:
    return _split_tag(str(element.tag))[1]


def _xml_node(element: Element) -> dict[str, object]:
    namespace, name = _split_tag(str(element.tag))
    return {
        "name": name,
        "namespace": namespace,
        "attributes": dict(element.attrib),
        "text": element.text.strip() if element.text and element.text.strip() else None,
        "children": [_xml_node(child) for child in element],
    }


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
    return str(value)


def _selected_logs(
    well_file: WellLogFile,
    log_index: int | None,
) -> list[tuple[int, Any]]:
    indexed_logs = list(enumerate(well_file.logical_files))
    if log_index is None:
        return indexed_logs
    if log_index < 0 or log_index >= len(well_file.logical_files):
        choices = f"0 to {len(well_file.logical_files) - 1}"
        raise ValueError(
            f"WITSML log index {log_index} is out of range; choose {choices}"
        )
    return [(log_index, well_file.logical_files[log_index])]


def witsml_inspection_payload(
    well_file: WellLogFile,
    log_index: int | None = None,
) -> dict[str, object]:
    """Return WITSML metadata without including raw sample values."""

    if well_file.closed:
        raise WellioError(f"Well-log file is closed: {well_file.source}")
    native_tree = well_file.native
    if not isinstance(native_tree, ElementTree):
        raise WellioError("WITSML native representation is not an XML tree")
    root = native_tree.getroot()

    logs: list[dict[str, object]] = []
    for index, logical in _selected_logs(well_file, log_index):
        dataset = logical.frames[0]
        native_log = logical.native
        data_blocks = []
        metadata_nodes = []
        for child in native_log:
            if _name(child) != "logData":
                metadata_nodes.append(_xml_node(child))
                continue
            mnemonic_list = next(
                (item for item in child if _name(item) == "mnemonicList"), None
            )
            unit_list = next(
                (item for item in child if _name(item) == "unitList"), None
            )
            data_blocks.append(
                {
                    "mnemonics": (
                        [item.strip() for item in (mnemonic_list.text or "").split(",")]
                        if mnemonic_list is not None
                        else []
                    ),
                    "units": (
                        [
                            item.strip() or None
                            for item in (unit_list.text or "").split(",")
                        ]
                        if unit_list is not None
                        else []
                    ),
                    "row_count": sum(1 for item in child if _name(item) == "data"),
                }
            )

        index_curve = dataset.index
        logs.append(
            {
                "index": index,
                "name": dataset.name,
                "uid": dataset.metadata.get("log_uid"),
                "uid_well": dataset.metadata.get("well_uid"),
                "uid_wellbore": dataset.metadata.get("wellbore_uid"),
                "row_count": dataset.row_count,
                "curve_count": dataset.curve_count,
                "index_curve": (
                    {
                        "mnemonic": index_curve.mnemonic,
                        "original_mnemonic": index_curve.original_mnemonic,
                        "kind": (
                            dataset.index_kind.value if dataset.index_kind else None
                        ),
                        "unit": index_curve.unit,
                        "first": (
                            _json_safe(index_curve.values[0])
                            if len(index_curve.values)
                            else None
                        ),
                        "last": (
                            _json_safe(index_curve.values[-1])
                            if len(index_curve.values)
                            else None
                        ),
                    }
                    if index_curve is not None
                    else None
                ),
                "normalized_metadata": {
                    key: _json_safe(value) for key, value in dataset.metadata.items()
                },
                "curves": [
                    {
                        "mnemonic": curve.mnemonic,
                        "original_mnemonic": curve.original_mnemonic,
                        "uid": (
                            curve.native.attrib.get("uid")
                            if isinstance(curve.native, Element)
                            else None
                        ),
                        "unit": curve.unit,
                        "description": curve.description,
                        "data_type": curve.data_type,
                        "sample_shape": list(curve.sample_shape),
                        "is_scalar": curve.is_scalar,
                    }
                    for curve in dataset.curves
                ],
                "data_blocks": data_blocks,
                "metadata": metadata_nodes,
            }
        )

    return {
        "source": str(well_file.source),
        "format": "witsml",
        "version": WITSML_VERSION,
        "metadata": [
            _xml_node(child)
            for child in root
            if _name(child) != "log"
        ],
        "logs": logs,
    }


def _append_node(lines: list[str], node: dict[str, object], indent: str) -> None:
    attributes = node["attributes"]
    rendered_attributes = (
        " " + " ".join(f"{key}={value!r}" for key, value in attributes.items())
        if attributes
        else ""
    )
    text = f": {node['text']}" if node["text"] is not None else ""
    namespace = node["namespace"]
    rendered_namespace = (
        f" [{namespace}]" if namespace and namespace != WITSML_NAMESPACE else ""
    )
    lines.append(
        f"{indent}{node['name']}{rendered_namespace}{rendered_attributes}{text}"
    )
    for child in node["children"]:
        _append_node(lines, child, indent + "  ")


def witsml_inspection_text(
    well_file: WellLogFile,
    log_index: int | None = None,
) -> str:
    """Render WITSML metadata without raw sample values."""

    payload = witsml_inspection_payload(well_file, log_index)
    lines = [
        f"File: {payload['source']}",
        "Format: WITSML",
        f"Version: {payload['version']}",
    ]
    if payload["metadata"]:
        lines.extend(("", "Document metadata:"))
        for node in payload["metadata"]:
            _append_node(lines, node, "- ")

    for log in payload["logs"]:
        lines.extend(
            (
                "",
                f"Log [{log['index']}]: {log['name']}",
                f"UID: {log['uid'] or 'Not available'}",
                "Well: "
                f"{log['normalized_metadata'].get('well_name') or 'Not available'}",
                "Wellbore: "
                f"{log['normalized_metadata'].get('wellbore_name') or 'Not available'}",
                f"Rows: {log['row_count']}",
                f"Curves: {log['curve_count']}",
                f"Index: {log['index_curve'] or 'Not available'}",
                "Curve definitions:",
            )
        )
        for curve in log["curves"]:
            lines.append(
                f"- {curve['mnemonic']}; original={curve['original_mnemonic']}; "
                f"unit={curve['unit'] or 'Not available'}; "
                f"type={curve['data_type'] or 'Not available'}; "
                f"sample_shape={tuple(curve['sample_shape'])}"
            )
        lines.append("Data blocks:")
        for block_index, block in enumerate(log["data_blocks"]):
            lines.append(
                f"- [{block_index}] rows={block['row_count']}; "
                f"mnemonics={block['mnemonics']}"
            )
        lines.append("Metadata nodes:")
        for node in log["metadata"]:
            _append_node(lines, node, "- ")
    return "\n".join(lines) + "\n"
