"""Tabular serialization for selected well-log data."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def dataframe_csv(frame: "pd.DataFrame") -> str:
    """Serialize an indexed DataFrame as CSV with the index as the first column."""

    return frame.reset_index().to_csv(index=False, lineterminator="\n")


def dataframe_json(frame: "pd.DataFrame") -> str:
    """Serialize an indexed DataFrame as JSON row records."""

    return (
        frame.reset_index().to_json(
            orient="records",
            date_format="iso",
            force_ascii=False,
        )
        + "\n"
    )


def dataframe_parquet(frame: "pd.DataFrame") -> bytes:
    """Serialize an indexed DataFrame as Parquet with the index first."""

    return frame.reset_index().to_parquet(index=False)
