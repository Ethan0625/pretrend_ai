"""KIS broker configuration helpers."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Tuple


def _pick_credentials(is_mock: bool) -> Tuple[str, str, str, str, str]:
    """Return (app_key, app_secret, account_no, product_code, base_url)."""
    if is_mock:
        app_key = os.getenv("KIS_MOCK_APP_KEY", "").strip()
        app_secret = os.getenv("KIS_MOCK_APP_SECRET", "").strip()
        account_no = os.getenv("KIS_MOCK_ACCOUNT_NO", "").strip()
        product_code = os.getenv("KIS_MOCK_PRODUCT_CODE", "").strip() or "01"
        base_url = os.getenv("KIS_MOCK_BASE_URL", "").strip()
    else:
        app_key = os.getenv("KIS_LIVE_APP_KEY", "").strip()
        app_secret = os.getenv("KIS_LIVE_APP_SECRET", "").strip()
        account_no = os.getenv("KIS_LIVE_ACCOUNT_NO", "").strip()
        product_code = os.getenv("KIS_LIVE_PRODUCT_CODE", "").strip() or "01"
        base_url = os.getenv("KIS_LIVE_BASE_URL", "").strip()

    # backward compatibility with legacy env names
    if not app_key:
        app_key = os.getenv("KIS_APP_KEY", "").strip()
    if not app_secret:
        app_secret = os.getenv("KIS_APP_SECRET", "").strip()
    if not account_no:
        account_no = os.getenv("KIS_ACCOUNT_NO", "").strip()
    if not product_code:
        product_code = os.getenv("KIS_PRODUCT_CODE", "").strip() or "01"
    if not base_url:
        base_url = os.getenv("KIS_BASE_URL", "").strip()
    return app_key, app_secret, account_no, product_code, base_url


@dataclass(frozen=True)
class KISConfig:
    app_key: str
    app_secret: str
    account_no: str
    product_code: str
    is_mock: bool
    base_url: str
    ws_url: str
    dry_run: bool
    timeout_sec: int

    @classmethod
    def from_env(cls) -> "KISConfig":
        is_mock = os.getenv("KIS_IS_MOCK", "true").strip().lower() in {"1", "true", "yes"}
        default_base = "https://openapivts.koreainvestment.com:29443" if is_mock else "https://openapi.koreainvestment.com:9443"
        default_ws = "ws://ops.koreainvestment.com:21000"
        app_key, app_secret, account_no, product_code, base_url = _pick_credentials(is_mock)

        # strict by default: selected mode credentials must exist.
        missing = []
        if not app_key:
            missing.append("app_key")
        if not app_secret:
            missing.append("app_secret")
        if not account_no:
            missing.append("account_no")
        if missing:
            mode = "mock" if is_mock else "live"
            raise ValueError(f"KIS {mode} credentials missing: {', '.join(missing)}")

        return cls(
            app_key=app_key,
            app_secret=app_secret,
            account_no=account_no,
            product_code=product_code or "01",
            is_mock=is_mock,
            base_url=base_url or default_base,
            ws_url=os.getenv("KIS_WS_URL", default_ws),
            dry_run=os.getenv("KIS_DRY_RUN", "true").strip().lower() in {"1", "true", "yes"},
            timeout_sec=int(os.getenv("KIS_TIMEOUT_SEC", "10")),
        )
