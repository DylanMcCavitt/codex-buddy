import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from codex_buddy_bridge.server import BuddyDaemon, make_handler


class RecordingPublisher:
    def __init__(self):
        self.payloads = []
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def publish(self, payload):
        self.payloads.append(payload)


class ServerTests(unittest.TestCase):
    def test_hook_endpoint_publishes_sanitized_snapshot(self):
        publisher = RecordingPublisher()
        daemon = BuddyDaemon(publisher)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(daemon))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            raw = json.dumps(
                {
                    "hook": {
                        "hook_event_name": "PermissionRequest",
                        "tool_input": {"command": "secret command should not leave daemon"},
                    }
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/hook",
                data=raw,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                body = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()

        self.assertTrue(body["ok"])
        self.assertEqual(publisher.payloads[-1]["waiting"], 1)
        self.assertEqual(publisher.payloads[-1]["prompt"]["hint"], "approve in app")
        self.assertNotIn("secret command", str(publisher.payloads[-1]))


if __name__ == "__main__":
    unittest.main()
