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
| DLIS | RP66v1; scalar and arbitrary-rank array channels |
| WITSML | Offline 1.4.1.1 `logs` XML with depth/time indexes and N-D arrays |
| `.xml` | Routed to WITSML, then namespace/version validated |

Do not expect WITSML server/ETP access, well-log editing/writing, database management, or built-in petrophysical interpretation.

## Commands and results

| Command | Purpose | Expected result |
|---|---|---|
| `wellio detect FILE` | Detect by extension | One token: `las`, `dlis`, `witsml`, or `unknown`; content is not parsed |
| `wellio info FILE` | Plan a query | Well/index metadata, ranges, datasets, row status/counts, curve names and units |
| `wellio inspect FILE [--format text\|json]` | Retrieve full metadata | Normalized and native metadata; raw curve samples excluded |
| `wellio curve FILE CURVE [OPTIONS]` | Query one curve | Scalar summary or bounded array preview; machine formats when requested |
| `wellio extract FILE [OPTIONS]` | Query/export several curves | Index plus selected scalar/array curves in compatible formats |

For DLIS, `info` lists logical files and frames without loading sample arrays. For WITSML, it lists each log separately.

Scalar text `curve` output contains the selected range, point/valid/missing counts, completeness, first/last values, and—when numeric—minimum, maximum, mean, median, and sample standard deviation. Array text output is deliberately bounded: identity, dtype, sample shape, selected data shape, axes, coordinate sources, and at most 12 flattened values from the first and last samples.

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
- Select array curves explicitly. Omit `--curve` from `extract` to include all scalar curves only.
- Keep complete internal samples; sample-axis slicing is not supported.
- Preserve native/C dimension order. WITSML axis order 1 is slowest-varying.
- Include the primary index in every data result.

## Output

```text
--format text|csv|json|structured-json|long-csv   curve
--format csv|json|structured-json|long-csv|parquet extract
--output PATH
--force
--force-stdout
```

- Legacy CSV/JSON remain scalar-only and reject explicitly selected arrays.
- Structured JSON (`wellio.structured.v1`) contains source/dataset identity, selected source rows, primary-index metadata, a dimension registry, curve shape/dtype/metadata, and nested values.
- Long CSV emits one row per scalar element with enough row, shape, and axis columns to reconstruct every sample exactly.
- Parquet keeps scalar columns primitive and array columns as nested lists with versioned shape/dimension metadata.
- Print small text, CSV, or JSON results to stdout when `--output` is omitted.
- Refuse stdout selections above 100,000 index/curve values before serialization. Every scalar element inside an N-D sample counts.
- Refuse final UTF-8 stdout payloads above 256 KiB. Use a smaller slice, `--output PATH`, or the explicit `--force-stdout` override.
- Require `--output PATH` for Parquet.
- Require the output directory to exist.
- Refuse to replace an existing file unless `--force` is supplied.
- Use exit code `1` with `Error: MESSAGE` for application/data failures.
- Use exit code `2` for invalid CLI syntax or argument validation.

## Large-file behavior

- DLIS `info` and `inspect` do not load frame samples.
- A DLIS data query decodes and caches the complete selected native frame once
  before applying primary-index or row selection. Slicing still prevents
  unselected rows from being expanded into JSON/CSV objects, but it does not
  eliminate the native frame decode cost.
- Structured JSON and long CSV currently build the complete serialized result
  in memory, including when writing to a file. Prefer small slices or nested
  Parquet for very large handoffs.

## Examples

```text
wellio info "sample.las"
wellio curve "sample.las" GR --start 1000 --stop 1100
wellio curve "sample.xml" ROP --log 0 --rows 0:20 --format json
wellio curve "sample.dlis" T2W --logical-file 0 --frame 0 --rows 0:2 --format structured-json
wellio extract "sample.dlis" --logical-file 0 --frame 0 --curve GR --curve TENS --format csv
wellio extract "sample.dlis" --logical-file 0 --frame 0 --curve GR --curve T2W --format parquet --output "mixed.parquet"
wellio extract "sample.las" --curve GR --format parquet --output "gr.parquet"
```
