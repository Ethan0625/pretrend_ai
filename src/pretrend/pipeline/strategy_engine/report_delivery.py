from __future__ import annotations

from typing import List


REPORT_SINGLE_MESSAGE_LIMIT = 3000


def compose_strategy_report_messages(
    main_lines: List[str],
    support_lines: List[str],
) -> List[str]:
    """Compose 1 or 2 logical Telegram messages for the strategy report."""
    main_text = "\n".join([line for line in main_lines if line is not None]).strip()
    support_text = "\n".join([line for line in support_lines if line is not None]).strip()
    if not support_text:
        return [main_text] if main_text else []

    full_text = "\n".join([part for part in [main_text, support_text] if part]).strip()
    if len(full_text) <= REPORT_SINGLE_MESSAGE_LIMIT:
        return [full_text]
    return [part for part in [main_text, support_text] if part]
