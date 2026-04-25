import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from codex_buddy_bridge.policy import HardwareApprovalPolicy, PolicyConfig
from codex_buddy_bridge.server import BuddyDaemon, make_handler


class RecordingPublisher:
    def __init__(self):
        self.payloads = []
        self.started = False
        self.stopped = False
        self.diagnostic_payload = {}

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def publish(self, payload):
        self.payloads.append(payload)

    def diagnostics(self):
        return dict(self.diagnostic_payload)


class ServerTests(unittest.TestCase):
    def test_hook_endpoint_publishes_sanitized_snapshot(self):
        publisher = RecordingPublisher()
        daemon = BuddyDaemon(publisher, permission_timeout=0.01)
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
        self.assertEqual(publisher.payloads[-1]["prompt"]["hint"], "A approve / B deny")
        self.assertNotIn("secret command", str(publisher.payloads[-1]))

    def test_permission_request_returns_hardware_deny_decision(self):
        publisher = RecordingPublisher()
        daemon = BuddyDaemon(publisher, permission_timeout=1)
        response = {}

        def call_hook():
            _, hook_response = daemon.handle_hook_with_response(
                {
                    "hook_event_name": "PermissionRequest",
                    "session_id": "session-secret",
                    "turn_id": "turn-secret",
                    "tool_name": "Bash",
                    "tool_input": {"command": "rm -rf should-not-leak"},
                }
            )
            response["body"] = hook_response

        thread = threading.Thread(target=call_hook)
        thread.start()
        try:
            prompt = _wait_for_active_prompt(daemon)
            decision = daemon.policy.evaluate(
                prompt_id=prompt.prompt_id,
                decision="deny",
                active_prompt=prompt,
            )
            daemon.handle_device_permission(
                {"cmd": "permission", "id": prompt.prompt_id, "decision": "deny"},
                decision,
            )
        finally:
            thread.join(timeout=2)

        self.assertEqual(
            response["body"]["hookSpecificOutput"]["decision"]["behavior"],
            "deny",
        )
        self.assertEqual(publisher.payloads[-1]["msg"], "denied")
        self.assertNotIn("prompt", publisher.payloads[-1])
        self.assertNotIn("session-secret", str(publisher.payloads))
        self.assertNotIn("rm -rf", str(publisher.payloads))

    def test_permission_request_allows_policy_approved_command(self):
        publisher = RecordingPublisher()
        daemon = BuddyDaemon(
            publisher,
            permission_timeout=1,
            policy=HardwareApprovalPolicy(PolicyConfig(hardware_approve_enabled=True)),
        )
        response = {}

        def call_hook():
            _, hook_response = daemon.handle_hook_with_response(
                {
                    "hook_event_name": "PermissionRequest",
                    "session_id": "session-1",
                    "turn_id": "turn-1",
                    "tool_name": "Bash",
                    "tool_input": {"command": "git status --short"},
                }
            )
            response["body"] = hook_response

        thread = threading.Thread(target=call_hook)
        thread.start()
        try:
            prompt = _wait_for_active_prompt(daemon)
            decision = daemon.policy.evaluate(
                prompt_id=prompt.prompt_id,
                decision="accept",
                active_prompt=prompt,
            )
            daemon.handle_device_permission(
                {"cmd": "permission", "id": prompt.prompt_id, "decision": "accept"},
                decision,
            )
        finally:
            thread.join(timeout=2)

        self.assertEqual(
            response["body"]["hookSpecificOutput"]["decision"]["behavior"],
            "allow",
        )
        self.assertEqual(publisher.payloads[-1]["msg"], "approved")
        self.assertNotIn("prompt", publisher.payloads[-1])

    def test_policy_rejected_approve_does_not_answer_hook(self):
        publisher = RecordingPublisher()
        daemon = BuddyDaemon(publisher, permission_timeout=1)
        response = {}

        def call_hook():
            snapshot, hook_response = daemon.handle_hook_with_response(
                {
                    "hook_event_name": "PermissionRequest",
                    "session_id": "session-1",
                    "turn_id": "turn-1",
                    "tool_name": "Bash",
                    "tool_input": {"command": "git status --short"},
                }
            )
            response["snapshot"] = snapshot
            response["body"] = hook_response

        thread = threading.Thread(target=call_hook)
        thread.start()
        try:
            prompt = _wait_for_active_prompt(daemon)
            decision = daemon.policy.evaluate(
                prompt_id=prompt.prompt_id,
                decision="accept",
                active_prompt=prompt,
            )
            daemon.handle_device_permission(
                {"cmd": "permission", "id": prompt.prompt_id, "decision": "accept"},
                decision,
            )
        finally:
            thread.join(timeout=2)

        self.assertIsNone(response["body"])
        self.assertEqual(response["snapshot"].to_wire()["waiting"], 1)
        self.assertEqual(publisher.payloads[-1]["msg"], "approve in Codex")

    def test_healthz_reports_sanitized_hook_diagnostics(self):
        publisher = RecordingPublisher()
        daemon = BuddyDaemon(publisher, permission_timeout=0.01)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(daemon))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            raw = json.dumps(
                {
                    "hook": {
                        "hook_event_name": "PermissionRequest",
                        "tool_input": {"command": "secret command should not be reported"},
                    }
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/hook",
                data=raw,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5):
                pass

            with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/healthz",
                timeout=5,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()

        self.assertTrue(body["ok"])
        self.assertEqual(body["diagnostics"]["last_hook_event"], "PermissionRequest")
        self.assertEqual(body["diagnostics"]["event_counts"]["PermissionRequest"], 1)
        self.assertNotIn("secret command", str(body["diagnostics"]))

    def test_unknown_hook_event_is_not_reflected_raw(self):
        publisher = RecordingPublisher()
        daemon = BuddyDaemon(publisher)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(daemon))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            raw = json.dumps(
                {"hook_event_name": "raw prompt text should not be logged"}
            ).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/hook",
                data=raw,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5):
                pass

            with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/healthz",
                timeout=5,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(body["diagnostics"]["last_hook_event"], "unknown")
        self.assertEqual(body["diagnostics"]["event_counts"]["unknown"], 1)
        self.assertNotIn("raw prompt text", str(body["diagnostics"]))

    def test_healthz_includes_publisher_diagnostics_without_prompt_data(self):
        publisher = RecordingPublisher()
        publisher.diagnostic_payload = {
            "transport": "serial",
            "selected_port": "/dev/cu.usbserial-7552A41038",
            "connection_state": "connected",
            "last_publish_time": "2026-04-24T12:00:00",
            "last_serial_error": None,
        }
        daemon = BuddyDaemon(publisher)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(daemon))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            raw = json.dumps(
                {
                    "hook": {
                        "hook_event_name": "UserPromptSubmit",
                        "prompt": "prompt text must not be reported",
                    }
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/hook",
                data=raw,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5):
                pass

            with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/healthz",
                timeout=5,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(body["diagnostics"]["publisher"]["transport"], "serial")
        self.assertEqual(body["diagnostics"]["publisher"]["connection_state"], "connected")
        self.assertNotIn("prompt text must not be reported", str(body["diagnostics"]))


if __name__ == "__main__":
    unittest.main()


def _wait_for_active_prompt(daemon):
    deadline = threading.Event()
    for _ in range(100):
        prompt = daemon.active_prompt()
        if prompt is not None:
            return prompt
        deadline.wait(0.01)
    raise AssertionError("active prompt was not registered")
