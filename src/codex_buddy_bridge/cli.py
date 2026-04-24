from __future__ import annotations

import argparse
from typing import Optional, Sequence

from .ble import make_publisher
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
        "--serial-port",
        help="USB serial device path; bypasses BLE and writes heartbeat JSON over serial",
    )
    bridge.add_argument(
        "--dry-run",
        action="store_true",
        help="print heartbeats instead of connecting to BLE",
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
        )
        daemon = BuddyDaemon(publisher)
        serve(daemon, args.host, args.port)
        return 0

    parser.error(f"unknown command {args.command}")
    return 2
