---
name: wellio
description: Inspect and analyze offline LAS, DLIS, and WITSML well-log files with the bundled Wellio CLI. Use when a user asks about file structure, well metadata, logical files or frames, curve inventories, values, statistics, missing data, extrema, trends, depth/time/row intervals, or CSV/JSON/Parquet export.
---

# Wellio Log Analysis

Use Wellio to retrieve data, then answer the user's question. Do not return only commands or raw output.

## Choose the runner

1. Confirm that the log file is locally accessible.
2. On Windows, run the bundled EXE when present:

   ```text
   "<skill-dir>/scripts/wellio.exe" COMMAND [ARGUMENTS] [OPTIONS]
   ```

3. If the EXE is missing, cannot launch, or the platform is not Windows, run:

   ```text
   python "<skill-dir>/scripts/run_wellio.py" -- COMMAND [ARGUMENTS] [OPTIONS]
   ```

4. Do not fall back when a launched EXE reports a normal command, selection, or input-file error. Report that error.

Never use a globally installed Wellio or clone the separate `Wellio_CLI` repository. Commands below use `wellio` as shorthand for the selected runner.

## Analyze the request

1. Run `wellio info FILE` before querying an unfamiliar file.
2. Resolve the requested logical file/log, frame, curves, and interval from `info` output.
3. Retrieve only what the answer requires:

   | Need | Command | Expected result |
   |---|---|---|
   | File type only | `detect FILE` | `las`, `dlis`, `witsml`, or `unknown` |
   | Structure and inventory | `info FILE` | Well/index metadata, datasets, row status/counts, curves, units |
   | Full metadata | `inspect FILE --format json` | Structured normalized/native metadata; no samples |
   | One-curve summary | `curve FILE CURVE` | Range, counts, completeness, first/last, statistics |
   | Actual samples | `curve ... --format json` | Index plus one curve's rows |
   | Multiple curves/export | `extract FILE --curve A --curve B` | Index plus selected scalar curves |

4. Use `--start` and `--stop` for inclusive depth/time bounds. Use `--rows START:STOP` for a zero-based, half-open row slice. Never combine them.
5. Verify the returned dataset, interval, units, and sample count before answering.

Read [references/cli-reference.md](references/cli-reference.md) for exact syntax, formats, selectors, and errors. Read [references/runtime-setup.md](references/runtime-setup.md) only for fallback, environment, build, or launch problems.

## Resolve datasets and curves

- Select the only logical file/log or frame automatically when exactly one exists.
- Match a user-specified dataset to its name or zero-based index.
- Ask one concise question when several datasets remain plausible. Never silently choose index `0`.
- Match curves case-insensitively: exact mnemonic first, then an unambiguous original mnemonic or description.
- Ask when a natural name maps to multiple curves.
- Do not export multidimensional DLIS/WITSML curves as tabular data; report the shape shown by `info`.

## Return the result

Lead with the answer. Always identify the source file and selected dataset, even when the user supplied them. Include only the remaining provenance needed to verify the result:

- source file and selected logical file/log/frame;
- actual index range and unit;
- curve mnemonic, description when useful, and unit;
- requested values, statistics, locations, or observed behavior;
- sample count and material missing-data concerns;
- whether a statement is calculated fact or interpretation.

For a compact single-curve answer, prefer this shape:

```text
Result: <requested value, statistic, or observed behavior>
Source: <file> [logical file/log/frame when applicable]
Interval: <actual start–stop> <index unit>
Curve: <mnemonic> — <description> [<unit>]
Samples: <count>; <missing-data note>
```

Apply these rules:

- For a value at a depth/time, return an exact recorded sample. If absent, say so; label any nearest sample as nearest.
- For behavior over an interval, use samples and report meaningful change, range, center, variability, and completeness. Do not infer a trend from global extrema alone.
- For extrema, ignore missing values and report the index; mention material ties.
- For an unnamed “well overview,” choose at most eight representative scalar curves from descriptions and units, state the selection, and offer other curves.
- For small exports, return the data directly. For large exports, write the requested CSV/JSON/Parquet file and link it.

Create output files only when requested or needed for a large result. Never use `--force` without permission to overwrite that exact path.

## Interpretation boundary

Describe observed curve behavior from data. Claim lithology, porosity, saturation, formation boundaries, borehole condition, or other petrophysical conclusions only when the user requests interpretation and provides or approves a method. Label interpretations and state inputs, assumptions, and missing evidence.

Report malformed, unsupported, empty-range, ambiguous-selection, and multidimensional-data errors plainly.
