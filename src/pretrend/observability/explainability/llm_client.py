from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Protocol

from pretrend.observability.explainability.codex_binary import resolve_codex_bin


FORBIDDEN_TERMS = (
    "predicted_",
    "forecast_",
    "recommend_",
    "should_buy_",
    "target_price",
    "target_return",
    "buy_signal",
    "sell_signal",
    "trading_signal",
)


class InvariantViolationError(ValueError):
    pass


class LLMCallError(RuntimeError):
    pass


class LLMProvider(Protocol):
    model_id: str

    def health_check(self, *, timeout_s: int = 10) -> bool:
        ...

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        timeout_s: int,
    ) -> str:
        ...


def check_invariant_or_raise(text: str) -> None:
    lowered = text.lower()
    for term in FORBIDDEN_TERMS:
        if term.lower() in lowered:
            raise InvariantViolationError(f"forbidden explainability term: {term}")


def check_report_invariant_or_raise(report_json: dict) -> None:
    check_invariant_or_raise(json.dumps(report_json, ensure_ascii=False, sort_keys=True))


class VSCodeCodexProvider:
    model_id = "vscode_codex"

    def __init__(self, codex_bin: str | Path | None = None) -> None:
        self.codex_bin = Path(codex_bin) if codex_bin is not None else None

    def health_check(self, *, timeout_s: int = 10) -> bool:
        try:
            codex_bin = self._resolve_codex_bin()
            result = subprocess.run(
                [str(codex_bin), "--help"],
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            return result.returncode == 0
        except Exception:
            return False

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        timeout_s: int,
    ) -> str:
        prompt = (
            f"{system_prompt}\n\n"
            f"{user_prompt}\n\n"
            f"max_tokens={max_tokens}; temperature={temperature}"
        )
        last_error: Exception | None = None
        for delay in [0, 1, 2, 4]:
            if delay:
                time.sleep(delay)
            try:
                return self._call_once(prompt, timeout_s=timeout_s)
            except Exception as exc:
                last_error = exc
        raise LLMCallError(str(last_error) if last_error else "LLM call failed")

    def _call_once(self, prompt: str, *, timeout_s: int) -> str:
        codex_bin = self._resolve_codex_bin()
        project_dir = Path.cwd()
        with tempfile.NamedTemporaryFile(prefix="p27-explain-", suffix=".txt", delete=False) as tmp:
            output_path = Path(tmp.name)
        try:
            result = subprocess.run(
                [
                    str(codex_bin),
                    "exec",
                    "--full-auto",
                    "-C",
                    str(project_dir),
                    "--output-last-message",
                    str(output_path),
                    prompt,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(project_dir),
                timeout=timeout_s,
            )
            response = (
                output_path.read_text(encoding="utf-8", errors="replace").strip()
                if output_path.exists()
                else ""
            )
            if result.returncode != 0:
                raise LLMCallError(result.stderr.strip() or result.stdout.strip() or "codex failed")
            return response or result.stdout.strip()
        finally:
            output_path.unlink(missing_ok=True)

    def _resolve_codex_bin(self) -> Path:
        try:
            return resolve_codex_bin(self.codex_bin)
        except FileNotFoundError as exc:
            raise LLMCallError(str(exc)) from exc


def get_provider(name: str | None = None) -> LLMProvider:
    provider_name = name or os.getenv("PRETREND_LLM_PROVIDER", "vscode_codex")
    if provider_name == "vscode_codex":
        return VSCodeCodexProvider()
    raise LLMCallError(f"unsupported LLM provider: {provider_name}")
