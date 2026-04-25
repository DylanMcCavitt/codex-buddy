import unittest

from codex_buddy_bridge.ble import BlePublisher


class FakeBleDevice:
    def __init__(self, name):
        self.name = name


class FakeScanner:
    devices = []

    @classmethod
    async def discover(cls, timeout, service_uuids=None):
        return cls.devices


class BleDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_transition_prefixes_match_codex_and_claude_devices(self):
        publisher = BlePublisher(["Claude", "Codex"], scan_timeout=0)

        FakeScanner.devices = [FakeBleDevice("Codex-ABCD")]
        self.assertIs(await publisher._find_device(FakeScanner), FakeScanner.devices[0])

        FakeScanner.devices = [FakeBleDevice("Claude-1234")]
        self.assertIs(await publisher._find_device(FakeScanner), FakeScanner.devices[0])

    async def test_tx_notification_feeds_sanitized_device_input(self):
        publisher = BlePublisher(["Codex"], scan_timeout=0)

        publisher._handle_tx_notification("tx", b'{"cmd":"ack","detail":"secret"}\n')

        diagnostics = publisher.diagnostics()
        self.assertEqual(diagnostics["transport"], "ble")
        self.assertEqual(diagnostics["connection_state"], "disconnected")
        self.assertEqual(diagnostics["device_input"]["last_command_type"], "ack")
        self.assertEqual(diagnostics["device_input"]["command_counts"]["ack"], 1)
        self.assertNotIn("secret", str(diagnostics))

    async def test_start_notifications_subscribes_to_nus_tx(self):
        publisher = BlePublisher(["Codex"], scan_timeout=0)
        client = FakeNotifyClient()

        await publisher._start_notifications(client)
        client.callback("tx", bytearray(b'{"cmd":"status"}\n'))

        self.assertEqual(client.uuid, "6e400003-b5a3-f393-e0a9-e50e24dcca9e")
        self.assertEqual(publisher.diagnostics()["device_input"]["last_command_type"], "status")


class FakeNotifyClient:
    def __init__(self):
        self.uuid = None
        self.callback = None

    async def start_notify(self, uuid, callback):
        self.uuid = uuid
        self.callback = callback


if __name__ == "__main__":
    unittest.main()
