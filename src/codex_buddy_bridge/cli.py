from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from .ble import make_publisher
from .hooks_config import HookConfigError, apply_user_hooks, default_python_executable, managed_events
from .server import BuddyDaemon, serve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-buddy", description="Codex Buddy bridge")
    sub = parser.add_subparsers(dest="command", required=True)

    bridge = sub.add_parser("bridge", help="run the repo-local status bridge")
    bridge.add_argument("--host", default="127.0.0.1", help="hook HTTP bind host")
    bridge.add_argument("--port", type=int, default=47833, help="hook HTTP bind port")
    bridge.add_argument(
        "--device-prefix",
        action="append",
        default=[],
        help="BLE device name prefix to scan for; repeatable",
    )
    bridge.add_argument("--scan-timeout", type=float, default=5.0, help="BLE scan timeout in seconds")
    bridge.add_argument(
        "--serial",
        action="store_true",
        help="use USB serial with automatic M5/ESP32 port discovery",
    )
    bridge.add_argument(
        "--serial-port",
        help="USB serial device path; implies --serial and bypasses BLE",
    )
    bridge.add_argument(
        "--dry-run",
        action="store_true",
        help="print heartbeats instead of connecting to BLE",
    )

    hooks = sub.add_parser("hooks", help="manage opt-in user-level Codex hooks")
    hook_sub = hooks.add_subparsers(dest="hooks_command", required=True)
    for action in ("install", "uninstall"):
        action_parser = hook_sub.add_parser(
            action,
            help=f"{action} Codex Buddy entries in ~/.codex/hooks.json",
        )
        action_parser.add_argument(
            "--config",
            type=Path,
            default=None,
            help="hooks.json path; defaults to ~/.codex/hooks.json",
        )
        action_parser.add_argument(
            "--dry-run",
            action="store_true",
            help="show the planned change without writing hooks.json",
        )
        if action == "install":
            action_parser.add_argument(
                "--python",
                default=default_python_executable(),
                help="Python executable used by the installed hook command",
            )
            action_parser.add_argument(
                "--source-dir",
                type=Path,
                default=None,
                help="directory added to PYTHONPATH for the hook module",
            )

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "bridge":
        prefixes = args.device_prefix or ["Claude", "Codex"]
        publisher = make_publisher(
            dry_run=args.dry_run,
            serial_port=args.serial_port,
            device_prefixes=prefixes,
            scan_timeout=args.scan_timeout,
            serial=args.serial,
        )
        daemon = BuddyDaemon(publisher)
        serve(daemon, args.host, args.port)
        return 0

    if args.command == "hooks":
        try:
            result = apply_user_hooks(
                args.hooks_command,
                config_path=args.config if args.config is not None else Path.home() / ".codex" / "hooks.json",
                python=getattr(args, "python", None),
                source_dir=getattr(args, "source_dir", None),
                dry_run=args.dry_run,
            )
        except HookConfigError as exc:
            parser.exit(2, f"codex-buddy: {exc}\n")

        _print_hook_result(result)
        return 0

    parser.error(f"unknown command {args.command}")
    return 2


def _print_hook_result(result: object) -> None:
    action = getattr(result, "action")
    dry_run = getattr(result, "dry_run")
    prefix = "Would update" if dry_run else "Updated"
    if not getattr(result, "changed"):
        prefix = "No changes needed for"

    print(f"{prefix} {getattr(result, 'path')}")
    print(f"Action: {action}")
    print("Managed events: " + ", ".join(managed_events()))
    if action == "install":
        print(f"Installed entries: {getattr(result, 'installed')}")
        print(f"Removed previous Codex Buddy entries: {getattr(result, 'removed')}")
        print(f"Hook command: {getattr(result, 'command')}")
    else:
        print(f"Removed Codex Buddy entries: {getattr(result, 'removed')}")
