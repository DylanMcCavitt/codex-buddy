from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence


NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
LOG_PATH = Path.home() / ".codex-buddy" / "bridge.log"


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


class Publisher:
    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def publish(self, payload: Dict[str, object]) -> None:
        raise NotImplementedError


class DryRunPublisher(Publisher):
    def start(self) -> None:
        log("[codex-buddy] dry-run publisher active")

    def stop(self) -> None:
        pass

    def publish(self, payload: Dict[str, object]) -> None:
        log("[codex-buddy] heartbeat " + json.dumps(payload, separators=(",", ":")))


class BlePublisher(Publisher):
    def __init__(
        self,
        device_prefixes: Sequence[str],
        scan_timeout: float = 5.0,
        reconnect_delay: float = 2.0,
    ) -> None:
        self.device_prefixes = tuple(device_prefixes)
        self.scan_timeout = scan_timeout
        self.reconnect_delay = reconnect_delay
        self._queue: "queue.Queue[None]" = queue.Queue()
        self._latest: Optional[Dict[str, object]] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._thread_main, name="codex-buddy-ble", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=3)

    def publish(self, payload: Dict[str, object]) -> None:
        with self._lock:
            self._latest = dict(payload)
        self._queue.put(None)

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:  # pragma: no cover - safety net for background thread
            print(f"[codex-buddy] BLE worker stopped: {exc}")

    async def _run(self) -> None:
        try:
            from bleak import BleakClient, BleakScanner
        except ImportError:
            log("[codex-buddy] bleak is not installed. Install with: python3 -m pip install -e '.[ble]'")
            return

        while not self._stop.is_set():
            device = await self._find_device(BleakScanner)
            if device is None:
                await self._sleep(self.reconnect_delay)
                continue

            name = getattr(device, "name", None) or getattr(device, "address", "unknown")
            log(f"[codex-buddy] connecting to {name}")
            try:
                async with BleakClient(device) as client:
                    log(f"[codex-buddy] connected to {name}")
                    await self._send_latest(client)
                    while client.is_connected and not self._stop.is_set():
                        await asyncio.to_thread(self._queue.get)
                        await self._send_latest(client)
            except Exception as exc:
                log(f"[codex-buddy] BLE connection failed: {exc}")
                await self._sleep(self.reconnect_delay)

    async def _find_device(self, scanner_cls: object):
        log(
            "[codex-buddy] scanning for "
            + ", ".join(f"{prefix}*" for prefix in self.device_prefixes)
        )
        try:
            devices = await scanner_cls.discover(timeout=self.scan_timeout, service_uuids=[NUS_SERVICE_UUID])
        except TypeError:
            devices = await scanner_cls.discover(timeout=self.scan_timeout)
        except Exception as exc:
            log(f"[codex-buddy] BLE scan failed: {exc}")
            return None
        log(
            "[codex-buddy] BLE scan saw "
            + str(len(devices))
            + " device(s): "
            + ", ".join(repr(getattr(device, "name", "") or "") for device in devices[:12])
        )
        for device in devices:
            name = getattr(device, "name", "") or ""
            if any(name.startswith(prefix) for prefix in self.device_prefixes):
                return device
        log("[codex-buddy] no matching buddy found")
        return None

    async def _send_latest(self, client: object) -> None:
        with self._lock:
            payload = dict(self._latest) if self._latest else None
        if payload is None:
            return
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        await client.write_gatt_char(NUS_RX_UUID, data, response=False)
        log("[codex-buddy] sent heartbeat to BLE")

    async def _sleep(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while not self._stop.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(0.1)


def make_publisher(
    dry_run: bool,
    serial_port: Optional[str],
    device_prefixes: Iterable[str],
    scan_timeout: float,
) -> Publisher:
    if serial_port:
        return SerialPublisher(serial_port)
    prefixes = tuple(device_prefixes)
    if dry_run:
        return DryRunPublisher()
    return BlePublisher(prefixes, scan_timeout=scan_timeout)


class SerialPublisher(Publisher):
    def __init__(self, port: str, baudrate: int = 115200) -> None:
        self.port = port
        self.baudrate = baudrate
        self._serial = None
        self._lock = threading.Lock()

    def start(self) -> None:
        try:
            import serial
        except ImportError:
            log("[codex-buddy] pyserial is not installed. Install with: python3 -m pip install pyserial")
            return

        with self._lock:
            if self._serial is not None:
                return
            try:
                self._serial = serial.Serial(self.port, self.baudrate, timeout=0.1, write_timeout=1)
                self._serial.dtr = False
                self._serial.rts = False
                time.sleep(0.2)
                log(f"[codex-buddy] serial connected to {self.port} @ {self.baudrate}")
            except Exception as exc:
                self._serial = None
                log(f"[codex-buddy] serial open failed: {exc}")

    def stop(self) -> None:
        with self._lock:
            if self._serial is not None:
                try:
                    self._serial.close()
                finally:
                    self._serial = None

    def publish(self, payload: Dict[str, object]) -> None:
        with self._lock:
            if self._serial is None:
                log("[codex-buddy] serial not connected; heartbeat dropped")
                return
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
            try:
                self._serial.write(data)
                self._serial.flush()
                log("[codex-buddy] sent heartbeat to serial")
            except Exception as exc:
                log(f"[codex-buddy] serial write failed: {exc}")
                try:
                    self._serial.close()
                finally:
                    self._serial = None
