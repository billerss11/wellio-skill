"""Wellio command-line application."""

from collections import Counter
from enum import StrEnum
from math import prod
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from wellio.core import (
    CurveSummary,
    DataSelection,
    detect_format,
    open_file,
    parse_row_slice,
    select_data,
    select_dataframe,
    summarize_curve,
)
from wellio.exporters import (
    array_preview,
    dataframe_csv,
    dataframe_json,
    dataframe_parquet,
    inspection_json,
    inspection_text,
    long_csv,
    selection_parquet,
    structured_json,
)
from wellio.models import Dataset, WellLogFile, WellLogFormat

if TYPE_CHECKING:
    import pandas as pd


MAX_STDOUT_DATA_VALUES = 100_000
MAX_STDOUT_BYTES = 256 * 1024

app = typer.Typer(
    help="Inspect and convert oilfield well-log files.",
    no_args_is_help=True,
)


class InspectionOutput(StrEnum):
    """Supported exhaustive inspection output formats."""

    TEXT = "text"
    JSON = "json"


class CurveOutput(StrEnum):
    """Supported single-curve output formats."""

    TEXT = "text"
    CSV = "csv"
    JSON = "json"
    STRUCTURED_JSON = "structured-json"
    LONG_CSV = "long-csv"


class DataOutput(StrEnum):
    """Supported tabular extraction output formats."""

    CSV = "csv"
    JSON = "json"
    PARQUET = "parquet"
    STRUCTURED_JSON = "structured-json"
    LONG_CSV = "long-csv"


@app.callback()
def main() -> None:
    """Run the Wellio command-line interface."""


@app.command()
def detect(
    file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Well-log file to inspect.",
        ),
    ],
) -> None:
    """Detect the well-log format of FILE."""

    typer.echo(detect_format(file).value)


@app.command()
def info(
    file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Well-log file to inspect.",
        ),
    ],
) -> None:
    """Display well, index, and curve information for FILE."""

    try:
        with open_file(file) as well_file:
            if well_file.format is WellLogFormat.DLIS:
                _display_dlis_info(well_file)
            elif well_file.format is WellLogFormat.WITSML:
                _display_witsml_info(well_file)
            else:
                _display_dataset_info(well_file.get_dataset())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def inspect(
    file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Well-log file to inspect exhaustively.",
        ),
    ],
    output_format: Annotated[
        InspectionOutput,
        typer.Option("--format", "-f", help="Inspection output format."),
    ] = InspectionOutput.TEXT,
    logical_file: Annotated[
        int | None,
        typer.Option(
            "--logical-file",
            "--log",
            help="Zero-based DLIS logical-file or WITSML log index to inspect.",
        ),
    ] = None,
) -> None:
    """Display every parsed metadata section and item in FILE."""

    try:
        with open_file(file) as well_file:
            inspection_source: Dataset | WellLogFile = (
                well_file
                if well_file.format in {WellLogFormat.DLIS, WellLogFormat.WITSML}
                else well_file.get_dataset(logical_file, None)
            )
            output = (
                inspection_json(inspection_source, logical_file)
                if output_format is InspectionOutput.JSON
                else inspection_text(inspection_source, logical_file)
            )
    except Exception as exc:
        _exit_with_error(exc)
    typer.echo(output, nl=False)


