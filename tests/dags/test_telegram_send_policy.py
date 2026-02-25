from __future__ import annotations

from pretrend.pipeline.notify.telegram_sender import send_telegram_fail_open


class DummyLogger:
    def __init__(self) -> None:
        self.msgs = []

    def warning(self, msg, *args):
        if args:
            msg = msg % args
        self.msgs.append(msg)


def test_send_fail_open_returns_false_when_token_missing() -> None:
    logger = DummyLogger()
    ok = send_telegram_fail_open(
        token="",
        chat_id="",
        text="hello",
        source_job="paper_trading_dag",
        logger=logger,
    )
    assert ok is False
    assert any("미설정" in m for m in logger.msgs)


def test_send_fail_open_returns_false_when_send_raises(monkeypatch) -> None:
    logger = DummyLogger()

    def _raise(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(
        "pretrend.pipeline.notify.telegram_sender.send_telegram",
        _raise,
    )
    ok = send_telegram_fail_open(
        token="token",
        chat_id="chat",
        text="hello",
        source_job="paper_trading_dag",
        logger=logger,
    )
    assert ok is False
    assert any("전송 실패" in m for m in logger.msgs)
