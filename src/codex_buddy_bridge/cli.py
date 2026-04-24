from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from .ble import make_publisher
from .hooks_config import HookConfigError, apply_user_hooks, default_python_executable, managed_events
from .launch_agent import (
    LaunchAgentError,
    LaunchAgentPaths,
    bootout,
    bootstrap,
    build_config,
    default_paths,
    kickstart,
    print_command,
    remove_plist,
    run_launchctl,
    write_plist,
)
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

    launch_agent = sub.add_parser("launch-agent", help="manage the opt-in user LaunchAgent")
    launch_sub = launch_agent.add_subparsers(dest="launch_agent_command", required=True)
    for action in ("install", "start", "stop", "restart", "status", "uninstall"):
        action_parser = launch_sub.add_parser(action, help=f"{action} the Codex Buddy LaunchAgent")
        action_parser.add_argument(
            "--plist",
            type=Path,
            default=None,
            help="LaunchAgent plist path; defaults to ~/Library/LaunchAgents/com.codex-buddy.bridge.plist",
        )
        if action in {"install", "uninstall"}:
            action_parser.add_argument(
                "--dry-run",
                action="store_true",
                help="show the planned change without writing files or calling launchctl",
            )
        if action == "install":
            action_parser.add_argument(
                "--python",
                default=None,
                help="Python executable used by launchd; defaults to the current Python",
            )
            action_parser.add_argument(
                "--source-dir",
                type=Path,
                default=None,
                help="directory added to PYTHONPATH for the bridge module",
            )
            action_parser.add_argument("--host", default="127.0.0.1", help="hook HTTP bind host")
            action_parser.add_argument("--port", type=int, default=47833, help="hook HTTP bind port")
            action_parser.add_argument(
                "--serial-port",
                default=None,
                help="force a USB serial device path instead of auto-discovery",
            )
            action_parser.add_argument(
                "--no-start",
                action="store_true",
                help="write the plist without bootstrapping the LaunchAgent",
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

    if args.command == "launch-agent":
        try:
            return _handle_launch_agent(args)
        except LaunchAgentError as exc:
            parser.exit(2, f"codex-buddy: {exc}\n")

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


def _handle_launch_agent(args: argparse.Namespace) -> int:
    paths = _launch_agent_paths(args.plist)
    config = build_config(
        python=getattr(args, "python", None),
        source_dir=getattr(args, "source_dir", None),
        host=getattr(args, "host", "127.0.0.1"),
        port=getattr(args, "port", 47833),
        serial_port=getattr(args, "serial_port", None),
        paths=paths,
    )

    action = args.launch_agent_command
    if action == "install":
        result = write_plist(config, dry_run=args.dry_run)
        _print_launch_agent_write("Would install" if args.dry_run else "Installed", result, config)
        if args.dry_run or args.no_start:
            return 0
        bootout(config, missing_ok=True)
        bootstrap(config, attempts=5)
        print(f"Loaded LaunchAgent: {config.label}")
        return 0

    if action == "start":
        if not config.paths.plist_path.exists():
            raise LaunchAgentError(f"{config.paths.plist_path} does not exist; run launch-agent install first")
        try:
            bootstrap(config)
            print(f"Loaded LaunchAgent: {config.label}")
        except LaunchAgentError:
            kickstart(config)
            print(f"Restarted loaded LaunchAgent: {config.label}")
        return 0

    if action == "stop":
        bootout(config, missing_ok=True)
        print(f"Stopped LaunchAgent: {config.label}")
        return 0

    if action == "restart":
        bootout(config, missing_ok=True)
        bootstrap(config, attempts=5)
        print(f"Restarted LaunchAgent: {config.label}")
        return 0

    if action == "status":
        completed = run_launchctl(print_command(config), check=False)
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            import sys

            print(completed.stderr, end="", file=sys.stderr)
        return completed.returncode

    if action == "uninstall":
        if not args.dry_run:
            bootout(config, missing_ok=True)
        result = remove_plist(config, dry_run=args.dry_run)
        _print_launch_agent_write("Would uninstall" if args.dry_run else "Uninstalled", result, config)
        return 0

    raise LaunchAgentError(f"unsupported launch-agent action {action!r}")


def _launch_agent_paths(plist_path: Optional[Path]) -> LaunchAgentPaths:
    paths = default_paths()
    if plist_path is None:
        return paths
    return LaunchAgentPaths(
        plist_path=plist_path,
        runtime_dir=paths.runtime_dir,
        log_path=paths.log_path,
        error_log_path=paths.error_log_path,
    )


def _print_launch_agent_write(prefix: str, result: object, config: object) -> None:
    changed = "changed" if getattr(result, "changed") else "already current"
    print(f"{prefix} {getattr(result, 'path')} ({changed})")
    print(f"Label: {getattr(config, 'label')}")
    print(f"Log: {getattr(getattr(config, 'paths'), 'log_path')}")
