from __future__ import annotations

from pathlib import Path

from pretrend.pipeline.broker.cod_reference import load_cod_reference


def _write_cod(path: Path, rows: list[str]) -> None:
    path.write_text("\n".join(rows) + "\n", encoding="cp949")


def test_load_cod_reference_parses_and_filters_etf(tmp_path: Path) -> None:
    root = tmp_path / "kis_cod"
    root.mkdir(parents=True, exist_ok=True)
    # stis=3 ETF row, stis=2 stock row
    etf_row = "\t".join(
        [
            "US", "22", "NAS", "나스닥", "QQQ", "NASQQQ", "인베스코 QQQ", "Invesco QQQ",
            "3", "USD", "4", "", "100.0", "1", "1", "0930", "1600", "N", "", "000", "0", "0", "001", "",
        ]
    )
    stk_row = "\t".join(
        [
            "US", "22", "NAS", "나스닥", "AAPL", "NASAAPL", "애플", "Apple Inc",
            "2", "USD", "4", "", "200.0", "1", "1", "0930", "1600", "N", "", "000", "0", "0", "000", "",
        ]
    )
    _write_cod(root / "NASMST.COD", [etf_row, stk_row])
    full_df, etf_df, quality = load_cod_reference(root)
    assert len(full_df) == 2
    assert len(etf_df) == 1
    assert etf_df.iloc[0]["symb"] == "QQQ"
    assert quality.invalid_column_rows == 0

