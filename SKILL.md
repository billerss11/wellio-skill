---
name: wellio
description: Inspect and analyze offline oilfield well-log files with the Wellio CLI, then answer natural-language questions using retrieved LAS, DLIS, or WITSML data. Use when a user provides or references a .las, .dlis, .witsml, or WITSML .xml file and asks about file structure, well metadata, logs or frames, available curves, curve values, statistics, missing data, extrema, trends, or behavior over a depth, time, or row interval; also use when exporting requested samples to CSV, JSON, or Parquet.
---

# Wellio Log Analysis

Use Wellio as the data-retrieval engine. Answer the user's actual question from the retrieved data. Do not stop after explaining a command or dumping raw CLI output.

## Run the bundled runtime

1. Confirm that the referenced log file is locally accessible. Ask for the file or path only when it is missing.
2. Locate this skill's directory and use `scripts/run_wellio.py` for every Wellio operation. Do not clone, pull, or install the separate `Wellio_CLI` repository. Do not substitute a globally installed Wellio command.
3. Invoke the launcher with an available Python interpreter and place Wellio arguments after `--`:

   ```text
   python "<skill-dir>/scripts/run_wellio.py" -- info "<log-file>"
   ```

4. Let the launcher create and maintain the isolated runtime automatically. It installs the Wellio code bundled in this skill under `runtime/` and downloads only the declared third-party Python dependencies.
5. Honor any environment location explicitly requested by the user by passing `--env-dir "<requested-path>"`. Otherwise let `WELLIO_ENV_DIR` or the safe platform default decide the location. Do not ask the user to choose a routine location.
6. Honor a requested environment manager with `--manager uv`, `--manager venv`, or `--manager conda`. Otherwise keep `--manager auto`.
7. Never install into system Python, Conda `base`, `VIRTUAL_ENV`, or `CONDA_PREFIX`. Never delete or replace an existing non-Wellio directory.
8. If the launcher reports that no safe environment manager is available, explain the blocker and ask before installing a Python runtime manager. Do not make the user run setup commands themselves.

Treat reading and terminal output as the default. Create an output file only when the user requests one or when a temporary file is necessary to process a large result. Never use `--force` without explicit permission to replace that exact file.

## Analyze a request

1. Identify the requested file, curve or curves, index interval, and desired result. Accept natural names such as “gamma ray” and resolve them against curve mnemonics, descriptions, and units.
2. Run `wellio info FILE` before querying an unfamiliar file. Use its format, index type and unit, curve inventory, and DLIS/WITSML structure to plan the query.
3. Resolve the dataset:
   - Use the only logical file, frame, or WITSML log automatically when exactly one exists.
   - Select a log or frame when the user's wording identifies it.
   - Ask a concise question when multiple plausible datasets remain. Do not silently choose index `0`.
4. Resolve curve names case-insensitively. Prefer an exact mnemonic, then an unambiguous original mnemonic or description match. Ask when the request maps to multiple curves.
5. Retrieve only the information needed:
   - Use `info` for the well, index, structure, and curve inventory.
   - Use `inspect --format json` for detailed normalized and native metadata.
   - Use `curve` with text output for a one-curve interval summary.
   - Use `curve --format json` or `extract --format json` when actual samples are needed for requested values, comparisons, extrema locations, changes, or calculations not present in the text summary.
   - Use `extract` with repeated `--curve` options for multiple curves.
6. Apply `--start` and `--stop` to depth or time bounds. Apply `--rows START:STOP` only when the user asks by row position. Never combine row slicing with index bounds.
7. Verify that the returned interval and units match the request. Do not interpolate an unrecorded value unless the user explicitly asks for interpolation. Label a nearest-sample result as nearest rather than exact.

Read [references/cli-reference.md](references/cli-reference.md) for command syntax, selection rules, supported formats, and current limitations. Read [references/runtime-setup.md](references/runtime-setup.md) when the launcher needs troubleshooting or the user requests a custom environment.

## Answer natural-language questions

Return a direct answer, not a command transcript. Include enough provenance for another person to verify it:

- Identify the file and selected DLIS logical file/frame or WITSML log.
- State the actual index range and index unit.
- Name every reported curve and its unit.
- Report the requested values, statistics, locations, or observed behavior.
- State the number of samples and missing-data/completeness concerns when relevant.
- Distinguish facts calculated from samples from interpretation or inference.

For common request types:

- **“What is this value at this depth/time?”** Return the exact recorded sample. If there is no exact sample, say so and offer or report the nearest sample only when appropriate.
- **“How does this curve look over this interval?”** Report its start/end values, range, center, variability, completeness, and meaningful observed changes. Use actual samples when describing a trend; do not infer a trend from only a global minimum and maximum.
- **“Where is the maximum/minimum?”** Retrieve samples, ignore missing values, calculate the extremum, and report every tied index when the tie is material.
- **“How does the well look over this interval?”** If no curves are named, inspect the inventory and summarize a compact representative set of available scalar curves, such as gamma ray, spontaneous potential, caliper, density, neutron, sonic, and resistivity. Use descriptions and units rather than mnemonic guesses, select no more than eight automatically, and state which curves were selected. Offer to examine other curves.
- **“Give/export the data.”** Return a small requested result directly. For larger results, create the requested CSV, JSON, or Parquet file and link it instead of flooding the response.

Prefer a compact table when comparing several curves or index locations. Preserve meaningful precision from the source and avoid inventing extra decimal places.

## Interpretation boundary

Describe observed curve behavior confidently when the data supports it. Do not claim lithology, porosity, saturation, formation boundaries, borehole condition, or other geological/petrophysical conclusions unless the user explicitly requests interpretation and supplies or approves an appropriate interpretation method. Clearly label any such conclusion as an interpretation, list the curves and assumptions used, and state important missing inputs.

Do not treat filename-extension detection as content validation. Report malformed, unsupported, multidimensional, empty-range, or ambiguous-selection errors plainly.
