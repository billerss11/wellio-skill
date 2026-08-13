# Wellio CLI Reference

Use this reference for exact command selection and current product limits.

## Runner

Use one working runner consistently:

```text
wellio
conda run -n cx_wellio wellio
python -m wellio
```

Prefer the first runner that successfully returns help. If installation is required and permitted, use an isolated Python 3.12+ environment. The source project is `https://github.com/billerss11/Wellio_CLI`.

Example Conda installation:

```powershell
conda create -n cx_wellio python=3.12 -y
conda run -n cx_wellio python -m pip install "git+https://github.com/billerss11/Wellio_CLI.git"
```

## Supported input

- LAS files: current verification covers LAS 2.0, wrapped and unwrapped.
- DLIS files: RP66v1; scalar channels can be queried and exported.
- WITSML files: offline WITSML 1.4.1.1 `logs` XML documents with depth or time indexes.
- `.xml` is routed as WITSML but still requires a valid supported namespace and version.

Wellio does not provide WITSML server access, ETP, curve editing, file writing, database management, or built-in petrophysical interpretation.

## Commands

Replace `wellio` below with the resolved runner when necessary.

```text
wellio detect FILE
```

Return the extension-based format: `las`, `dlis`, `witsml`, or `unknown`. This does not parse or validate file content.

```text
wellio info FILE
```

Return well metadata, index details, ranges, row/curve counts, and curve inventory. For DLIS, list logical files and frames without loading curve arrays. For WITSML, list each log separately.

```text
wellio inspect FILE [--format text|json] [--logical-file INDEX|--log INDEX]
```

Return detailed normalized and native metadata. Inspection excludes raw curve samples.

```text
wellio curve FILE CURVE_NAME [OPTIONS]
```

Summarize or return one curve. Relevant options:

```text
--logical-file INDEX, --log INDEX
--frame INDEX
--start VALUE
--stop VALUE
--rows START:STOP
--format text|csv|json
--output PATH
--force
```

Text output includes point counts, completeness, first/last values, and numeric minimum, maximum, mean, median, and sample standard deviation. CSV or JSON includes index and sample values.

```text
wellio extract FILE [OPTIONS]
```

Return selected curves or all scalar curves. Relevant options:

```text
--curve NAME              Repeat for multiple curves
--logical-file INDEX, --log INDEX
--frame INDEX
--start VALUE
--stop VALUE
--rows START:STOP
--format csv|json|parquet
--output PATH
--force
```

The primary index is always included. Parquet is binary and requires `--output PATH`.

## Query rules

- Treat `--start` and `--stop` as inclusive primary-index bounds.
- Treat `--rows START:STOP` as a zero-based, half-open positional slice.
- Allow omitted row bounds such as `:100` and `100:`.
- Never combine `--rows` with `--start` or `--stop`.
- Treat DLIS logical-file and frame selectors as zero-based.
- Treat WITSML log selectors as zero-based.
- Omit a selector only when exactly one valid choice exists.
- Expect an empty selection to fail.
- Expect multidimensional DLIS channels and WITSML array curves to be visible in `info` and `inspect` but rejected by tabular `curve` and `extract` operations.
- Protect existing output files unless `--force` is explicitly provided.
- Ensure the output directory already exists.

Application failures use exit code `1` and `Error: MESSAGE`. Invalid CLI usage uses exit code `2`.
