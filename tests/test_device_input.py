import unittest

from codex_buddy_bridge.device_input import DeviceInputMonitor
from codex_buddy_bridge.policy import ApprovalPrompt, HardwareApprovalPolicy, PromptKind


class DeviceInputMonitorTests(unittest.TestCase):
    def test_parses_known_and_unknown_commands_without_details(self):
        logs = []
        monitor = DeviceInputMonitor(logger=logs.append)

        monitor.feed_bytes(b'{"cmd":"permission","decision":"decline","prompt":"secret"}\n')
        monitor.feed_bytes(b'{"cmd":"status","owner":"secret"}\n')
        monitor.feed_bytes(b'{"cmd":"future","value":"secret"}\n')

        diagnostics = monitor.diagnostics()
        self.assertEqual(diagnostics["last_command_type"], "unknown")
        self.assertEqual(diagnostics["command_counts"]["permission"], 1)
        self.assertEqual(diagnostics["command_counts"]["status"], 1)
        self.assertEqual(diagnostics["command_counts"]["unknown"], 1)
        self.assertNotIn("secret", str(diagnostics))
        self.assertNotIn("secret", "\n".join(logs))

    def test_malformed_and_oversized_input_are_counted_safely(self):
        logs = []
        monitor = DeviceInputMonitor(max_line_bytes=16, logger=logs.append)

        monitor.feed_bytes(b"{not-json}\n")
        monitor.feed_bytes(b'{"cmd":"permission"}\n')

        diagnostics = monitor.diagnostics()
        self.assertEqual(diagnostics["parse_errors"], 1)
        self.assertEqual(diagnostics["oversized_inputs"], 1)
        self.assertIsNone(diagnostics["last_command_type"])
        self.assertNotIn("permission", "\n".join(logs))

    def test_ble_style_chunked_input_uses_newline_framing(self):
        monitor = DeviceInputMonitor()

        monitor.feed_bytes(b'{"cmd":"per')
        self.assertIsNone(monitor.diagnostics()["last_command_type"])

        monitor.feed_bytes(b'mission"}\n{"cmd":"ack"}\n')

        diagnostics = monitor.diagnostics()
        self.assertEqual(diagnostics["last_command_type"], "ack")
        self.assertEqual(diagnostics["command_counts"], {"permission": 1, "ack": 1})

    def test_permission_input_records_sanitized_policy_decision(self):
        prompt = ApprovalPrompt(
            prompt_id="request-secret",
            kind=PromptKind.COMMAND,
            command="rm -rf /Users/dylanmccavitt/private",
        )
        monitor = DeviceInputMonitor(
            policy=HardwareApprovalPolicy(),
            active_prompt=lambda: prompt,
        )

        monitor.feed_bytes(b'{"cmd":"permission","id":"request-secret","decision":"accept"}\n')

        diagnostics = monitor.diagnostics()
        decision = diagnostics["last_policy_decision"]
        self.assertEqual(decision["outcome"], "reject_hardware_approve")
        self.assertEqual(decision["reason"], "hardware_approve_disabled")
        self.assertNotIn("request-secret", str(diagnostics))
        self.assertNotIn("/Users/dylanmccavitt/private", str(diagnostics))


if __name__ == "__main__":
    unittest.main()