@app.command()
def curve(
    file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Well-log file containing the curve.",
        ),
    ],
    curve_name: Annotated[str, typer.Argument(help="Curve mnemonic to query.")],
    logical_file: Annotated[
        int | None,
        typer.Option(
            "--logical-file",
            "--log",
            help="Zero-based DLIS logical-file or WITSML log index.",
        ),
    ] = None,
    frame: Annotated[
        int | None,
        typer.Option("--frame", help="Zero-based DLIS frame index."),
    ] = None,
    start: Annotated[
        str | None,
        typer.Option("--start", help="Inclusive primary-index start value."),
    ] = None,
    stop: Annotated[
        str | None,
        typer.Option("--stop", help="Inclusive primary-index stop value."),
    ] = None,
    rows: Annotated[
        str | None,
        typer.Option("--rows", help="Zero-based, half-open START:STOP row slice."),
    ] = None,
    output_format: Annotated[
        CurveOutput,
        typer.Option("--format", "-f", help="Curve output format."),
    ] = CurveOutput.TEXT,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", dir_okay=False, help="Write output to PATH."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing output file."),
    ] = False,
    force_stdout: Annotated[
        bool,
        typer.Option(
            "--force-stdout",
            help="Allow exhaustive output above standard-output safety limits.",
        ),
    ] = False,
) -> None:
    """Describe one curve over a depth, time, or row interval."""

    try:
        with open_file(file) as well_file:
            dataset = well_file.get_dataset(logical_file, frame)
            row_slice = parse_row_slice(rows) if rows is not None else None
            selected_curve = dataset.get_curve(curve_name)
            if output_format in {
                CurveOutput.STRUCTURED_JSON,
                CurveOutput.LONG_CSV,
            } or (output_format is CurveOutput.TEXT and not selected_curve.is_scalar):
                selection = select_data(
                    dataset,
                    [selected_curve.mnemonic],
                    start=start,
                    stop=stop,
                    rows=row_slice,
                )
                if output_format is CurveOutput.STRUCTURED_JSON:
                    _guard_selection_stdout(
                        selection,
                        output=output,
                        force_stdout=force_stdout,
                    )
                    rendered = structured_json(selection)
                elif output_format is CurveOutput.LONG_CSV:
                    _guard_selection_stdout(
                        selection,
                        output=output,
                        force_stdout=force_stdout,
                    )
                    rendered = long_csv(selection)
                else:
                    rendered = array_preview(selection) + "\n"
            else:
                if not selected_curve.is_scalar:
                    raise ValueError(
                        f"Curve {selected_curve.mnemonic!r} has sample shape "
                        f"{selected_curve.sample_shape}; use --format "
                        "structured-json or --format long-csv"
                    )
                summary, selected_frame = summarize_curve(
                    dataset,
                    selected_curve.mnemonic,
                    start=start,
                    stop=stop,
                    rows=row_slice,
                )
                if output_format is CurveOutput.CSV:
                    _guard_dataframe_stdout(
                        selected_frame,
                        output=output,
                        force_stdout=force_stdout,
                    )
                    rendered = dataframe_csv(selected_frame)
                elif output_format is CurveOutput.JSON:
                    _guard_dataframe_stdout(
                        selected_frame,
                        output=output,
                        force_stdout=force_stdout,
                    )
                    rendered = dataframe_json(selected_frame)
                else:
                    rendered = _format_curve_summary(dataset, summary)
            _emit_or_write(
                rendered,
                output=output,
                force=force,
                force_stdout=force_stdout,
            )
    except Exception as exc:
        _exit_with_error(exc)


@app.command()
def extract(
    file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Well-log file containing data to extract.",
        ),
    ],
    curve_names: Annotated[
        list[str] | None,
        typer.Option(
            "--curve",
            "-c",
            help="Curve to include; repeat as needed. Arrays must be explicit.",
        ),
    ] = None,
    logical_file: Annotated[
        int | None,
        typer.Option(
            "--logical-file",
            "--log",
            help="Zero-based DLIS logical-file or WITSML log index.",
        ),
    ] = None,
    frame: Annotated[
        int | None,
        typer.Option("--frame", help="Zero-based DLIS frame index."),
    ] = None,
    start: Annotated[
        str | None,
        typer.Option("--start", help="Inclusive primary-index start value."),
    ] = None,
    stop: Annotated[
        str | None,
        typer.Option("--stop", help="Inclusive primary-index stop value."),
    ] = None,
    rows: Annotated[
        str | None,
        typer.Option("--rows", help="Zero-based, half-open START:STOP row slice."),
    ] = None,
    output_format: Annotated[
        DataOutput,
        typer.Option("--format", "-f", help="Extraction output format."),
    ] = DataOutput.CSV,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", dir_okay=False, help="Write output to PATH."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing output file."),
    ] = False,
    force_stdout: Annotated[
        bool,
        typer.Option(
            "--force-stdout",
            help="Allow exhaustive output above standard-output safety limits.",
        ),
    ] = False,
) -> None:
    """Extract selected scalar or explicitly requested array curve data."""

    try:
        if output_format is DataOutput.PARQUET and output is None:
            raise ValueError("Parquet output requires --output PATH")
        with open_file(file) as well_file:
            dataset = well_file.get_dataset(logical_file, frame)
            row_slice = parse_row_slice(rows) if rows is not None else None
            explicit_curves = (
                [dataset.get_curve(name) for name in curve_names]
                if curve_names is not None
                else []
            )
            includes_arrays = any(not curve.is_scalar for curve in explicit_curves)
            if output_format in {
                DataOutput.STRUCTURED_JSON,
                DataOutput.LONG_CSV,
            } or (output_format is DataOutput.PARQUET and includes_arrays):
                selection = select_data(
                    dataset,
                    curve_names,
                    start=start,
                    stop=stop,
                    rows=row_slice,
                )
                if output_format is DataOutput.STRUCTURED_JSON:
                    _guard_selection_stdout(
                        selection,
                        output=output,
                        force_stdout=force_stdout,
                    )
                    rendered = structured_json(selection)
                elif output_format is DataOutput.LONG_CSV:
                    _guard_selection_stdout(
                        selection,
                        output=output,
                        force_stdout=force_stdout,
                    )
                    rendered = long_csv(selection)
                else:
                    rendered = selection_parquet(selection)
            else:
                if includes_arrays:
                    details = ", ".join(
                        f"{curve.mnemonic} shape={curve.sample_shape}"
                        for curve in explicit_curves
                        if not curve.is_scalar
                    )
                    raise ValueError(
                        f"Legacy {output_format.value} cannot export array "
                        f"curves: {details}; use --format structured-json, "
                        "long-csv, or parquet"
                    )
                selected_frame = select_dataframe(
                    dataset,
                    curve_names,
                    start=start,
                    stop=stop,
                    rows=row_slice,
                )
                if output_format is DataOutput.JSON:
                    _guard_dataframe_stdout(
                        selected_frame,
                        output=output,
                        force_stdout=force_stdout,
                    )
                    rendered = dataframe_json(selected_frame)
                elif output_format is DataOutput.PARQUET:
                    rendered = dataframe_parquet(selected_frame)
                else:
                    _guard_dataframe_stdout(
                        selected_frame,
                        output=output,
                        force_stdout=force_stdout,
                    )
                    rendered = dataframe_csv(selected_frame)
            _emit_or_write(
                rendered,
                output=output,
                force=force,
                force_stdout=force_stdout,
            )
    except Exception as exc:
        _exit_with_error(exc)


