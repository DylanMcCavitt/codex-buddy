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


if __name__ == "__main__":
    unittest.main()
