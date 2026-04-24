import unittest

from codex_buddy_bridge.ble import SerialPublisher, choose_serial_port, likely_serial_ports


class FakePort:
    def __init__(
        self,
        device,
        description="",
        manufacturer="",
        product="",
        hwid="",
        vid=None,
    ):
        self.device = device
        self.description = description
        self.manufacturer = manufacturer
        self.product = product
        self.hwid = hwid
        self.vid = vid


class FakeSerialDevice:
    def __init__(self, fail_writes=False):
        self.fail_writes = fail_writes
        self.closed = False
        self.writes = []
        self.dtr = True
        self.rts = True

    def write(self, data):
        if self.fail_writes:
            raise OSError("device unplugged")
        self.writes.append(data)

    def flush(self):
        pass

    def close(self):
        self.closed = True


class FakeSerialModule:
    def __init__(self, fail_writes=None):
        self.fail_writes = list(fail_writes or [])
        self.instances = []

    def Serial(self, port, baudrate, timeout, write_timeout):
        fail_writes = self.fail_writes.pop(0) if self.fail_writes else False
        device = FakeSerialDevice(fail_writes=fail_writes)
        self.instances.append(
            {
                "port": port,
                "baudrate": baudrate,
                "timeout": timeout,
                "write_timeout": write_timeout,
                "device": device,
            }
        )
        return device


class SerialPortSelectionTests(unittest.TestCase):
    def test_choose_serial_port_prefers_likely_m5_esp32_devices(self):
        ports = [
            FakePort("/dev/cu.Bluetooth-Incoming-Port", description="Bluetooth"),
            FakePort(
                "/dev/tty.usbserial-7552A41038",
                description="CP2102 USB to UART Bridge Controller",
                manufacturer="Silicon Labs",
                vid=0x10C4,
            ),
            FakePort(
                "/dev/cu.usbserial-7552A41038",
                description="CP2102 USB to UART Bridge Controller",
                manufacturer="Silicon Labs",
                vid=0x10C4,
            ),
        ]

        self.assertEqual(choose_serial_port(ports), "/dev/cu.usbserial-7552A41038")
        self.assertEqual(
            likely_serial_ports(ports),
            ["/dev/cu.usbserial-7552A41038", "/dev/tty.usbserial-7552A41038"],
        )

    def test_choose_serial_port_returns_none_without_likely_match(self):
        ports = [
            FakePort("/dev/cu.Audioengine2"),
            FakePort("/dev/cu.Bluetooth-Incoming-Port", description="Bluetooth"),
            FakePort("/dev/cu.debug-console"),
        ]

        self.assertIsNone(choose_serial_port(ports))


class SerialPublisherTests(unittest.TestCase):
    def test_unplugged_startup_does_not_raise_and_reports_diagnostics(self):
        publisher = SerialPublisher(
            serial_module=FakeSerialModule(),
            ports_provider=lambda: [],
            reconnect_delay=0,
            settle_delay=0,
        )

        publisher.start()
        publisher.publish({"msg": "idle"})

        diagnostics = publisher.diagnostics()
        self.assertEqual(diagnostics["transport"], "serial")
        self.assertEqual(diagnostics["connection_state"], "disconnected")
        self.assertIsNone(diagnostics["selected_port"])
        self.assertIn("no likely M5/ESP32", diagnostics["last_serial_error"])

    def test_auto_discovery_reconnects_when_device_appears(self):
        ports = []
        serial_module = FakeSerialModule()
        publisher = SerialPublisher(
            serial_module=serial_module,
            ports_provider=lambda: ports,
            reconnect_delay=0,
            settle_delay=0,
        )

        publisher.publish({"msg": "idle"})
        ports.append(
            FakePort(
                "/dev/cu.usbserial-7552A41038",
                description="CP2102 USB to UART Bridge Controller",
                manufacturer="Silicon Labs",
                vid=0x10C4,
            )
        )
        publisher.publish({"msg": "working"})

        self.assertEqual(serial_module.instances[0]["port"], "/dev/cu.usbserial-7552A41038")
        self.assertEqual(serial_module.instances[0]["device"].writes, [b'{"msg":"working"}\n'])
        diagnostics = publisher.diagnostics()
        self.assertEqual(diagnostics["connection_state"], "connected")
        self.assertEqual(diagnostics["selected_port"], "/dev/cu.usbserial-7552A41038")
        self.assertIsNotNone(diagnostics["last_publish_time"])
        self.assertIsNone(diagnostics["last_serial_error"])

    def test_write_failure_disconnects_and_next_publish_reopens(self):
        ports = [
            FakePort(
                "/dev/cu.usbserial-7552A41038",
                description="CP2102 USB to UART Bridge Controller",
                manufacturer="Silicon Labs",
                vid=0x10C4,
            )
        ]
        serial_module = FakeSerialModule(fail_writes=[True, False])
        publisher = SerialPublisher(
            serial_module=serial_module,
            ports_provider=lambda: ports,
            reconnect_delay=0,
            settle_delay=0,
        )

        publisher.publish({"msg": "first"})
        self.assertTrue(serial_module.instances[0]["device"].closed)
        self.assertEqual(publisher.diagnostics()["connection_state"], "disconnected")
        self.assertIsNone(publisher.diagnostics()["selected_port"])
        self.assertIn("serial write failed", publisher.diagnostics()["last_serial_error"])

        publisher.publish({"msg": "second"})

        self.assertEqual(len(serial_module.instances), 2)
        self.assertEqual(serial_module.instances[1]["device"].writes, [b'{"msg":"second"}\n'])
        self.assertEqual(publisher.diagnostics()["connection_state"], "connected")

    def test_write_failure_then_missing_device_reports_latest_discovery_error(self):
        ports = [
            FakePort(
                "/dev/cu.usbserial-7552A41038",
                description="CP2102 USB to UART Bridge Controller",
                manufacturer="Silicon Labs",
                vid=0x10C4,
            )
        ]
        serial_module = FakeSerialModule(fail_writes=[True])
        publisher = SerialPublisher(
            serial_module=serial_module,
            ports_provider=lambda: ports,
            reconnect_delay=0,
            settle_delay=0,
        )

        publisher.publish({"msg": "first"})
        ports.clear()
        publisher.publish({"msg": "retry"})

        diagnostics = publisher.diagnostics()
        self.assertEqual(diagnostics["connection_state"], "disconnected")
        self.assertIsNone(diagnostics["selected_port"])
        self.assertEqual(diagnostics["last_serial_error"], "no likely M5/ESP32 USB serial port found")


if __name__ == "__main__":
    unittest.main()
