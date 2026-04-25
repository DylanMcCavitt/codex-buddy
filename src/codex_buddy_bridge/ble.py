from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from .device_input import DeviceInputMonitor


NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
DEFAULT_LOG_PATH = Path.home() / ".codex-buddy" / "bridge.log"
KNOWN_USB_SERIAL_VIDS = {0x0403, 0x10C4, 0x1A86, 0x2341, 0x239A, 0x303A}
USB_SERIAL_DEVICE_PARTS = (
    "usbserial",
    "usbmodem",
    "wchusbserial",
    "slab_usbtouart",
    "ttyusb",
    "ttyacm",
)
USB_SERIAL_TEXT_PARTS = (
    "m5stack",
    "m5stick",
    "esp32",
    "esp32-s",
    "cp210",
    "silicon labs",
    "ch340",
    "ch910",
    "ftdi",
    "usb serial",
    "usb-serial",
    "usb to uart",
    "usb-to-uart",
    "wch",
    "uart",
)


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    if os.environ.get("CODEX_BUDDY_LOG_STDOUT_ONLY") == "1":
        return
    try:
        log_path = Path(os.environ.get("CODEX_BUDDY_LOG_PATH", str(DEFAULT_LOG_PATH))).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def likely_serial_ports(port_infos: Iterable[object]) -> List[str]:
    ranked: List[tuple[int, int, str]] = []
    for port_info in port_infos:
        device = _port_device(port_info)
        if not device:
            continue
        score = serial_port_score(port_info)
        if score <= 0:
            continue
        ranked.append((score, _device_preference(device), device))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [device for _, _, device in ranked]


def choose_serial_port(port_infos: Iterable[object]) -> Optional[str]:
    ports = likely_serial_ports(port_infos)
    if not ports:
        return None
    return ports[0]


def serial_port_score(port_info: object) -> int:
    device = _port_device(port_info)
    if not device:
        return 0

    text = _port_search_text(port_info)
    if "bluetooth" in text:
        return 0

    device_lower = device.lower()
    has_usb_serial_device = any(part in device_lower for part in USB_SERIAL_DEVICE_PARTS)
    has_usb_serial_text = any(part in text for part in USB_SERIAL_TEXT_PARTS)
    vid = getattr(port_info, "vid", None)
    has_known_usb_vid = isinstance(vid, int) and vid in KNOWN_USB_SERIAL_VIDS
    if not (has_usb_serial_device or has_usb_serial_text or has_known_usb_vid):
        return 0

    score = 0
    if has_usb_serial_device:
        score += 6
    if has_usb_serial_text:
        score += 5
    if has_known_usb_vid:
        score += 4
    if device.startswith("/dev/cu."):
        score += 1
    return score


def _port_device(port_info: object) -> str:
    value = getattr(port_info, "device", None)
    if value is None:
        return ""
    return str(value)


def _port_search_text(port_info: object) -> str:
    values = [
        _port_device(port_info),
        getattr(port_info, "description", ""),
        getattr(port_info, "manufacturer", ""),
        getattr(port_info, "product", ""),
        getattr(port_info, "hwid", ""),
    ]
    return " ".join(str(value) for value in values if value).lower()


def _device_preference(device: str) -> int:
    if device.startswith("/dev/cu."):
        return 0
    return 1


