"""Korea Investment mock-trading adapter.

This adapter supports two modes:
- dry-run(default): no outbound order call; deterministic mock response
- live-mock: calls KIS mock API endpoints using OAuth token
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
import time
import uuid
from typing import Any, Dict, List, Optional

import requests

from .base import BrokerAdapter, BrokerBalance, BrokerPosition, OrderResult
from .kis_config import KISConfig


@dataclass
class _TokenState:
    access_token: Optional[str] = None
    expires_at_epoch: float = 0.0


class KISMockAdapter(BrokerAdapter):
    """KIS mock broker adapter (overseas stock focused)."""

    def __init__(self, config: KISConfig):
        self.config = config
        self._token = _TokenState()
        self._session = requests.Session()
        self._token_refresh_count: int = 0
        self._last_refresh_at: Optional[datetime] = None
        self._last_auth_error_code: Optional[int] = None
        self._cod_symbol_map: Optional[Dict[str, Dict[str, str]]] = None
        self._request_delay_sec: float = float(os.getenv("KIS_REQUEST_DELAY_SEC", "0.5"))

    @classmethod
    def from_env(cls) -> "KISMockAdapter":
        return cls(KISConfig.from_env())

    def _throttle(self) -> None:
        # Gate D: rate-limit safe default
        time.sleep(max(0.0, self._request_delay_sec))

    def _load_cod_symbol_map(self) -> Dict[str, Dict[str, str]]:
        if self._cod_symbol_map is not None:
            return self._cod_symbol_map
        out: Dict[str, Dict[str, str]] = {}
        cod_root = os.getenv("KIS_COD_ROOT", "data/reference/kis_cod")
        try:
            from pathlib import Path

            root = Path(cod_root)
            for fp in sorted(root.glob("*.COD")):
                for line in fp.read_text(encoding="cp949", errors="ignore").splitlines():
                    cols = line.split("\t")
                    if len(cols) != 24:
                        continue
                    symb = str(cols[4]).strip().upper()
                    rsym = str(cols[5]).strip().upper()
                    excd = str(cols[2]).strip().upper()
                    if not symb or not excd:
                        continue
                    out[symb] = {"symb": symb, "rsym": rsym, "excd": excd}
        except Exception:
            out = {}
        self._cod_symbol_map = out
        return out

    def _resolve_symbol_market(self, symbol: str) -> Dict[str, str]:
        symb = str(symbol).strip().upper()
        m = self._load_cod_symbol_map().get(symb, {})
        excd = str(m.get("excd", "NAS")).upper()
        rsym = str(m.get("rsym", symb)).upper()
        ovrs_excg = {"NAS": "NASD", "NYS": "NYSE", "AMS": "AMEX"}.get(excd, "NASD")
        return {"symb": symb, "rsym": rsym, "excd": excd, "ovrs_excg_cd": ovrs_excg}

    @staticmethod
    def _format_order_price(price: float) -> str:
        """Normalize order price string for psamount query."""
        s = f"{float(price):.4f}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s

    def _ensure_token(self) -> str:
        if self.config.dry_run:
            return "DRY_RUN_TOKEN"
        now = time.time()
        # token is effectively refreshed every 55 minutes (3300s) for 1h expiry.
        if self._token.access_token and now < self._token.expires_at_epoch - 300:
            return self._token.access_token
        url = f"{self.config.base_url}/oauth2/tokenP"
        resp = self._session.post(
            url,
            json={
                "grant_type": "client_credentials",
                "appkey": self.config.app_key,
                "appsecret": self.config.app_secret,
            },
            timeout=self.config.timeout_sec,
        )
        resp.raise_for_status()
        body = resp.json()
        token = str(body.get("access_token", ""))
        if not token:
            raise RuntimeError("KIS token issuance failed: empty token")
        expires_in = int(body.get("expires_in", 3600))
        self._token = _TokenState(access_token=token, expires_at_epoch=now + expires_in)
        self._token_refresh_count += 1
        self._last_refresh_at = datetime.now(timezone.utc)
        self._last_auth_error_code = None
        return token

    def _headers(self, tr_id: str) -> Dict[str, str]:
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._ensure_token()}",
            "appKey": self.config.app_key,
            "appSecret": self.config.app_secret,
            "tr_id": tr_id,
        }

    @staticmethod
    def _raise_if_kis_error(body: Any, context: str) -> None:
        if not isinstance(body, dict):
            return
        rt_cd = str(body.get("rt_cd", "")).strip()
        if rt_cd and rt_cd != "0":
            msg_cd = str(body.get("msg_cd", "")).strip()
            msg1 = str(body.get("msg1", "")).strip()
            raise RuntimeError(f"KIS {context} failed: rt_cd={rt_cd}, msg_cd={msg_cd}, msg1={msg1}")

    def auth_status(self) -> Dict[str, Any]:
        return {
            "token_refresh_count": self._token_refresh_count,
            "last_refresh_at": self._last_refresh_at.isoformat() if self._last_refresh_at else None,
            "auth_status": "FAILED" if self._last_auth_error_code else "OK",
            "error_code": self._last_auth_error_code,
        }

    def _request_with_auth_retry(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        """Retry once after token refresh on 401/403."""
        resp = self._session.request(method, url, **kwargs)
        if resp.status_code in {401, 403} and not self.config.dry_run:
            self._last_auth_error_code = resp.status_code
            # force refresh
            self._token = _TokenState()
            hdr = kwargs.get("headers", {})
            tr_id = hdr.get("tr_id", "")
            kwargs["headers"] = self._headers(tr_id)
            resp = self._session.request(method, url, **kwargs)
        return resp

    @staticmethod
    def _to_float_safe(v: Any) -> Optional[float]:
        if v is None:
            return None
        s = str(v).strip().replace(",", "")
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None

    @classmethod
    def _extract_fx_usdkrw(cls, body: Any) -> Optional[float]:
        """Extract USD/KRW fx from KIS response payload when present."""
        candidates: List[float] = []

        def _walk(obj: Any) -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    lk = str(k).lower()
                    if "exrt" in lk or "excg_rt" in lk or "exchange_rate" in lk:
                        fv = cls._to_float_safe(v)
                        if fv is not None and fv > 0:
                            candidates.append(fv)
                    _walk(v)
            elif isinstance(obj, list):
                for x in obj:
                    _walk(x)

        _walk(body)
        if not candidates:
            return None
        # Prefer realistic KRW per USD range first.
        realistic = [x for x in candidates if 800 <= x <= 2500]
        if realistic:
            return realistic[0]
        return candidates[0]

    @staticmethod
    def _pick_amount(d: Dict[str, Any], keys: List[str]) -> Optional[float]:
        for k in keys:
            if k in d:
                v = KISMockAdapter._to_float_safe(d.get(k))
                if v is not None:
                    return v
        return None

    def get_balance(self) -> BrokerBalance:
        if self.config.dry_run:
            return BrokerBalance(cash=100_000.0, total_value=100_000.0, currency="KRW", fx_usdkrw=1300.0)
        self._throttle()
        # KIS reference(v1_해외주식-008): VTRP6504R + WCRC/NATN/TR_MKET/INQR params.
        url = f"{self.config.base_url}/uapi/overseas-stock/v1/trading/inquire-present-balance"
        headers = self._headers("VTRP6504R" if self.config.is_mock else "CTRP6504R")
        resp = self._request_with_auth_retry(
            "GET",
            url,
            headers=headers,
            params={
                "CANO": self.config.account_no,
                "ACNT_PRDT_CD": self.config.product_code,
                "WCRC_FRCR_DVSN_CD": "02",
                "NATN_CD": "000",
                "TR_MKET_CD": "00",
                "INQR_DVSN_CD": "00",
            },
            timeout=self.config.timeout_sec,
        )
        resp.raise_for_status()
        body = resp.json()
        self._raise_if_kis_error(body, "inquire-present-balance")
        output2_raw = body.get("output2", {}) if isinstance(body, dict) else {}
        output3_raw = body.get("output3", {}) if isinstance(body, dict) else {}
        if isinstance(output2_raw, list):
            output2_first = output2_raw[0] if output2_raw and isinstance(output2_raw[0], dict) else {}
        elif isinstance(output2_raw, dict):
            output2_first = output2_raw
        else:
            output2_first = {}
        if isinstance(output3_raw, list):
            output3 = output3_raw[0] if output3_raw and isinstance(output3_raw[0], dict) else {}
        elif isinstance(output3_raw, dict):
            output3 = output3_raw
        else:
            output3 = {}

        # Present-balance summary is output3 in KIS examples; prefer it.
        cash = self._pick_amount(
            output3,
            [
                "frcr_use_psbl_amt",
                "dncl_amt",
                "tot_dncl_amt",
            ],
        )
        total = self._pick_amount(
            output3,
            [
                "tot_asst_amt",
                "tot_asst_amt2",
                "frcr_evlu_tota",
                "tot_evlu_pfls_amt",
            ],
        )
        if cash is None:
            # fallback from currency rows
            if isinstance(output2_raw, list):
                cash = 0.0
                for row in output2_raw:
                    if not isinstance(row, dict):
                        continue
                    v = self._to_float_safe(row.get("frcr_dncl_amt_2"))
                    if v is not None:
                        cash += float(v)
            else:
                cash = self._pick_amount(
                    output2_first,
                    ["frcr_dncl_amt_2", "frcr_dncl_amt1"],
                )
        if cash is None:
            cash = 0.0
        if total is None:
            total = cash
        fx = self._extract_fx_usdkrw(body)
        return BrokerBalance(cash=cash, total_value=total, currency="KRW", fx_usdkrw=fx)

    def get_foreign_cash_balances(self) -> List[Dict[str, Any]]:
        """Return per-currency foreign cash rows from present-balance output3 when available."""
        if self.config.dry_run:
            return [{"currency": "USD", "amount": 100_000.0}]
        self._throttle()
        url = f"{self.config.base_url}/uapi/overseas-stock/v1/trading/inquire-present-balance"
        headers = self._headers("VTRP6504R" if self.config.is_mock else "CTRP6504R")
        resp = self._request_with_auth_retry(
            "GET",
            url,
            headers=headers,
            params={
                "CANO": self.config.account_no,
                "ACNT_PRDT_CD": self.config.product_code,
                "WCRC_FRCR_DVSN_CD": "02",
                "NATN_CD": "000",
                "TR_MKET_CD": "00",
                "INQR_DVSN_CD": "00",
            },
            timeout=self.config.timeout_sec,
        )
        resp.raise_for_status()
        body = resp.json()
        self._raise_if_kis_error(body, "inquire-present-balance")
        rows_raw = body.get("output2", []) if isinstance(body, dict) else []
        if isinstance(rows_raw, list):
            rows = rows_raw
        elif isinstance(rows_raw, dict):
            rows = [rows_raw]
        else:
            rows = []
        out: List[Dict[str, Any]] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            ccy = str(r.get("crcy_cd") or r.get("tr_crcy_cd") or r.get("frcr_crcy_cd") or "").strip().upper()
            amt = self._to_float_safe(
                r.get("frcr_dncl_amt_2")
                or r.get("frcr_dncl_amt1")
                or r.get("frcr_drwg_psbl_amt_1")
                or r.get("frcr_use_psbl_amt")
            )
            if not ccy and amt is None:
                continue
            amount = 0.0 if amt is None else float(amt)
            # suppress meaningless placeholder rows
            if (not ccy or ccy == "UNKNOWN") and amount == 0.0:
                continue
            out.append({"currency": ccy or "UNKNOWN", "amount": amount, "raw": r})
        return out

    def get_positions(self) -> List[BrokerPosition]:
        if self.config.dry_run:
            return []
        self._throttle()
        url = f"{self.config.base_url}/uapi/overseas-stock/v1/trading/inquire-balance"
        headers = self._headers("VTTS3012R")
        resp = self._request_with_auth_retry(
            "GET",
            url,
            headers=headers,
            params={
                "CANO": self.config.account_no,
                "ACNT_PRDT_CD": self.config.product_code,
                "OVRS_EXCG_CD": "NASD",
                "TR_CRCY_CD": "USD",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            },
            timeout=self.config.timeout_sec,
        )
        resp.raise_for_status()
        body = resp.json()
        self._raise_if_kis_error(body, "inquire-balance")
        rows = body.get("output1", []) if isinstance(body, dict) else []
        out: List[BrokerPosition] = []
        for r in rows:
            out.append(
                BrokerPosition(
                    symbol=str(r.get("ovrs_pdno", "")),
                    quantity=float(r.get("ovrs_cblc_qty", 0.0)),
                    avg_price=float(r.get("pchs_avg_pric", 0.0)),
                    market_price=float(r.get("now_pric", 0.0)),
                    market_value=float(r.get("ovrs_stck_evlu_amt", 0.0)),
                )
            )
        return out

    def get_current_price(self, symbol: str) -> float:
        if self.config.dry_run:
            return 0.0
        self._throttle()
        url = f"{self.config.base_url}/uapi/overseas-price/v1/quotations/price"
        headers = self._headers("HHDFS00000300")
        m = self._resolve_symbol_market(symbol)
        try:
            # Mock mode: keep a single execution-price query path to reduce API load.
            resp = self._request_with_auth_retry(
                "GET",
                url,
                headers=headers,
                params={"AUTH": "", "EXCD": m["excd"], "SYMB": m["symb"]},
                timeout=self.config.timeout_sec,
            )
            resp.raise_for_status()
            body = resp.json()
            self._raise_if_kis_error(body, "quotations/price")
            out = body.get("output", {}) if isinstance(body, dict) else {}
            if isinstance(out, list):
                out = out[0] if out and isinstance(out[0], dict) else {}
            if not isinstance(out, dict):
                return 0.0
            for field in ["last", "ovrs_nmix_prpr", "stck_prpr", "clos"]:
                val = self._to_float_safe(out.get(field))
                if val is not None and val > 0:
                    return float(val)
        except Exception:
            return 0.0
        return 0.0

    def get_usdkrw_rate(self) -> Optional[float]:
        """Fetch USD/KRW from a dedicated FX-oriented probe, then fallback to balance payload."""
        if self.config.dry_run:
            return 1300.0
        self._throttle()
        probes = [
            {
                "url": f"{self.config.base_url}/uapi/overseas-stock/v1/trading/inquire-exchange-rate",
                "tr_id": "VTTS3012R",
                "params": {
                    "CANO": self.config.account_no,
                    "ACNT_PRDT_CD": self.config.product_code,
                    "OVRS_EXCG_CD": "NASD",
                    "WCRC_FRCR_DVSN_CD": "02",
                    "NATN_CD": "840",
                    "TR_MKET_CD": "NASD",
                    "INQR_DVSN_CD": "00",
                },
            },
            {
                "url": f"{self.config.base_url}/uapi/overseas-stock/v1/trading/inquire-present-balance",
                "tr_id": "VTRP6504R" if self.config.is_mock else "CTRP6504R",
                "params": {
                    "CANO": self.config.account_no,
                    "ACNT_PRDT_CD": self.config.product_code,
                    "WCRC_FRCR_DVSN_CD": "02",
                    "NATN_CD": "000",
                    "TR_MKET_CD": "00",
                    "INQR_DVSN_CD": "00",
                },
            },
        ]
        for spec in probes:
            try:
                resp = self._request_with_auth_retry(
                    "GET",
                    spec["url"],
                    headers=self._headers(spec["tr_id"]),
                    params=spec["params"],
                    timeout=self.config.timeout_sec,
                )
                if resp.status_code >= 400:
                    continue
                fx = self._extract_fx_usdkrw(resp.json())
                if fx and fx > 0:
                    return fx
            except Exception:
                continue
        return None

    def get_orderable_cash_usd(
        self,
        symbol: str,
        *,
        exchange_code: str = "NASD",
        order_price: Optional[float] = None,
    ) -> Optional[float]:
        """Query KIS inquire-psamount(v1_해외주식-014) and return foreign-currency orderable amount."""
        info = self.get_orderable_info(
            symbol,
            exchange_code=exchange_code,
            order_price=order_price,
        )
        for key in ["ord_psbl_frcr_amt", "frcr_ord_psbl_amt1"]:
            val = self._to_float_safe(info.get(key))
            if val is not None:
                return float(val)
        return None

    def get_orderable_info(
        self,
        symbol: str,
        *,
        exchange_code: str = "NASD",
        order_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Return parsed inquire-psamount output for a symbol."""
        if self.config.dry_run:
            return {
                "tr_crcy_cd": "USD",
                "ord_psbl_frcr_amt": 100000.0,
                "ovrs_ord_psbl_amt": None,
                "exrt": None,
                "ovrs_excg_cd": exchange_code,
                "symbol": symbol,
            }
        self._throttle()
        px = order_price
        if px is None or px <= 0:
            try:
                px = self.get_current_price(symbol)
            except Exception:
                px = 0.0
        if px is None or px <= 0:
            return {
                "symbol": str(symbol).upper(),
                "error": "ORDERABLE_PRICE_UNAVAILABLE",
                "order_price": 0.0,
            }
        order_price_str = self._format_order_price(px)
        url = f"{self.config.base_url}/uapi/overseas-stock/v1/trading/inquire-psamount"
        tr_id = "VTTS3007R" if self.config.is_mock else "TTTS3007R"
        m = self._resolve_symbol_market(symbol)
        exchanges: List[str] = [m["ovrs_excg_cd"]]

        last_error: Dict[str, Any] = {}
        # inquire-psamount expects item code as symbol (e.g., SPY/QQQ),
        # while rsym(AMSSPY/NASQQQ) may cause INPUT_FIELD_SIZE errors in VTS.
        item_codes: List[str] = [str(m["symb"]).strip().upper()]

        debug_attempts: List[Dict[str, Any]] = []
        for ex in exchanges:
            for item_cd in item_codes:
                try:
                    resp = self._request_with_auth_retry(
                        "GET",
                        url,
                        headers=self._headers(tr_id),
                        params={
                            "CANO": self.config.account_no,
                            "ACNT_PRDT_CD": self.config.product_code,
                            "OVRS_EXCG_CD": ex,
                            "OVRS_ORD_UNPR": order_price_str,
                            "ITEM_CD": item_cd,
                        },
                        timeout=self.config.timeout_sec,
                    )
                    body = {}
                    try:
                        body = resp.json()
                    except Exception:
                        body = {}
                    debug_attempts.append(
                        {
                            "ovrs_excg_cd": ex,
                            "item_cd": item_cd,
                            "status_code": resp.status_code,
                            "rt_cd": body.get("rt_cd") if isinstance(body, dict) else None,
                            "msg_cd": body.get("msg_cd") if isinstance(body, dict) else None,
                            "msg1": body.get("msg1") if isinstance(body, dict) else None,
                        }
                    )
                    if resp.status_code >= 500:
                        last_error = {
                            "status_code": resp.status_code,
                            "ovrs_excg_cd": ex,
                            "item_cd": item_cd,
                            "symbol": str(symbol).upper(),
                        }
                        continue
                    resp.raise_for_status()
                    rt_cd = str(body.get("rt_cd", "")).strip() if isinstance(body, dict) else ""
                    if rt_cd and rt_cd != "0":
                        last_error = {
                            "status_code": resp.status_code,
                            "rt_cd": rt_cd,
                            "msg_cd": body.get("msg_cd") if isinstance(body, dict) else None,
                            "msg1": body.get("msg1") if isinstance(body, dict) else None,
                            "ovrs_excg_cd": ex,
                            "item_cd": item_cd,
                            "symbol": str(symbol).upper(),
                        }
                        continue
                    out = body.get("output", {}) if isinstance(body, dict) else {}
                    if isinstance(out, list):
                        out = out[0] if out and isinstance(out[0], dict) else {}
                    if not isinstance(out, dict):
                        last_error = {
                            "status_code": resp.status_code,
                            "rt_cd": rt_cd or None,
                            "msg_cd": body.get("msg_cd") if isinstance(body, dict) else None,
                            "msg1": body.get("msg1") if isinstance(body, dict) else None,
                            "ovrs_excg_cd": ex,
                            "item_cd": item_cd,
                            "symbol": str(symbol).upper(),
                        }
                        continue
                    info: Dict[str, Any] = {
                        "symbol": str(symbol).upper(),
                        "ovrs_excg_cd": ex,
                        "order_price": float(px),
                        "order_price_param": order_price_str,
                        "tr_crcy_cd": str(out.get("tr_crcy_cd", "")).upper() or "USD",
                        "ord_psbl_frcr_amt": self._to_float_safe(out.get("ord_psbl_frcr_amt")),
                        "frcr_ord_psbl_amt1": self._to_float_safe(out.get("frcr_ord_psbl_amt1")),
                        "ovrs_ord_psbl_amt": self._to_float_safe(out.get("ovrs_ord_psbl_amt")),
                        "ord_psbl_amt": self._to_float_safe(out.get("ord_psbl_amt")),
                        "exrt": self._to_float_safe(out.get("exrt")),
                        "max_ord_psbl_qty": self._to_float_safe(out.get("max_ord_psbl_qty")),
                        "ord_psbl_qty": self._to_float_safe(out.get("ord_psbl_qty")),
                        "raw": out,
                    }
                    # return when at least one numeric orderable field exists
                    if any(info.get(k) is not None for k in ["ord_psbl_frcr_amt", "frcr_ord_psbl_amt1", "ovrs_ord_psbl_amt", "ord_psbl_amt"]):
                        return info
                except Exception:
                    last_error = {
                        "ovrs_excg_cd": ex,
                        "item_cd": item_cd,
                        "symbol": str(symbol).upper(),
                        "exception": "request_failed",
                    }
                    continue
        return {
            "symbol": str(symbol).upper(),
            "ovrs_excg_cd": exchanges[0] if exchanges else exchange_code,
            "error": "ORDERABLE_INFO_UNAVAILABLE",
            "attempted_exchanges": exchanges,
            "attempted_item_cd": item_codes,
            "order_price": float(px),
            "order_price_param": order_price_str,
            "debug_attempts": debug_attempts,
            **last_error,
        }

    def debug_inquire_psamount(
        self,
        symbol: str,
        *,
        exchange_code: str = "NASD",
        order_price: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Return all psamount attempt responses for debugging."""
        info = self.get_orderable_info(
            symbol,
            exchange_code=exchange_code,
            order_price=order_price,
        )
        rows = info.get("debug_attempts")
        return rows if isinstance(rows, list) else []

    def _place_order(self, side: str, symbol: str, qty: int, order_type: str = "MARKET") -> OrderResult:
        now = datetime.now(timezone.utc)
        if self.config.dry_run:
            return OrderResult(
                order_id=f"DRY-{uuid.uuid4().hex[:12]}",
                symbol=symbol,
                side=side,
                quantity=float(qty),
                requested_price=None,
                filled_price=None,
                status="FILLED",
                executed_at=now,
                raw={"mode": "dry_run", "order_type": order_type},
            )

        self._throttle()
        tr_id = "VTTT1002U" if side == "BUY" else "VTTT1001U"
        url = f"{self.config.base_url}/uapi/overseas-stock/v1/trading/order"
        payload = {
            "CANO": self.config.account_no,
            "ACNT_PRDT_CD": self.config.product_code,
            "OVRS_EXCG_CD": "NASD",
            "PDNO": symbol,
            "ORD_DVSN": "00" if order_type.upper() == "MARKET" else "01",
            "ORD_QTY": str(int(qty)),
            "OVRS_ORD_UNPR": "0" if order_type.upper() == "MARKET" else "",
            "ORD_SVR_DVSN_CD": "0",
        }
        headers = self._headers(tr_id)
        resp = self._request_with_auth_retry(
            "POST",
            url,
            headers=headers,
            json=payload,
            timeout=self.config.timeout_sec,
        )
        resp.raise_for_status()
        body = resp.json()
        output = body.get("output", {}) if isinstance(body, dict) else {}
        order_no = str(output.get("ODNO", "") or output.get("odno", "") or uuid.uuid4().hex[:12])
        status = "ACCEPTED" if order_no else "FAILED"
        return OrderResult(
            order_id=order_no,
            symbol=symbol,
            side=side,
            quantity=float(qty),
            requested_price=None,
            filled_price=None,
            status=status,
            executed_at=now,
            raw=body if isinstance(body, dict) else {"raw": str(body)},
        )

    def place_buy_order(self, symbol: str, qty: int, order_type: str = "MARKET") -> OrderResult:
        return self._place_order("BUY", symbol, qty, order_type)

    def place_sell_order(self, symbol: str, qty: int, order_type: str = "MARKET") -> OrderResult:
        return self._place_order("SELL", symbol, qty, order_type)

    def get_order_status(self, order_id: str) -> str:
        # For now, dry-run returns FILLED immediately. Live path can be expanded.
        if self.config.dry_run:
            return "FILLED"
        return "ACCEPTED"