def _display_dataset_info(dataset: Dataset) -> None:
    """Write a readable dataset summary to the terminal."""

    metadata_rows = (
        ("LAS version", "las_version"),
        ("Well", "well_name"),
        ("API", "api"),
        ("UWI", "uwi"),
        ("Company", "company"),
        ("Operator", "operator"),
        ("Service company", "service_company"),
        ("Field", "field"),
        ("Location", "location"),
        ("County", "county"),
        ("State / Province", "state_province"),
        ("Country", "country"),
        ("Latitude", "latitude"),
        ("Longitude", "longitude"),
        ("Log date", "date"),
        ("Datum", "datum"),
    )

    typer.echo(f"File: {dataset.source}")
    typer.echo(f"Format: {dataset.format.value.upper()}")
    for label, key in metadata_rows:
        typer.echo(f"{label}: {_display_value(dataset.metadata.get(key))}")

    if dataset.index is not None:
        index_kind = dataset.index_kind.value if dataset.index_kind else "unknown"
        typer.echo(f"Index: {dataset.index.mnemonic}")
        typer.echo(f"Index type: {index_kind}")
        typer.echo(f"Index unit: {_display_value(dataset.index.unit)}")
        typer.echo(f"Index range: {_index_range(dataset)}")
    else:
        typer.echo("Index: Not available")

    typer.echo(f"Rows: {dataset.row_count}")
    typer.echo(f"Curves: {dataset.curve_count}")
    typer.echo("\nCurve definitions:")
    for curve in dataset.curves:
        unit = _display_value(curve.unit)
        description = _display_value(curve.description)
        typer.echo(f"- {curve.mnemonic} [{unit}]: {description}")


def _display_dlis_info(well_file: WellLogFile) -> None:
    """Write DLIS hierarchy and metadata without loading frame samples."""

    typer.echo(f"File: {well_file.source}")
    typer.echo("Format: DLIS")
    typer.echo(f"Logical files: {len(well_file.logical_files)}")
    for logical_index, logical in enumerate(well_file.logical_files):
        objects = logical.native.find(".*")
        counts = Counter(str(item.type) for item in objects)
        rendered_counts = ", ".join(
            f"{name}={count}" for name, count in sorted(counts.items())
        )
        typer.echo(f"\nLogical file [{logical_index}]: {logical.name}")
        typer.echo(f"Objects: {rendered_counts or 'None'}")
        typer.echo(f"Frames: {len(logical.frames)}")
        for frame_index, dataset in enumerate(logical.frames):
            typer.echo(f"\n  Frame [{frame_index}]: {dataset.name}")
            typer.echo("  Rows: Not loaded")
            typer.echo(f"  Channels: {dataset.curve_count}")
            if dataset.index is None:
                typer.echo("  Index: Not available")
            else:
                typer.echo(f"  Index: {dataset.index.mnemonic}")
                typer.echo(
                    "  Index type: "
                    f"{_display_value(dataset.metadata.get('index_type'))}"
                )
                typer.echo(
                    f"  Direction: {_display_value(dataset.metadata.get('direction'))}"
                )
                typer.echo(
                    f"  Spacing: {_display_value(dataset.metadata.get('spacing'))}"
                )
                typer.echo(f"  Index unit: {_display_value(dataset.index.unit)}")
            typer.echo("  Channel definitions:")
            for curve in dataset.curves:
                typer.echo(
                    f"  - {curve.mnemonic}; original="
                    f"{_display_value(curve.original_mnemonic)}; "
                    f"unit={_display_value(curve.unit)}; "
                    f"sample_shape={curve.sample_shape}"
                )
                _display_sample_axes(curve, indent="    ")