class Publisher:
    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def publish(self, payload: Dict[str, object]) -> None:
        raise NotImplementedError

    def diagnostics(self) -> Dict[str, object]:
        return {}


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
        self._device_input = DeviceInputMonitor(logger=log)
        self._connection_state = "disconnected"
        self._last_publish_time: Optional[str] = None
        self._last_ble_error: Optional[str] = None
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

    def diagnostics(self) -> Dict[str, object]:
        with self._lock:
            return {
                "transport": "ble",
                "connection_state": self._connection_state,
                "last_publish_time": self._last_publish_time,
                "last_ble_error": self._last_ble_error,
                "device_input": self._device_input.diagnostics(),
            }

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
            with self._lock:
                self._connection_state = "scanning"
            device = await self._find_device(BleakScanner)
            if device is None:
                with self._lock:
                    self._connection_state = "disconnected"
                await self._sleep(self.reconnect_delay)
                continue

            name = getattr(device, "name", None) or getattr(device, "address", "unknown")
            log(f"[codex-buddy] connecting to {name}")
            try:
                with self._lock:
                    self._connection_state = "connecting"
                async with BleakClient(device) as client:
                    with self._lock:
                        self._connection_state = "connected"
                        self._last_ble_error = None
                    log(f"[codex-buddy] connected to {name}")
                    await self._start_notifications(client)
                    await self._send_latest(client)
                    while client.is_connected and not self._stop.is_set():
                        await asyncio.to_thread(self._queue.get)
                        await self._send_latest(client)
            except Exception as exc:
                with self._lock:
                    self._connection_state = "disconnected"
                    self._last_ble_error = str(exc)
                log(f"[codex-buddy] BLE connection failed: {exc}")
                await self._sleep(self.reconnect_delay)
            else:
                with self._lock:
                    self._connection_state = "disconnected"

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
        with self._lock:
            self._last_publish_time = datetime.now().isoformat(timespec="seconds")
            self._last_ble_error = None
        log("[codex-buddy] sent heartbeat to BLE")

    async def _start_notifications(self, client: object) -> None:
        start_notify = getattr(client, "start_notify", None)
        if not callable(start_notify):
            return
        try:
            await start_notify(NUS_TX_UUID, self._handle_tx_notification)
            log("[codex-buddy] subscribed to BLE device input")
        except Exception as exc:
            log(f"[codex-buddy] BLE input subscription failed: {exc}")

    def _handle_tx_notification(self, sender: object, data: object) -> None:
        if isinstance(data, bytearray):
            raw = bytes(data)
        elif isinstance(data, bytes):
            raw = data
        elif isinstance(data, memoryview):
            raw = data.tobytes()
        else:
            return
        self._device_input.feed_bytes(raw)

    async def _sleep(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while not self._stop.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(0.1)


def make_publisher(
    dry_run: bool,
    serial_port: Optional[str],
    device_prefixes: Iterable[str],
    scan_timeout: float,
    serial: bool = False,
) -> Publisher:
    if serial or serial_port:
        return SerialPublisher(port=serial_port)
    prefixes = tuple(device_prefixes)
    if dry_run:
        return DryRunPublisher()
    return BlePublisher(prefixes, scan_timeout=scan_timeout)


class SerialPublisher(Publisher):
    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 115200,
        reconnect_delay: float = 2.0,
        settle_delay: float = 0.2,
        serial_module: Optional[object] = None,
        ports_provider: Optional[Callable[[], Sequence[object]]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.requested_port = port
        self.baudrate = baudrate
        self.reconnect_delay = reconnect_delay
        self.settle_delay = settle_delay
        self._serial_module = serial_module
        self._ports_provider = ports_provider
        self._clock = clock
        self._serial = None
        self._selected_port: Optional[str] = port
        self._connection_state = "disconnected"
        self._last_publish_time: Optional[str] = None
        self._last_serial_error: Optional[str] = None
        self._next_connect_attempt = 0.0
        self._reader_stop = threading.Event()
        self._reader_thread: Optional[threading.Thread] = None
        self._reader_serial = None
        self._io_lock = threading.Lock()
        self._device_input = DeviceInputMonitor(logger=log)
        self._lock = threading.Lock()

    def start(self) -> None:
        mode = self.requested_port or "auto-discovery"
        self._reader_stop.clear()
        log(f"[codex-buddy] serial publisher active ({mode})")

    def stop(self) -> None:
        self._reader_stop.set()
        with self._lock:
            if self._serial is not None:
                try:
                    self._serial.close()
                finally:
                    self._serial = None
            self._connection_state = "disconnected"
        if self._reader_thread:
            self._reader_thread.join(timeout=1)
            self._reader_thread = None

    def publish(self, payload: Dict[str, object]) -> None:
        with self._lock:
            if not self._ensure_connected_locked():
                return
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
            try:
                with self._io_lock:
                    self._serial.write(data)
                    self._serial.flush()
                self._connection_state = "connected"
                self._last_publish_time = datetime.now().isoformat(timespec="seconds")
                self._last_serial_error = None
                log("[codex-buddy] sent heartbeat to serial")
            except Exception as exc:
                self._record_disconnect_locked(f"serial write failed: {exc}")
                try:
                    self._serial.close()
                finally:
                    self._serial = None

    def diagnostics(self) -> Dict[str, object]:
        with self._lock:
            return {
                "transport": "serial",
                "requested_port": self.requested_port,
                "selected_port": self._selected_port,
                "connection_state": self._connection_state,
                "last_publish_time": self._last_publish_time,
                "last_serial_error": self._last_serial_error,
                "device_input": self._device_input.diagnostics(),
            }

    def _ensure_connected_locked(self) -> bool:
        if self._serial is not None:
            return True
        if self._clock() < self._next_connect_attempt:
            return False
        return self._connect_locked()

    def _connect_locked(self) -> bool:
        serial_module = self._load_serial_module_locked()
        if serial_module is None:
            return False

        port = self.requested_port or self._discover_port_locked()
        if port is None:
            self._record_disconnect_locked("no likely M5/ESP32 USB serial port found")
            return False

        self._selected_port = port
        try:
            self._serial = serial_module.Serial(port, self.baudrate, timeout=0.1, write_timeout=1)
            self._serial.dtr = False
            self._serial.rts = False
            if self.settle_delay > 0:
                time.sleep(self.settle_delay)
            self._connection_state = "connected"
            self._last_serial_error = None
            self._start_reader_locked(self._serial)
            log(f"[codex-buddy] serial connected to {port} @ {self.baudrate}")
            return True
        except Exception as exc:
            self._serial = None
            self._record_disconnect_locked(f"serial open failed for {port}: {exc}")
            return False

    def _load_serial_module_locked(self) -> Optional[object]:
        if self._serial_module is not None:
            return self._serial_module
        try:
            import serial
        except ImportError:
            self._record_disconnect_locked("pyserial is not installed. Install with: python3 -m pip install -e .")
            return None
        self._serial_module = serial
        return self._serial_module

    def _discover_port_locked(self) -> Optional[str]:
        try:
            if self._ports_provider is not None:
                ports = list(self._ports_provider())
            else:
                from serial.tools import list_ports

                ports = list(list_ports.comports())
        except Exception as exc:
            self._record_disconnect_locked(f"serial port discovery failed: {exc}")
            return None
        port = choose_serial_port(ports)
        self._selected_port = port
        return port

    def _record_disconnect_locked(self, message: str) -> None:
        self._connection_state = "disconnected"
        if self.requested_port is None:
            self._selected_port = None
        self._last_serial_error = message
        self._next_connect_attempt = self._clock() + self.reconnect_delay
        log(f"[codex-buddy] {message}")

    def _start_reader_locked(self, serial_device: object) -> None:
        if self._reader_thread and self._reader_thread.is_alive() and self._reader_serial is serial_device:
            return
        self._reader_serial = serial_device
        thread = threading.Thread(
            target=self._reader_loop,
            args=(serial_device,),
            name="codex-buddy-serial-reader",
            daemon=True,
        )
        self._reader_thread = thread
        thread.start()

    def _reader_loop(self, serial_device: object) -> None:
        while not self._reader_stop.is_set():
            with self._lock:
                if self._serial is not serial_device:
                    return
            try:
                with self._io_lock:
                    line = serial_device.readline()
            except AttributeError:
                return
            except Exception as exc:
                with self._lock:
                    if self._serial is serial_device:
                        self._record_disconnect_locked(f"serial read failed: {exc}")
                        try:
                            serial_device.close()
                        finally:
                            self._serial = None
                return
            if line:
                self._device_input.feed_line(bytes(line))
