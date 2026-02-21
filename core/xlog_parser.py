"""CONTAM XLOG results file parser.

Extracts pressure differentials from .xlog files produced by the CONTAM solver.
"""

from pathlib import Path
from typing import List, Optional

import numpy as np

from .prj_parser import check_keywords


def parse_xlog_file(filepath: str) -> Optional[np.ndarray]:
    """Parse an xlog file and extract the pressure differential data table.

    Searches for the 'path offset dPmax Fmax' section and reads all
    subsequent lines that parse as 4 floats.

    Args:
        filepath: Path to the .xlog file

    Returns:
        NumPy array of shape (num_paths, 4) with columns:
        [path_index, offset, dP_max, F_max]
        Returns None if the section is not found.

    Raises:
        FileNotFoundError: If the xlog file doesn't exist
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"XLOG file not found: {filepath}")

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    return _extract_dp_table(lines)


def _extract_dp_table(lines: List[str]) -> Optional[np.ndarray]:
    """Extract the pressure differential table from xlog lines."""
    # Find the header line containing 'pathoffsetdPmaxFmax' (spaces removed)
    header_idx = -1
    for i, line in enumerate(lines):
        if check_keywords(line, "pathoffsetdPmaxFmax"):
            header_idx = i
            break

    if header_idx < 0:
        return None

    # Read data lines after the header
    rows = []
    for i in range(header_idx + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 4:
            break
        try:
            row = [float(p) for p in parts[:4]]
            rows.append(row)
        except ValueError:
            break

    if not rows:
        return None

    return np.array(rows)


def extract_pressure_diffs(
    xlog_filepath: str,
    path_indices: List[int],
) -> np.ndarray:
    """Extract max pressure differentials for specified paths.

    Args:
        xlog_filepath: Path to the .xlog file
        path_indices: List of 1-based path indices to extract

    Returns:
        Array of dP values in Pascals.
        Convert to in. w.c. by multiplying by PA_TO_INWC (dividing by 249).

    Raises:
        FileNotFoundError: If the xlog file doesn't exist
        ValueError: If path indices are invalid or data is missing
    """
    data = parse_xlog_file(xlog_filepath)
    if data is None:
        raise ValueError(
            f"No pressure differential data found in {xlog_filepath}. "
            "The file may not contain a 'path offset dPmax Fmax' section."
        )

    # CONTAM path indices are 1-based, array indices are 0-based
    zero_based = np.array(path_indices) - 1

    # Validate indices
    max_idx = data.shape[0]
    invalid = zero_based[(zero_based < 0) | (zero_based >= max_idx)]
    if len(invalid) > 0:
        raise ValueError(
            f"Invalid path indices (0-based): {invalid.tolist()}. "
            f"XLOG file has {max_idx} paths."
        )

    # Column 2 is dP_max
    return data[zero_based, 2]


def extract_all_pressure_diffs(xlog_filepath: str) -> Optional[np.ndarray]:
    """Extract ALL pressure differentials from an xlog file.

    Returns:
        Full data table as NumPy array, or None if not found.
    """
    return parse_xlog_file(xlog_filepath)
