"""CSV loading utilities for FormPilot."""

from __future__ import annotations

from pathlib import Path
import csv
from typing import Iterable, Literal

import pandas as pd

DEFAULT_ENCODINGS: tuple[str, ...] = (
    "utf-8-sig",
    "utf-8",
    "cp1250",
    "iso-8859-2",
    "latin1",
)


def _detect_delimiter(sample: str) -> str | None:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return None
    return dialect.delimiter


def _read_csv_with_fallback(
    path: Path, encoding: str, delimiter: str | None
) -> pd.DataFrame:
    """Read CSV using either detected delimiter or parser-level auto detection."""

    if delimiter is not None:
        return pd.read_csv(path, encoding=encoding, sep=delimiter)

    # Let pandas infer separator when sniffer cannot decide.
    engine: Literal["python"] = "python"
    return pd.read_csv(path, encoding=encoding, sep=None, engine=engine)


def load_csv(
    file_path: str | Path, encodings: Iterable[str] = DEFAULT_ENCODINGS
) -> pd.DataFrame:
    """Load a CSV file with basic delimiter and encoding fallback support."""

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    last_error: Exception | None = None
    for encoding in encodings:
        try:
            sample = path.read_text(encoding=encoding, errors="strict")[:4096]
            delimiter = _detect_delimiter(sample)
            return _read_csv_with_fallback(
                path=path, encoding=encoding, delimiter=delimiter
            )
        except Exception as exc:  # pragma: no cover - fallback path
            last_error = exc

    raise ValueError(f"Unable to read CSV file: {path}") from last_error