def _display_witsml_info(well_file: WellLogFile) -> None:
    """Write WITSML log summaries without merging separate logs."""

    typer.echo(f"File: {well_file.source}")
    typer.echo("Format: WITSML")
    typer.echo("Version: 1.4.1.1")
    typer.echo(f"Logs: {len(well_file.logical_files)}")
    for log_index, logical in enumerate(well_file.logical_files):
        dataset = logical.frames[0]
        typer.echo(f"\nLog [{log_index}]: {dataset.name}")
        typer.echo(f"UID: {_display_value(dataset.metadata.get('log_uid'))}")
        typer.echo(f"Well: {_display_value(dataset.metadata.get('well_name'))}")
        typer.echo(
            f"Wellbore: {_display_value(dataset.metadata.get('wellbore_name'))}"
        )
        typer.echo(
            "Service company: "
            f"{_display_value(dataset.metadata.get('service_company'))}"
        )
        typer.echo(f"Rows: {dataset.row_count}")
        typer.echo(f"Curves: {dataset.curve_count}")
        if dataset.index is None:
            typer.echo("Index: Not available")
        else:
            typer.echo(f"Index: {dataset.index.mnemonic}")
            typer.echo(
                f"Index type: {_display_value(dataset.metadata.get('index_type'))}"
            )
            typer.echo(
                f"Direction: {_display_value(dataset.metadata.get('direction'))}"
            )
            typer.echo(f"Index unit: {_display_value(dataset.index.unit)}")
            typer.echo(f"Index range: {_index_range(dataset)}")
        typer.echo("Curve definitions:")
        for curve in dataset.curves:
            typer.echo(
                f"- {curve.mnemonic}; original="
                f"{_display_value(curve.original_mnemonic)}; "
                f"unit={_display_value(curve.unit)}; "
                f"type={_display_value(curve.data_type)}; "
                f"sample_shape={curve.sample_shape}"
            )
            _display_sample_axes(curve, indent="  ")


def _display_sample_axes(curve: object, *, indent: str) -> None:
    """Display declared array-axis metadata without loading sample values."""

    sample_axes = getattr(curve, "sample_axes", ())
    sample_shape = getattr(curve, "sample_shape", ())
    for axis_index, axis in enumerate(sample_axes):
        size = sample_shape[axis_index] if axis_index < len(sample_shape) else "?"
        coordinates = tuple(axis.coordinates)
        if len(coordinates) == size:
            source = axis.metadata.get("coordinate_source", "recorded")
        elif coordinates and axis.spacing is not None:
            source = "derived"
        else:
            source = "position"
        name = axis.name or "Not available"
        identifier = axis.identifier or "Not available"
        unit = axis.unit or "Not available"
        typer.echo(
            f"{indent}axis[{axis_index}]: name={name}; id={identifier}; "
            f"size={size}; unit={unit}; coordinate_source={source}; "
            f"declared_coordinates={len(coordinates)}; "
            f"spacing={_display_value(axis.spacing)}"
        )


def _index_range(dataset: Dataset) -> str:
    """Format the first and last index values without assuming numeric data."""

    if dataset.index is None or len(dataset.index.values) == 0:
        return "Not available"
    first = dataset.index.values[0]
    last = dataset.index.values[-1]
    return f"{first} to {last}"


def _display_value(value: object) -> str:
    """Format optional metadata for terminal output."""

    if value is None or (isinstance(value, str) and not value.strip()):
        return "Not available"
    return str(value)


