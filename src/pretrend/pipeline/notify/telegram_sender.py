"""Telegram sender utilities with fail-open behavior."""
from __future__ import annotations

import logging
from typing import List, Optional

import requests


_TELEGRAM_TEXT_LIMIT = 3500


def _split_telegram_text(text: str, max_chars: int = _TELEGRAM_TEXT_LIMIT) -> List[str]:
    """Split message into Telegram-safe chunks.

    Telegram sendMessage limit is 4096 chars. We keep a safety margin and split by line.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for line in text.splitlines():
        line_len = len(line) + 1  # keep newline
        if line_len > max_chars:
            if current:
                chunks.append("\n".join(current).strip())
                current = []
                current_len = 0
            # hard-wrap exceptionally long line
            start = 0
            while start < len(line):
                chunks.append(line[start:start + max_chars])
                start += max_chars
            continue

        if current_len + line_len > max_chars and current:
            chunks.append("\n".join(current).strip())
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len

    if current:
        chunks.append("\n".join(current).strip())

    return [c for c in chunks if c]


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

    chunks = _split_telegram_text(text)
    if len(chunks) > 1:
        log.info("[%s] Telegram message chunking applied: %d chunks", source_job, len(chunks))

    try:
        for idx, chunk in enumerate(chunks, start=1):
            send_telegram(token=token, chat_id=chat_id, text=chunk, timeout=timeout)
            if idx < len(chunks):
                log.info("[%s] Telegram chunk %d/%d sent", source_job, idx, len(chunks))
        return True
    except Exception as exc:  # pragma: no cover - exercised via unit tests
        log.warning("[%s] Telegram 전송 실패(fail-open): %s", source_job, exc)
        return False
