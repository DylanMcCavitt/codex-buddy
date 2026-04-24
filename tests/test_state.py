import unittest

from codex_buddy_bridge.state import hook_event_name, snapshot_for_hook


class SnapshotMappingTests(unittest.TestCase):
    def test_user_prompt_maps_to_running_without_raw_prompt(self):
        snapshot, idle_delay = snapshot_for_hook(
            {
                "hook": {
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "do not send this to BLE",
                }
            }
        )

        payload = snapshot.to_wire()
        self.assertEqual(payload["running"], 1)
        self.assertEqual(payload["waiting"], 0)
        self.assertEqual(payload["msg"], "Codex working")
        self.assertNotIn("do not send this", str(payload))
        self.assertIsNone(idle_delay)

    def test_permission_request_is_display_only(self):
        snapshot, idle_delay = snapshot_for_hook(
            {
                "hook_event_name": "PermissionRequest",
                "tool_input": {"command": "rm -rf should-not-leak"},
            }
        )

        payload = snapshot.to_wire()
        self.assertEqual(payload["running"], 0)
        self.assertEqual(payload["waiting"], 1)
        self.assertEqual(payload["prompt"]["id"], "display-only")
        self.assertEqual(payload["prompt"]["hint"], "approve in app")
        self.assertNotIn("rm -rf", str(payload))
        self.assertIsNone(idle_delay)

    def test_stop_briefly_completes_then_idles(self):
        snapshot, idle_delay = snapshot_for_hook({"hook_event_name": "Stop"})

        self.assertEqual(snapshot.to_wire()["msg"], "completed")
        self.assertEqual(idle_delay, 2.0)

    def test_enveloped_hook_event_name(self):
        self.assertEqual(
            hook_event_name({"hook": {"hook_event_name": "SessionStart"}}),
            "SessionStart",
        )


if __name__ == "__main__":
    unittest.main()