def _format_curve_summary(dataset: Dataset, summary: CurveSummary) -> str:
    """Format a concise human answer for one curve interval."""

    index = dataset.index
    index_kind = dataset.index_kind.value if dataset.index_kind else "unknown"
    index_name = index.mnemonic if index else "Not available"
    index_unit = _display_value(index.unit if index else None)
    lines = [
        f"File: {dataset.source}",
        f"Well: {_display_value(dataset.metadata.get('well_name'))}",
        f"Index: {index_name} [{index_unit}]",
        f"Index type: {index_kind}",
        f"Selected range: {summary.index_start} to {summary.index_stop}",
        "",
        f"Curve: {summary.curve.mnemonic}",
        f"Original mnemonic: {_display_value(summary.curve.original_mnemonic)}",
        f"Unit: {_display_value(summary.curve.unit)}",
        f"Description: {_display_value(summary.curve.description)}",
        f"Points: {summary.total_points}",
        f"Valid: {summary.valid_points}",
        f"Missing: {summary.missing_points}",
        f"Completeness: {summary.completeness:.1f}%",
        f"First value: {_summary_value(summary.first_value)}",
        f"Last value: {_summary_value(summary.last_value)}",
    ]
    if summary.is_numeric:
        lines.extend(
            (
                f"Minimum: {_summary_value(summary.minimum)}",
                f"Maximum: {_summary_value(summary.maximum)}",
                f"Mean: {_summary_value(summary.mean)}",
                f"Median: {_summary_value(summary.median)}",
                "Sample standard deviation: "
                f"{_summary_value(summary.standard_deviation)}",
            )
        )
    else:
        lines.append(f"Unique values: {summary.unique_values}")
    return "\n".join(lines) + "\n"


def _summary_value(value: object) -> str:
    """Format summary values without displaying NaN as meaningful data."""

    if value is None:
        return "Not available"
    try:
        if bool(value != value):
            return "Not available"
    except (TypeError, ValueError):
        pass
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _selection_value_count(selection: DataSelection) -> int:
    """Count selected index and curve values before text serialization."""

    return len(selection.index_values) + sum(
        len(selected.values) * prod(selected.curve.sample_shape)
        for selected in selection.curves
    )


def _dataframe_value_count(frame: "pd.DataFrame") -> int:
    """Count index and data cells emitted by a tabular serializer."""

    return len(frame.index) + frame.size


def _guard_selection_stdout(
    selection: DataSelection,
    *,
    output: Path | None,
    force_stdout: bool,
) -> None:
    """Reject oversized N-dimensional stdout output before serialization."""

    _guard_stdout_value_count(
        _selection_value_count(selection),
        output=output,
        force_stdout=force_stdout,
    )


def _guard_dataframe_stdout(
    frame: "pd.DataFrame",
    *,
    output: Path | None,
    force_stdout: bool,
) -> None:
    """Reject oversized tabular stdout output before serialization."""

    _guard_stdout_value_count(
        _dataframe_value_count(frame),
        output=output,
        force_stdout=force_stdout,
    )


def _guard_stdout_value_count(
    value_count: int,
    *,
    output: Path | None,
    force_stdout: bool,
) -> None:
    """Apply the standard-output data-value budget."""

    if (
        output is not None
        or force_stdout
        or value_count <= MAX_STDOUT_DATA_VALUES
    ):
        return
    raise ValueError(
        f"Refusing to write {value_count:,} data values to standard output "
        f"(safety limit: {MAX_STDOUT_DATA_VALUES:,}). Use --rows, --start, or "
        "--stop to reduce the selection; use --output PATH to write a file; "
        "or use --force-stdout to override."
    )


def _emit_or_write(
    rendered: str | bytes,
    *,
    output: Path | None,
    force: bool,
    force_stdout: bool = False,
) -> None:
    """Write rendered output to stdout or an explicitly selected file."""

    if output is None:
        if isinstance(rendered, bytes):
            raise ValueError("Binary output requires --output PATH")
        rendered_size = len(rendered.encode("utf-8"))
        if not force_stdout and rendered_size > MAX_STDOUT_BYTES:
            raise ValueError(
                f"Refusing to write {rendered_size:,} bytes to standard output "
                f"(safety limit: {MAX_STDOUT_BYTES:,} bytes). Use --rows, "
                "--start, or --stop to reduce the selection; use --output PATH "
                "to write a file; or use --force-stdout to override."
            )
        typer.echo(rendered, nl=False)
        return
    if output.exists() and not force:
        raise FileExistsError(f"Output file already exists: {output}; use --force")
    if not output.parent.exists():
        raise FileNotFoundError(f"Output directory does not exist: {output.parent}")
    if isinstance(rendered, bytes):
        output.write_bytes(rendered)
    else:
        output.write_text(rendered, encoding="utf-8", newline="")


def _exit_with_error(exc: Exception) -> None:
    """Report a command error consistently and stop execution."""

    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(code=1) from exc
