from __future__ import annotations

import json
import time

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


def test_token_cache_roundtrip(monkeypatch, tmp_path) -> None:
    """Token saved to disk is reloaded by a new adapter instance without calling tokenP."""
    cache_file = tmp_path / "kis_token_cache.json"
    monkeypatch.setenv("KIS_TOKEN_CACHE_PATH", str(cache_file))
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "test_key")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "test_secret")
    monkeypatch.setenv("KIS_MOCK_ACCOUNT_NO", "12345678")
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.setenv("KIS_DRY_RUN", "false")

    adapter1 = KISMockAdapter.from_env()
    # Simulate a token already in memory (as if tokenP was just called)
    from pretrend.pipeline.broker.kis_mock import _TokenState
    adapter1._token = _TokenState(access_token="valid_token", expires_at_epoch=time.time() + 3600)
    adapter1._save_cached_token()

    # New adapter instance should load from cache without calling tokenP
    adapter2 = KISMockAdapter.from_env()
    assert adapter2._token.access_token == "valid_token"
    assert adapter2._token_refresh_count == 0  # no tokenP call


def test_token_cache_ignores_wrong_app_key(monkeypatch, tmp_path) -> None:
    """Cache for a different app_key is not loaded."""
    cache_file = tmp_path / "kis_token_cache.json"
    cache_file.write_text(
        json.dumps({"app_key": "other_key", "access_token": "stale", "expires_at_epoch": time.time() + 3600}),
        encoding="utf-8",
    )
    monkeypatch.setenv("KIS_TOKEN_CACHE_PATH", str(cache_file))
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "test_key")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "test_secret")
    monkeypatch.setenv("KIS_MOCK_ACCOUNT_NO", "12345678")
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.setenv("KIS_DRY_RUN", "false")

    adapter = KISMockAdapter.from_env()
    assert adapter._token.access_token is None


def test_token_cache_ignores_expired(monkeypatch, tmp_path) -> None:
    """Expired cached token is not loaded."""
    cache_file = tmp_path / "kis_token_cache.json"
    cache_file.write_text(
        json.dumps({"app_key": "test_key", "access_token": "old_token", "expires_at_epoch": time.time() - 1}),
        encoding="utf-8",
    )
    monkeypatch.setenv("KIS_TOKEN_CACHE_PATH", str(cache_file))
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "test_key")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "test_secret")
    monkeypatch.setenv("KIS_MOCK_ACCOUNT_NO", "12345678")
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.setenv("KIS_DRY_RUN", "false")

    adapter = KISMockAdapter.from_env()
    assert adapter._token.access_token is None


def test_place_market_order_uses_resolved_exchange_and_price(monkeypatch) -> None:
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
            return {"rt_cd": "0", "output": {"ODNO": "A0001"}}

    captured = {}

    monkeypatch.setattr(
        adapter,
        "_resolve_symbol_market",
        lambda symbol: {"symb": "SCHD", "rsym": "SCHD", "excd": "NYS", "ovrs_excg_cd": "NYSE"},
    )
    monkeypatch.setattr(adapter, "get_current_price", lambda symbol: 27.53)
    monkeypatch.setattr(adapter, "_ensure_token", lambda: "TOKEN")

    def _fake_req(method, url, **kwargs):
        captured["json"] = kwargs.get("json", {})
        return _Resp()

    monkeypatch.setattr(adapter, "_request_with_auth_retry", _fake_req)

    result = adapter.place_buy_order("SCHD", qty=1)

    assert captured["json"]["OVRS_EXCG_CD"] == "NYSE"
    assert captured["json"]["PDNO"] == "SCHD"
    assert captured["json"]["ORD_DVSN"] == "00"
    assert captured["json"]["OVRS_ORD_UNPR"] == "27.53"
    assert result.requested_price == 27.53
    assert result.status == "ACCEPTED"


