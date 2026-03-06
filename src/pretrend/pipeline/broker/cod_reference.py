"""KIS COD reference parsing helpers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


COD_COLUMNS: List[str] = [
    "ncod",
    "exid",
    "excd",
    "exnm",
    "symb",
    "rsym",
    "knam",
    "enam",
    "stis",
    "curr",
    "zdiv",
    "ztyp",
    "base",
    "bnit",
    "anit",
    "mstm",
    "metm",
    "isdr",
    "drcd",
    "icod",
    "sjong",
    "ttyp",
    "etyp",
    "ttyp_sb",
]


@dataclass(frozen=True)
class CodQuality:
    total_rows: int
    invalid_column_rows: int
    missing_symbol_rows: int
    missing_exchange_rows: int

    def as_dict(self) -> Dict[str, int]:
        return {
            "total_rows": self.total_rows,
            "invalid_column_rows": self.invalid_column_rows,
            "missing_symbol_rows": self.missing_symbol_rows,
            "missing_exchange_rows": self.missing_exchange_rows,
        }


def _parse_cod_file(path: Path) -> Tuple[pd.DataFrame, int]:
    rows: List[List[str]] = []
    invalid = 0
    for raw in path.read_text(encoding="cp949").splitlines():
        cols = raw.rstrip("\n").split("\t")
        if len(cols) != 24:
            invalid += 1
            continue
        rows.append(cols)
    df = pd.DataFrame(rows, columns=COD_COLUMNS)
    if not df.empty:
        df["source_file"] = path.name
    return df, invalid


def load_cod_reference(cod_root: Path) -> Tuple[pd.DataFrame, pd.DataFrame, CodQuality]:
    """Load and parse COD files into full universe and ETF-only view."""
    files = sorted(cod_root.glob("*.COD"))
    all_frames: List[pd.DataFrame] = []
    invalid_rows = 0
    for fp in files:
        df, invalid = _parse_cod_file(fp)
        all_frames.append(df)
        invalid_rows += invalid
    full_df = pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame(columns=COD_COLUMNS + ["source_file"])
    if not full_df.empty:
        for col in COD_COLUMNS:
            full_df[col] = full_df[col].astype(str).str.strip()
    etf_df = full_df[full_df["stis"] == "3"].copy() if not full_df.empty else full_df.copy()

    missing_symbol_rows = int((full_df["symb"].fillna("").str.len() == 0).sum()) if not full_df.empty else 0
    missing_exchange_rows = int((full_df["excd"].fillna("").str.len() == 0).sum()) if not full_df.empty else 0
    quality = CodQuality(
        total_rows=int(len(full_df)),
        invalid_column_rows=int(invalid_rows),
        missing_symbol_rows=missing_symbol_rows,
        missing_exchange_rows=missing_exchange_rows,
    )
    return full_df, etf_df, quality

