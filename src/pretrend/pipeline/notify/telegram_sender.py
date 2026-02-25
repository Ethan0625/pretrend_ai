"""Telegram sender utilities with fail-open behavior."""
from __future__ import annotations

import logging
from typing import Optional

import requests


def send_telegram(token: str, chat_id: str, text: str, timeout: int = 10) -> None:
    """Send a Telegram message via Bot API."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=timeout,
    )
    resp.raise_for_status()


def send_telegram_fail_open(
    token: str,
    chat_id: str,
    text: str,
    *,
    source_job: str,
    timeout: int = 10,
    logger: Optional[logging.Logger] = None,
) -> bool:
    """Try sending Telegram and swallow errors (fail-open).

    Returns True when sent, False when skipped/failed.
    """
    log = logger or logging.getLogger(__name__)
    if not token or not chat_id:
        log.warning("[%s] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정 — 알림 스킵", source_job)
        return False

    try:
        send_telegram(token=token, chat_id=chat_id, text=text, timeout=timeout)
        return True
    except Exception as exc:  # pragma: no cover - exercised via unit tests
        log.warning("[%s] Telegram 전송 실패(fail-open): %s", source_job, exc)
        return False
