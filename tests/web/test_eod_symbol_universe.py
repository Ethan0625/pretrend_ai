import re
from pathlib import Path

from pretrend.pipeline.config.eod_observability import OBSERVABILITY_SYMBOLS_V1


def test_web_eod_symbol_universe_matches_backend_sot() -> None:
    source = Path("apps/web/src/pages/_shared.tsx").read_text(encoding="utf-8")
    block_match = re.search(
        r"export const EOD_SYMBOL_UNIVERSE = \[(?P<body>.*?)\] as const;",
        source,
        flags=re.S,
    )
    assert block_match is not None

    web_symbols = re.findall(r'symbol: "([^"]+)"', block_match.group("body"))

    assert web_symbols == OBSERVABILITY_SYMBOLS_V1
    assert "GLD" not in web_symbols
    assert "IAU" in web_symbols
