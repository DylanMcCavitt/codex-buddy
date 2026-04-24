from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

from .hooks_config import default_source_dir


DEFAULT_LABEL = "com.codex-buddy.bridge"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 47833
DEFAULT_PLIST_NAME = f"{DEFAULT_LABEL}.plist"

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class LaunchAgentError(RuntimeError):
    pass


@dataclass(frozen=True)
class LaunchAgentPaths:
    plist_path: Path
    runtime_dir: Path
    log_path: Path
    error_log_path: Path


@dataclass(frozen=True)
class LaunchAgentConfig:
    label: str
    python: str
    source_dir: Optional[Path]
    host: str
    port: int
    serial_port: Optional[str]
    paths: LaunchAgentPaths


@dataclass(frozen=True)
class WriteResult:
    path: Path
    changed: bool
    dry_run: bool


def default_paths(home: Optional[Path] = None) -> LaunchAgentPaths:
    root = Path(home) if home is not None else Path.home()
    runtime_dir = root / ".codex-buddy"
    return LaunchAgentPaths(
        plist_path=root / "Library" / "LaunchAgents" / DEFAULT_PLIST_NAME,
        runtime_dir=runtime_dir,
        log_path=runtime_dir / "bridge.log",
        error_log_path=runtime_dir / "bridge.err.log",
    )


def build_config(
    *,
    label: str = DEFAULT_LABEL,
    python: Optional[str] = None,
    source_dir: Optional[Path] = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    serial_port: Optional[str] = None,
    paths: Optional[LaunchAgentPaths] = None,
) -> LaunchAgentConfig:
    return LaunchAgentConfig(
        label=label,
        python=python or sys.executable,
        source_dir=source_dir if source_dir is not None else default_source_dir(),
        host=host,
        port=port,
        serial_port=serial_port,
        paths=paths or default_paths(),
    )


def program_arguments(config: LaunchAgentConfig) -> Tuple[str, ...]:
    args = [
        config.python,
        "-m",
        "codex_buddy_bridge",
        "bridge",
        "--host",
        config.host,
        "--port",
        str(config.port),
    ]
    if config.serial_port:
        args.extend(["--serial-port", config.serial_port])
    else:
        args.append("--serial")
    return tuple(args)


def render_plist(config: LaunchAgentConfig) -> bytes:
    environment = {
        "CODEX_BUDDY_LOG_PATH": str(config.paths.log_path),
        "CODEX_BUDDY_LOG_STDOUT_ONLY": "1",
    }
    if config.source_dir is not None:
        environment["PYTHONPATH"] = str(config.source_dir)

    body = {
        "Label": config.label,
        "ProgramArguments": list(program_arguments(config)),
        "EnvironmentVariables": environment,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "StandardOutPath": str(config.paths.log_path),
        "StandardErrorPath": str(config.paths.error_log_path),
    }
    return plistlib.dumps(body, sort_keys=False)


def write_plist(config: LaunchAgentConfig, *, dry_run: bool = False) -> WriteResult:
    rendered = render_plist(config)
    existing = config.paths.plist_path.read_bytes() if config.paths.plist_path.exists() else None
    changed = existing != rendered
    if changed and not dry_run:
        config.paths.plist_path.parent.mkdir(parents=True, exist_ok=True)
        config.paths.runtime_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = config.paths.plist_path.with_name(config.paths.plist_path.name + ".tmp")
        tmp_path.write_bytes(rendered)
        tmp_path.replace(config.paths.plist_path)
    elif not dry_run:
        config.paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    return WriteResult(path=config.paths.plist_path, changed=changed, dry_run=dry_run)


def remove_plist(config: LaunchAgentConfig, *, dry_run: bool = False) -> WriteResult:
    exists = config.paths.plist_path.exists()
    if exists and not dry_run:
        config.paths.plist_path.unlink()
    return WriteResult(path=config.paths.plist_path, changed=exists, dry_run=dry_run)


def user_domain(uid: Optional[int] = None) -> str:
    return f"gui/{os.getuid() if uid is None else uid}"


def service_target(label: str = DEFAULT_LABEL, *, uid: Optional[int] = None) -> str:
    return f"{user_domain(uid)}/{label}"


def bootstrap_command(config: LaunchAgentConfig, *, uid: Optional[int] = None) -> Tuple[str, ...]:
    return ("launchctl", "bootstrap", user_domain(uid), str(config.paths.plist_path))


def bootout_command(config: LaunchAgentConfig, *, uid: Optional[int] = None) -> Tuple[str, ...]:
    return ("launchctl", "bootout", service_target(config.label, uid=uid))


def kickstart_command(config: LaunchAgentConfig, *, uid: Optional[int] = None) -> Tuple[str, ...]:
    return ("launchctl", "kickstart", "-k", service_target(config.label, uid=uid))


def print_command(config: LaunchAgentConfig, *, uid: Optional[int] = None) -> Tuple[str, ...]:
    return ("launchctl", "print", service_target(config.label, uid=uid))


def run_launchctl(
    command: Sequence[str],
    *,
    runner: Optional[Runner] = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    run = runner or _default_runner
    completed = run(tuple(command))
    if check and completed.returncode != 0:
        raise LaunchAgentError(_format_launchctl_error(command, completed))
    return completed


def bootout(config: LaunchAgentConfig, *, runner: Optional[Runner] = None, missing_ok: bool = False) -> None:
    completed = run_launchctl(bootout_command(config), runner=runner, check=False)
    if completed.returncode == 0:
        return
    if missing_ok and _looks_like_missing_service(completed):
        return
    raise LaunchAgentError(_format_launchctl_error(bootout_command(config), completed))


def bootstrap(
    config: LaunchAgentConfig,
    *,
    runner: Optional[Runner] = None,
    attempts: int = 1,
    delay: float = 0.5,
) -> None:
    command = bootstrap_command(config)
    last_result: Optional[subprocess.CompletedProcess[str]] = None
    for attempt in range(max(1, attempts)):
        completed = run_launchctl(command, runner=runner, check=False)
        if completed.returncode == 0:
            return
        last_result = completed
        if attempt + 1 < max(1, attempts):
            time.sleep(delay)

    assert last_result is not None
    raise LaunchAgentError(_format_launchctl_error(command, last_result))


def kickstart(config: LaunchAgentConfig, *, runner: Optional[Runner] = None) -> None:
    run_launchctl(kickstart_command(config), runner=runner)


def _default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _format_launchctl_error(
    command: Sequence[str],
    completed: subprocess.CompletedProcess[str],
) -> str:
    detail = (completed.stderr or completed.stdout or "").strip()
    suffix = f": {detail}" if detail else ""
    return f"{' '.join(command)} failed with exit code {completed.returncode}{suffix}"


def _looks_like_missing_service(completed: subprocess.CompletedProcess[str]) -> bool:
    text = f"{completed.stderr}\n{completed.stdout}".lower()
    return any(
        marker in text
        for marker in (
            "could not find service",
            "no such process",
            "service is not loaded",
            "not found",
        )
    )
