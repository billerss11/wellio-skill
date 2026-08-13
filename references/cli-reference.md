# Wellio CLI Reference

Use this file for exact syntax and expected results. Use `wellio` below as shorthand for either runner:

```text
"<skill-dir>/scripts/wellio.exe" COMMAND ...
python "<skill-dir>/scripts/run_wellio.py" -- COMMAND ...
```

Prefer the EXE on Windows. See [runtime-setup.md](runtime-setup.md) for fallback and build behavior.

## Supported input

| Input | Support |
|---|---|
| LAS | LAS 2.0; wrapped or unwrapped |
| DLIS | RP66v1; scalar channels are queryable/exportable |
| WITSML | Offline 1.4.1.1 `logs` XML with depth or time indexes |
| `.xml` | Routed to WITSML, then namespace/version validated |

Do not expect WITSML server/ETP access, well-log editing/writing, database management, or built-in petrophysical interpretation.

## Commands and results

| Command | Purpose | Expected result |
|---|---|---|
| `wellio detect FILE` | Detect by extension | One token: `las`, `dlis`, `witsml`, or `unknown`; content is not parsed |
| `wellio info FILE` | Plan a query | Well/index metadata, ranges, datasets, row status/counts, curve names and units |
| `wellio inspect FILE [--format text\|json]` | Retrieve full metadata | Normalized and native metadata; raw curve samples excluded |
| `wellio curve FILE CURVE [OPTIONS]` | Query one curve | Text summary by default; indexed CSV/JSON rows when requested |
| `wellio extract FILE [OPTIONS]` | Query/export several curves | Index plus requested scalar curves as CSV/JSON/Parquet |

For DLIS, `info` lists logical files and frames without loading sample arrays. For WITSML, it lists each log separately.

Text `curve` output contains the selected range, point/valid/missing counts, completeness, first/last values, and—when numeric—minimum, maximum, mean, median, and sample standard deviation.

## Selectors and bounds

Use these options where accepted:

```text
--logical-file INDEX, --log INDEX   Select DLIS logical file or WITSML log
--frame INDEX                       Select DLIS frame
--start VALUE                       Inclusive primary-index start
--stop VALUE                        Inclusive primary-index stop
--rows START:STOP                   Zero-based, half-open row slice
--curve NAME                        Select a curve; repeat for extract
```

Rules:

- Treat all selectors as zero-based.
- Omit a dataset/frame selector only when exactly one choice exists.
- Allow open row bounds: `:100` or `100:`.
- Never combine `--rows` with `--start` or `--stop`.
- Expect an empty selection to fail.
- Reject multidimensional DLIS channels and WITSML arrays from tabular `curve`/`extract`; inspect them with `info` or `inspect`.
- Omit `--curve` from `extract` to include all scalar curves.
- Include the primary index in every CSV/JSON/Parquet result.

## Output

```text
--format text|csv|json       curve
--format csv|json|parquet    extract
--output PATH
--force
```

- Print text, CSV, or JSON to stdout when `--output` is omitted.
- Require `--output PATH` for Parquet.
- Require the output directory to exist.
- Refuse to replace an existing file unless `--force` is supplied.
- Use exit code `1` with `Error: MESSAGE` for application/data failures.
- Use exit code `2` for invalid CLI syntax or argument validation.

## Examples

```text
wellio info "sample.las"
wellio curve "sample.las" GR --start 1000 --stop 1100
wellio curve "sample.xml" ROP --log 0 --rows 0:20 --format json
wellio extract "sample.dlis" --logical-file 0 --frame 0 --curve GR --curve TENS --format csv
wellio extract "sample.las" --curve GR --format parquet --output "gr.parquet"
```
