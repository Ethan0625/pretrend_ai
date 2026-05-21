from __future__ import annotations

import pytest

from pretrend.observability.explainability.codex_binary import resolve_codex_bin
from pretrend.observability.explainability.legacy_report.context import (
    _build_compact_llm_input,
    _env_bool,
    _env_clean,
    _env_float,
    _env_int,
)
from pretrend.observability.explainability.legacy_report import analyzer


def test_report_llm_env_helpers_strip_inline_comments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPORT_LLM_PROVIDER", "gemini          # gemini | ollama")
    monkeypatch.setenv("REPORT_LLM_FALLBACK_ENABLED", "1       # fallback enabled")
    monkeypatch.setenv("REPORT_LLM_RETRY", "3                  # retry count")
    monkeypatch.setenv("REPORT_LLM_TEMPERATURE", "0.4          # sampling")

    assert _env_clean("REPORT_LLM_PROVIDER", "ollama") == "gemini"
    assert _env_bool("REPORT_LLM_FALLBACK_ENABLED", "0") is True
    assert _env_int("REPORT_LLM_RETRY", 1) == 3
    assert _env_float("REPORT_LLM_TEMPERATURE", 0.1) == 0.4


def test_report_llm_env_helpers_fall_back_on_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPORT_LLM_RETRY", "not-an-int")
    monkeypatch.setenv("REPORT_LLM_TEMPERATURE", "not-a-float")

    assert _env_int("REPORT_LLM_RETRY", 3) == 3
    assert _env_float("REPORT_LLM_TEMPERATURE", 0.4) == 0.4


def test_report_analyzer_can_run_stateless_without_bot_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, *, cwd, timeout):
        calls.append(cmd)
        return _Result(), "codex analysis"

    monkeypatch.setattr(analyzer, "_BOT_AVAILABLE", False)
    monkeypatch.setattr(analyzer, "_require_codex_bin", lambda: "/opt/codex/codex")
    monkeypatch.setattr(analyzer, "_run_codex_output_command", _fake_run)

    result = analyzer.generate_report_via_analyzer(
        system_prompt="system",
        user_content="payload",
        timeout=10,
    )

    assert result == "codex analysis"
    assert calls
    assert calls[0][:2] == ["/opt/codex/codex", "exec"]


def test_codex_bin_resolver_uses_configured_bin_dir(tmp_path) -> None:
    bin_dir = tmp_path / "codex-bin"
    bin_dir.mkdir()
    codex = bin_dir / "codex"
    codex.write_text("#!/bin/sh\n", encoding="utf-8")

    resolved = resolve_codex_bin(
        env={"PRETREND_CODEX_BIN_DIR": str(bin_dir), "PATH": ""},
        system="Linux",
        home=tmp_path,
    )

    assert resolved == codex


def test_codex_bin_resolver_uses_os_specific_vscode_path(tmp_path) -> None:
    codex_dir = (
        tmp_path
        / ".vscode"
        / "extensions"
        / "openai.chatgpt-1.2.3"
        / "bin"
        / "windows-x86_64"
    )
    codex_dir.mkdir(parents=True)
    codex = codex_dir / "codex.exe"
    codex.write_text("", encoding="utf-8")

    resolved = resolve_codex_bin(env={"PATH": ""}, system="Windows", home=tmp_path)

    assert resolved == codex


def test_codex_bin_resolver_does_not_pick_linux_bin_on_windows(tmp_path) -> None:
    bin_dir = tmp_path / "codex-bin"
    bin_dir.mkdir()
    (bin_dir / "codex").write_text("#!/bin/sh\n", encoding="utf-8")

    codex_dir = (
        tmp_path
        / ".vscode"
        / "extensions"
        / "openai.chatgpt-1.2.3"
        / "bin"
        / "windows-x86_64"
    )
    codex_dir.mkdir(parents=True)
    codex = codex_dir / "codex.exe"
    codex.write_text("", encoding="utf-8")

    resolved = resolve_codex_bin(
        env={"PRETREND_CODEX_BIN_DIR": str(bin_dir), "PATH": ""},
        system="Windows",
        home=tmp_path,
    )

    assert resolved == codex


def test_codex_bin_resolver_keeps_explicit_path_strict(tmp_path) -> None:
    missing = tmp_path / "missing-codex"

    with pytest.raises(FileNotFoundError, match="Codex binary not found"):
        resolve_codex_bin(explicit=missing, env={"PATH": ""}, system="Linux", home=tmp_path)


def test_compact_llm_input_tolerates_missing_relative_strength() -> None:
    """OFS-004: relative_strength unavailable 상태는 compact report 입력에서 N/A로 표현된다."""
    compact = _build_compact_llm_input(
        {
            "tactical_etf": {
                "SECTOR": [
                    {"name_ko": "Energy", "symbol": "XLE", "rs": None},
                    {"name_ko": "Tech", "symbol": "XLK", "rs": 0.125},
                    {"name_ko": "Utility", "symbol": "XLU", "rs": float("inf")},
                ],
            },
        }
    )

    entries = next(iter(compact["relative_strength"].values()))
    assert "Energy N/A" in entries
    assert "Utility N/A" in entries
    assert any("Tech +12.5%" in entry for entry in entries)
    assert compact["rs_assets_top5"] == [
        {
            "name_ko": "Tech",
            "symbol": "XLK",
            "rs": "+12.5%",
            "group": next(iter(compact["relative_strength"].keys())),
        }
    ]
