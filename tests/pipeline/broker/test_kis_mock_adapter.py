from __future__ import annotations

import pytest

from pretrend.pipeline.broker.kis_mock import KISMockAdapter


def test_kis_mock_adapter_dry_run_order(monkeypatch) -> None:
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "mock_key")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "mock_secret")
    monkeypatch.setenv("KIS_MOCK_ACCOUNT_NO", "12345678")
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.setenv("KIS_DRY_RUN", "true")
    adapter = KISMockAdapter.from_env()
    result = adapter.place_buy_order("SPY", qty=1)
    assert result.status in {"FILLED", "ACCEPTED"}
    assert result.symbol == "SPY"
    assert result.side == "BUY"
    assert result.quantity == 1.0
    status = adapter.auth_status()
    assert "token_refresh_count" in status
    assert "auth_status" in status


def test_extract_fx_usdkrw_from_payload() -> None:
    body = {
        "rt_cd": "0",
        "output2": {
            "frst_bltn_exrt": "1,335.25",
        },
    }
    fx = KISMockAdapter._extract_fx_usdkrw(body)
    assert fx is not None
    assert abs(fx - 1335.25) < 1e-9


def test_get_usdkrw_rate_dry_run(monkeypatch) -> None:
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "mock_key")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "mock_secret")
    monkeypatch.setenv("KIS_MOCK_ACCOUNT_NO", "12345678")
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.setenv("KIS_DRY_RUN", "true")
    adapter = KISMockAdapter.from_env()
    assert adapter.get_usdkrw_rate() == 1300.0
    assert adapter.get_orderable_cash_usd("SPY") == 100_000.0
    info = adapter.get_orderable_info("SPY")
    assert info.get("tr_crcy_cd") == "USD"
    assert info.get("ord_psbl_frcr_amt") == 100_000.0


def test_get_foreign_cash_balances_dry_run(monkeypatch) -> None:
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "mock_key")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "mock_secret")
    monkeypatch.setenv("KIS_MOCK_ACCOUNT_NO", "12345678")
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.setenv("KIS_DRY_RUN", "true")
    adapter = KISMockAdapter.from_env()
    rows = adapter.get_foreign_cash_balances()
    assert isinstance(rows, list)
    assert rows
    assert rows[0]["currency"] == "USD"


def test_raise_if_kis_error() -> None:
    with pytest.raises(RuntimeError):
        KISMockAdapter._raise_if_kis_error(
            {"rt_cd": "2", "msg_cd": "OPSQ2001", "msg1": "invalid"},
            "sample",
        )


def test_get_balance_handles_output2_list(monkeypatch) -> None:
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "mock_key")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "mock_secret")
    monkeypatch.setenv("KIS_MOCK_ACCOUNT_NO", "12345678")
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.setenv("KIS_DRY_RUN", "false")

    adapter = KISMockAdapter.from_env()

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "rt_cd": "0",
                "output2": [
                    {
                        "crcy_cd": "USD",
                        "frcr_dncl_amt_2": "100000.0",
                    }
                ],
                "output3": {
                    "tot_asst_amt": "120000.0",
                    "frcr_use_psbl_amt": "100000.0",
                },
            }

    monkeypatch.setattr(adapter, "_ensure_token", lambda: "TOKEN")
    monkeypatch.setattr(adapter, "_request_with_auth_retry", lambda *args, **kwargs: _Resp())
    b = adapter.get_balance()
    assert b.cash == 100000.0
    assert b.total_value == 120000.0


def test_get_foreign_cash_balances_from_output2_rows(monkeypatch) -> None:
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "mock_key")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "mock_secret")
    monkeypatch.setenv("KIS_MOCK_ACCOUNT_NO", "12345678")
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.setenv("KIS_DRY_RUN", "false")

    adapter = KISMockAdapter.from_env()

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "rt_cd": "0",
                "output2": [
                    {"crcy_cd": "USD", "frcr_dncl_amt_2": "10.5"},
                    {"crcy_cd": "JPY", "frcr_dncl_amt_2": "0.0"},
                    {"crcy_cd": "", "frcr_dncl_amt_2": "0.0"},
                ],
            }

    monkeypatch.setattr(adapter, "_ensure_token", lambda: "TOKEN")
    monkeypatch.setattr(adapter, "_request_with_auth_retry", lambda *args, **kwargs: _Resp())
    rows = adapter.get_foreign_cash_balances()
    assert len(rows) == 2
    assert rows[0]["currency"] == "USD"
    assert rows[0]["amount"] == 10.5


def test_get_current_price_handles_empty_string(monkeypatch) -> None:
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "mock_key")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "mock_secret")
    monkeypatch.setenv("KIS_MOCK_ACCOUNT_NO", "12345678")
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.setenv("KIS_DRY_RUN", "false")
    adapter = KISMockAdapter.from_env()

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"rt_cd": "0", "output": {"last": ""}}

    monkeypatch.setattr(adapter, "_ensure_token", lambda: "TOKEN")
    monkeypatch.setattr(adapter, "_request_with_auth_retry", lambda *args, **kwargs: _Resp())
    assert adapter.get_current_price("SPY") == 0.0


def test_get_current_price_uses_cod_mapping(monkeypatch, tmp_path) -> None:
    cod_root = tmp_path / "kis_cod"
    cod_root.mkdir(parents=True, exist_ok=True)
    # 24 columns (tab-separated): use NASQQQ realtime symbol on NAS exchange.
    row = [
        "US", "22", "NAS", "나스닥", "QQQ", "NASQQQ", "인베스코QQQ", "Invesco QQQ",
        "3", "USD", "", "", "", "", "", "", "", "", "", "", "", "", "001", "",
    ]
    (cod_root / "NASMST.COD").write_text("\t".join(row) + "\n", encoding="cp949")

    monkeypatch.setenv("KIS_MOCK_APP_KEY", "mock_key")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "mock_secret")
    monkeypatch.setenv("KIS_MOCK_ACCOUNT_NO", "12345678")
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.setenv("KIS_DRY_RUN", "false")
    monkeypatch.setenv("KIS_COD_ROOT", str(cod_root))
    adapter = KISMockAdapter.from_env()

    calls = []

    class _Resp:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self._body

    def _fake_req(method, url, **kwargs):
        params = kwargs.get("params", {})
        calls.append((params.get("EXCD"), params.get("SYMB")))
        if params.get("EXCD") == "NAS" and params.get("SYMB") in {"NASQQQ", "QQQ"}:
            return _Resp(200, {"rt_cd": "0", "output": {"last": "612.34"}})
        return _Resp(500, {})

    monkeypatch.setattr(adapter, "_ensure_token", lambda: "TOKEN")
    monkeypatch.setattr(adapter, "_request_with_auth_retry", _fake_req)
    px = adapter.get_current_price("QQQ")
    assert abs(px - 612.34) < 1e-9
    assert any(ex == "NAS" and sym in {"NASQQQ", "QQQ"} for ex, sym in calls)


def test_resolve_symbol_market_uses_cod_default(monkeypatch) -> None:
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "mock_key")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "mock_secret")
    monkeypatch.setenv("KIS_MOCK_ACCOUNT_NO", "12345678")
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.setenv("KIS_DRY_RUN", "true")
    adapter = KISMockAdapter.from_env()
    m = adapter._resolve_symbol_market("TLT")
    assert m["excd"] == "NAS"
    assert m["ovrs_excg_cd"] == "NASD"
    assert isinstance(m["rsym"], str) and len(m["rsym"]) > 0
