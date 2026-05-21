from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import urllib.request
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


def explainability_timeout_s(default: int = 180) -> int:
    raw = os.getenv("PRETREND_EXPLAINABILITY_TIMEOUT", "").strip()
    if not raw:
        return default
    try:
        return max(int(raw), 30)
    except ValueError:
        return default


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
                    "--skip-git-repo-check",
                    *self._sandbox_args(),
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

    def _sandbox_args(self) -> list[str]:
        bypass = os.getenv("PRETREND_CODEX_BYPASS_SANDBOX", "").strip().lower()
        if bypass in {"1", "true", "yes"}:
            return ["--dangerously-bypass-approvals-and-sandbox"]
        mode = os.getenv("PRETREND_CODEX_SANDBOX", "workspace-write").strip() or "workspace-write"
        return ["--sandbox", mode]


class ApiCodexProvider:
    """Proxy Codex generation through the FastAPI report analyzer endpoint."""

    model_id = "vscode_codex"

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        health_url: str | None = None,
    ) -> None:
        self.api_url = (
            api_url
            or os.getenv("PRETREND_EXPLAINABILITY_ANALYZER_API_URL")
            or "http://api:8000/api/v1/report/explainability/analyze"
        )
        self.api_key = api_key if api_key is not None else os.getenv("PRETREND_API_KEY", "")
        self.health_url = (
            health_url
            or os.getenv("PRETREND_EXPLAINABILITY_ANALYZER_HEALTH_URL")
            or "http://api:8000/health"
        )

    def health_check(self, *, timeout_s: int = 10) -> bool:
        if not self.api_url or not self.api_key:
            return False
        try:
            with urllib.request.urlopen(self.health_url, timeout=timeout_s) as response:
                return 200 <= response.status < 500
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
        body = json.dumps(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "timeout": timeout_s,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            self.api_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": self.api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout_s + 5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        raw_text = str(payload.get("raw_text") or "").strip()
        if not raw_text:
            raise LLMCallError("empty explainability analyzer response")
        return raw_text


def get_provider(name: str | None = None) -> LLMProvider:
    provider_name = name or os.getenv("PRETREND_LLM_PROVIDER", "vscode_codex")
    if provider_name == "vscode_codex":
        return VSCodeCodexProvider()
    if provider_name in {"api_vscode_codex", "report_api_vscode_codex"}:
        return ApiCodexProvider()
    raise LLMCallError(f"unsupported LLM provider: {provider_name}")
