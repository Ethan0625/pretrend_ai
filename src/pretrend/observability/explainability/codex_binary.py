from __future__ import annotations

import os
import platform
import shutil
from collections.abc import Mapping
from pathlib import Path


def _normal_system(system: str | None = None) -> str:
    return (system or platform.system()).lower()


def _codex_names(system: str) -> tuple[str, ...]:
    if system == "windows":
        return ("codex.exe", "codex")
    return ("codex",)


def _vscode_bin_patterns(system: str) -> tuple[str, ...]:
    if system == "windows":
        return (
            "windows-x86_64/codex.exe",
            "windows-x86_64/codex.EXE",
            "win32-x64/codex.exe",
            "win32-arm64/codex.exe",
        )
    if system == "darwin":
        return ("darwin-arm64/codex", "darwin-x64/codex")
    return ("linux-x86_64/codex", "linux-x64/codex", "linux-arm64/codex")


def _vscode_extension_roots(system: str, home: Path) -> tuple[Path, ...]:
    roots = [
        home / ".vscode" / "extensions",
        home / ".vscode-insiders" / "extensions",
    ]
    if system != "windows":
        roots.insert(0, home / ".vscode-server" / "extensions")
    return tuple(roots)


def _dedupe(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def codex_bin_candidates(
    *,
    env: Mapping[str, str] | None = None,
    system: str | None = None,
    home: Path | None = None,
) -> list[Path]:
    runtime_env = os.environ if env is None else env
    current_system = _normal_system(system)
    home_dir = (home or Path.home()).expanduser()
    names = _codex_names(current_system)

    candidates: list[Path] = []
    bin_dir = str(runtime_env.get("PRETREND_CODEX_BIN_DIR", "")).strip()
    if bin_dir:
        candidates.extend(Path(bin_dir).expanduser() / name for name in names)

    if current_system != "windows":
        candidates.extend(Path("/opt/pretrend/codex-bin") / name for name in names)

    path_value = None if env is None else runtime_env.get("PATH", "")
    for name in names:
        found = shutil.which(name, path=path_value)
        if found:
            candidates.append(Path(found))

    for root in _vscode_extension_roots(current_system, home_dir):
        for pattern in _vscode_bin_patterns(current_system):
            candidates.extend(sorted(root.glob(f"openai.chatgpt-*/bin/{pattern}")))

    return _dedupe(candidates)


def resolve_codex_bin(
    explicit: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    system: str | None = None,
    home: Path | None = None,
) -> Path:
    runtime_env = os.environ if env is None else env
    explicit_value = explicit
    if explicit_value is None:
        explicit_value = str(runtime_env.get("PRETREND_CODEX_BIN", "")).strip()

    if explicit_value:
        path = Path(explicit_value).expanduser()
        if path.exists():
            return path
        raise FileNotFoundError(f"Codex binary not found: {path}")

    searched = codex_bin_candidates(env=runtime_env, system=system, home=home)
    for path in searched:
        if path.exists():
            return path

    preview = ", ".join(str(path) for path in searched[:8])
    if len(searched) > 8:
        preview += ", ..."
    searched_text = f" Searched: {preview}" if preview else ""
    raise FileNotFoundError(
        "Codex binary not found. Set PRETREND_CODEX_BIN, add codex to PATH, "
        "or mount PRETREND_CODEX_BIN_DIR into the container."
        f"{searched_text}"
    )
