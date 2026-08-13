"""Wellio command-line application."""

from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from wellio.core import (
    CurveSummary,
    detect_format,
    open_file,
    parse_row_slice,
    select_dataframe,
    summarize_curve,
)
from wellio.exporters import (
    dataframe_csv,
    dataframe_json,
    dataframe_parquet,
    inspection_json,
    inspection_text,
)
from wellio.models import Dataset, WellLogFile, WellLogFormat

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


class DataOutput(StrEnum):
    """Supported tabular extraction output formats."""

    CSV = "csv"
    JSON = "json"
    PARQUET = "parquet"


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
) -> None:
    """Describe one curve over a depth, time, or row interval."""

    try:
        with open_file(file) as well_file:
            dataset = well_file.get_dataset(logical_file, frame)
            row_slice = parse_row_slice(rows) if rows is not None else None
            summary, selected_frame = summarize_curve(
                dataset,
                curve_name,
                start=start,
                stop=stop,
                rows=row_slice,
            )
            if output_format is CurveOutput.CSV:
                rendered = dataframe_csv(selected_frame)
            elif output_format is CurveOutput.JSON:
                rendered = dataframe_json(selected_frame)
            else:
                rendered = _format_curve_summary(dataset, summary)
            _emit_or_write(rendered, output=output, force=force)
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
        typer.Option("--curve", "-c", help="Curve to include; repeat as needed."),
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
) -> None:
    """Extract selected curve data as CSV, JSON, or Parquet."""

    try:
        if output_format is DataOutput.PARQUET and output is None:
            raise ValueError("Parquet output requires --output PATH")
        with open_file(file) as well_file:
            dataset = well_file.get_dataset(logical_file, frame)
            row_slice = parse_row_slice(rows) if rows is not None else None
            selected_frame = select_dataframe(
                dataset,
                curve_names,
                start=start,
                stop=stop,
                rows=row_slice,
            )
            if output_format is DataOutput.JSON:
                rendered = dataframe_json(selected_frame)
            elif output_format is DataOutput.PARQUET:
                rendered = dataframe_parquet(selected_frame)
            else:
                rendered = dataframe_csv(selected_frame)
            _emit_or_write(rendered, output=output, force=force)
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


def _emit_or_write(rendered: str | bytes, *, output: Path | None, force: bool) -> None:
    """Write rendered output to stdout or an explicitly selected file."""

    if output is None:
        if isinstance(rendered, bytes):
            raise ValueError("Binary output requires --output PATH")
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