def test_place_sell_order_uses_us_sell_tr_id(monkeypatch) -> None:
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
            return {"rt_cd": "0", "output": {"ODNO": "S0001"}}

    captured = {}

    monkeypatch.setattr(
        adapter,
        "_resolve_symbol_market",
        lambda symbol: {"symb": "SCHD", "rsym": "SCHD", "excd": "NYS", "ovrs_excg_cd": "NYSE"},
    )
    monkeypatch.setattr(adapter, "get_current_price", lambda symbol: 27.53)
    monkeypatch.setattr(adapter, "_ensure_token", lambda: "TOKEN")

    def _fake_req(method, url, **kwargs):
        captured["tr_id"] = kwargs.get("headers", {}).get("tr_id")
        captured["json"] = kwargs.get("json", {})
        return _Resp()

    monkeypatch.setattr(adapter, "_request_with_auth_retry", _fake_req)

    result = adapter.place_sell_order("SCHD", qty=1)

    assert captured["tr_id"] == "VTTT1006U"
    assert captured["json"]["SLL_TYPE"] == "00"
    assert result.status == "ACCEPTED"


def test_get_order_status_uses_fill_rows(monkeypatch) -> None:
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "mock_key")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "mock_secret")
    monkeypatch.setenv("KIS_MOCK_ACCOUNT_NO", "12345678")
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.setenv("KIS_DRY_RUN", "false")

    adapter = KISMockAdapter.from_env()
    monkeypatch.setattr(
        adapter,
        "_inquire_algo_ccnl",
        lambda order_id, order_date=None: [{"FT_ORD_QTY": "2", "FT_CCLD_QTY": "1"}],
    )
    assert adapter.get_order_status("A0001") == "PARTIAL_FILLED"

    monkeypatch.setattr(
        adapter,
        "_inquire_algo_ccnl",
        lambda order_id, order_date=None: [{"FT_ORD_QTY": "2", "FT_CCLD_QTY": "2"}],
    )
    assert adapter.get_order_status("A0001") == "FILLED"

    monkeypatch.setattr(adapter, "_inquire_algo_ccnl", lambda order_id, order_date=None: [])
    assert adapter.get_order_status("A0001") == "ACCEPTED"


def _dry_run_adapter(monkeypatch) -> KISMockAdapter:
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "mock_key")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "mock_secret")
    monkeypatch.setenv("KIS_MOCK_ACCOUNT_NO", "12345678")
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.setenv("KIS_DRY_RUN", "true")
    return KISMockAdapter.from_env()


def test_cancel_order_dry_run(monkeypatch) -> None:
    """dry_run 모드에서는 API 호출 없이 CANCELLED 반환."""
    adapter = _dry_run_adapter(monkeypatch)
    result = adapter.cancel_order(order_id="ORD-001", symbol="SPY", qty=2, side="BUY")
    assert result["status"] == "CANCELLED"
    assert result["order_id"] == "ORD-001"
    assert result["raw"]["mode"] == "dry_run"


def _live_mock_adapter(monkeypatch) -> KISMockAdapter:
    """dry_run=False adapter with network calls stubbed out."""
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "mock_key")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "mock_secret")
    monkeypatch.setenv("KIS_MOCK_ACCOUNT_NO", "12345678")
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.setenv("KIS_DRY_RUN", "false")
    adapter = KISMockAdapter.__new__(KISMockAdapter)
    from pretrend.pipeline.broker.kis_config import KISConfig
    from pretrend.pipeline.broker.kis_mock import _TokenState
    import requests
    adapter.config = KISConfig.from_env()
    adapter._token = _TokenState(access_token="fake-token", expires_at_epoch=time.time() + 3600)
    adapter._session = requests.Session()
    adapter._token_refresh_count = 0
    adapter._last_refresh_at = None
    adapter._last_auth_error_code = None
    adapter._cod_symbol_map = None
    adapter._request_delay_sec = 0.0
    return adapter


