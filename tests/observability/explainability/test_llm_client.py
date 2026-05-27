from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from pretrend.observability.explainability.llm_client import (
    LLMCallError,
    VSCodeCodexProvider,
    get_provider,
)


def test_get_provider_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PRETREND_LLM_PROVIDER", raising=False)
    assert isinstance(get_provider(), VSCodeCodexProvider)


def test_get_provider_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRETREND_LLM_PROVIDER", "vscode_codex")
    assert isinstance(get_provider(), VSCodeCodexProvider)


def test_get_provider_rejects_unknown() -> None:
    with pytest.raises(LLMCallError):
        get_provider("other")


def test_vscode_codex_health_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    if os.name == "nt":
        codex = tmp_path / "codex.cmd"
        codex.write_text("@echo off\r\nexit /b 0\r\n")
    else:
        codex = tmp_path / "codex"
        codex.write_text("#!/bin/sh\nexit 0\n")
        codex.chmod(0o755)
    provider = VSCodeCodexProvider(codex)

    assert provider.health_check()


def test_vscode_codex_call_uses_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\nexit 0\n")
    provider = VSCodeCodexProvider(codex)

    def fake_run(cmd, **kwargs):
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text('{"ok": true}')
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert provider.call("system", "user", max_tokens=10, temperature=0.1, timeout_s=1) == '{"ok": true}'
