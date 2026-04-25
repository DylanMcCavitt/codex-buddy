from __future__ import annotations

import copy
import json
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


MANAGED_MARKER = "CODEX_BUDDY_HOOK_MANAGED=1"


@dataclass(frozen=True)
class HookSpec:
    event: str
    matcher: Optional[str] = None
    status_message: Optional[str] = None
    timeout: Optional[int] = None


@dataclass(frozen=True)
class HookConfigResult:
    action: str
    path: Path
    command: str
    changed: bool
    installed: int
    removed: int
    dry_run: bool


class HookConfigError(ValueError):
    pass


HOOK_SPECS: Tuple[HookSpec, ...] = (
    HookSpec("SessionStart", matcher="startup|resume", status_message="Updating Codex Buddy"),
    HookSpec("UserPromptSubmit"),
    HookSpec("PreToolUse", matcher="Bash"),
    HookSpec("PermissionRequest", matcher="Bash", status_message="Updating Codex Buddy", timeout=15),
    HookSpec("PostToolUse", matcher="Bash"),
    HookSpec("Stop", timeout=5),
)


def managed_events() -> Iterable[str]:
    return (spec.event for spec in HOOK_SPECS)


def default_source_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def default_python_executable() -> str:
    system_python = Path("/usr/bin/python3")
    if system_python.exists():
        return str(system_python)
    return sys.executable


def build_hook_command(
    *,
    python: Optional[str] = None,
    source_dir: Optional[Path] = None,
) -> str:
    python_path = python or default_python_executable()
    module_root = source_dir or default_source_dir()
    return (
        f"env {MANAGED_MARKER} "
        f"PYTHONPATH={shlex.quote(str(module_root))} "
        f"{shlex.quote(python_path)} -m codex_buddy_bridge.hook"
    )


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"hooks": {}}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HookConfigError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(loaded, dict):
        raise HookConfigError(f"{path} must contain a JSON object")
    hooks = loaded.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise HookConfigError(f"{path} field 'hooks' must be a JSON object")
    return loaded


def write_config(path: Path, config: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def install_user_hooks(
    config: Mapping[str, Any],
    *,
    command: str,
) -> Tuple[Dict[str, Any], int, int]:
    updated, removed = remove_user_hooks(config)
    hooks = _hooks_object(updated)
    for spec in HOOK_SPECS:
        hooks.setdefault(spec.event, []).append(_hook_group(spec, command))
    return updated, len(HOOK_SPECS), removed


def remove_user_hooks(config: Mapping[str, Any]) -> Tuple[Dict[str, Any], int]:
    updated = copy.deepcopy(dict(config))
    hooks = _hooks_object(updated)
    removed = 0

    for event, groups in list(hooks.items()):
        if not isinstance(groups, list):
            raise HookConfigError(f"hook event {event!r} must contain a list")

        retained_groups: List[Any] = []
        for group in groups:
            if not isinstance(group, dict):
                retained_groups.append(group)
                continue

            commands = group.get("hooks")
            if not isinstance(commands, list):
                retained_groups.append(group)
                continue

            retained_commands = []
            for hook in commands:
                if _is_managed_hook(hook):
                    removed += 1
                else:
                    retained_commands.append(hook)

            if retained_commands:
                retained_group = dict(group)
                retained_group["hooks"] = retained_commands
                retained_groups.append(retained_group)

        if retained_groups:
            hooks[event] = retained_groups
        else:
            del hooks[event]

    return updated, removed


def apply_user_hooks(
    action: str,
    *,
    config_path: Optional[Path] = None,
    python: Optional[str] = None,
    source_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> HookConfigResult:
    if action not in {"install", "uninstall"}:
        raise HookConfigError(f"unsupported hooks action {action!r}")

    command = build_hook_command(python=python, source_dir=source_dir)
    path = config_path or Path.home() / ".codex" / "hooks.json"
    before = load_config(path)
    if action == "install":
        after, installed, removed = install_user_hooks(before, command=command)
    else:
        after, removed = remove_user_hooks(before)
        installed = 0

    changed = before != after
    if changed and not dry_run:
        write_config(path, after)

    return HookConfigResult(
        action=action,
        path=path,
        command=command,
        changed=changed,
        installed=installed,
        removed=removed,
        dry_run=dry_run,
    )


def _hooks_object(config: Dict[str, Any]) -> Dict[str, Any]:
    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise HookConfigError("field 'hooks' must be a JSON object")
    return hooks


def _hook_group(spec: HookSpec, command: str) -> Dict[str, Any]:
    hook: Dict[str, Any] = {
        "type": "command",
        "command": command,
    }
    if spec.status_message:
        hook["statusMessage"] = spec.status_message
    if spec.timeout is not None:
        hook["timeout"] = spec.timeout

    group: Dict[str, Any] = {"hooks": [hook]}
    if spec.matcher:
        group["matcher"] = spec.matcher
    return group


def _is_managed_hook(hook: Any) -> bool:
    if not isinstance(hook, dict):
        return False
    command = hook.get("command")
    return isinstance(command, str) and MANAGED_MARKER in command