def test_cancel_order_api_success(monkeypatch) -> None:
    """KIS API 정상 응답 시 CANCELLED 반환."""
    adapter = _live_mock_adapter(monkeypatch)

    fake_body = {"rt_cd": "0", "msg_cd": "APBK0013", "msg1": "주문취소 완료", "output": {}}

    class _FakeResp:
        def raise_for_status(self): pass
        def json(self): return fake_body

    monkeypatch.setattr(adapter, "_throttle", lambda: None)
    monkeypatch.setattr(adapter, "_headers", lambda tr_id: {})
    monkeypatch.setattr(
        adapter, "_request_with_auth_retry",
        lambda method, url, **kw: _FakeResp(),
    )

    result = adapter.cancel_order(order_id="ORD-002", symbol="IAU", qty=3, side="SELL")
    assert result["status"] == "CANCELLED"
    assert result["order_id"] == "ORD-002"


def test_cancel_order_api_failure(monkeypatch) -> None:
    """KIS API 오류 응답 시 FAILED 반환 (예외 삼킴)."""
    adapter = _live_mock_adapter(monkeypatch)

    monkeypatch.setattr(adapter, "_throttle", lambda: None)
    monkeypatch.setattr(adapter, "_headers", lambda tr_id: {})
    monkeypatch.setattr(
        adapter, "_request_with_auth_retry",
        lambda method, url, **kw: (_ for _ in ()).throw(RuntimeError("connection timeout")),
    )

    result = adapter.cancel_order(order_id="ORD-003", symbol="SPY", qty=1, side="BUY")
    assert result["status"] == "FAILED"
    assert "connection timeout" in result["error"]


def test_place_order_raises_on_kis_application_error(monkeypatch) -> None:
    """KIS rt_cd != 0 응답 시 RuntimeError 발생 (UUID fallback 방지)."""
    adapter = _live_mock_adapter(monkeypatch)

    class _FakeResp:
        status_code = 200

        def raise_for_status(self): pass

        def json(self):
            return {"rt_cd": "1", "msg_cd": "OPSQ1301", "msg1": "장마감 이후에는 주문이 불가합니다"}

    monkeypatch.setattr(adapter, "_throttle", lambda: None)
    monkeypatch.setattr(adapter, "_headers", lambda tr_id: {})
    monkeypatch.setattr(adapter, "get_current_price", lambda sym: 100.0)
    monkeypatch.setattr(
        adapter, "_request_with_auth_retry",
        lambda method, url, **kw: _FakeResp(),
    )

    import pytest
    with pytest.raises(RuntimeError, match="rt_cd=1"):
        adapter.place_buy_order("SPY", qty=1)


def test_place_order_failed_prefix_when_odno_missing(monkeypatch) -> None:
    """ODNO 없는 성공 응답 시 FAILED- prefix order_id 반환."""
    adapter = _live_mock_adapter(monkeypatch)

    class _FakeResp:
        status_code = 200

        def raise_for_status(self): pass

        def json(self):
            return {"rt_cd": "0", "output": {}}  # ODNO 없음

    monkeypatch.setattr(adapter, "_throttle", lambda: None)
    monkeypatch.setattr(adapter, "_headers", lambda tr_id: {})
    monkeypatch.setattr(adapter, "get_current_price", lambda sym: 100.0)
    monkeypatch.setattr(
        adapter, "_request_with_auth_retry",
        lambda method, url, **kw: _FakeResp(),
    )

    result = adapter.place_buy_order("IAU", qty=2)
    assert result.status == "FAILED"
    assert result.order_id.startswith("FAILED-")


def test_inquire_algo_ccnl_returns_empty_on_server_error(monkeypatch) -> None:
    """inquire-algo-ccnl 500 응답 시 빈 리스트 반환 (예외 아님)."""
    adapter = _live_mock_adapter(monkeypatch)

    class _FakeResp:
        status_code = 500

        def raise_for_status(self):
            raise Exception("500 Internal Server Error")

        def json(self):
            return {}

    monkeypatch.setattr(adapter, "_throttle", lambda: None)
    monkeypatch.setattr(adapter, "_headers", lambda tr_id: {})
    monkeypatch.setattr(
        adapter, "_request_with_auth_retry",
        lambda method, url, **kw: _FakeResp(),
    )

    rows = adapter._inquire_algo_ccnl("4d05f83a9261")
    assert rows == []
