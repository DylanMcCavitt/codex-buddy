import json
import tempfile
import unittest
from pathlib import Path

from codex_buddy_bridge.hooks_config import (
    HOOK_SPECS,
    MANAGED_MARKER,
    HookConfigError,
    apply_user_hooks,
    build_hook_command,
    install_user_hooks,
    remove_user_hooks,
)


class UserHookConfigTests(unittest.TestCase):
    def test_install_adds_managed_hooks_for_expected_events(self):
        command = build_hook_command(python="/usr/bin/python3", source_dir=Path("/tool/src"))
        config, installed, removed = install_user_hooks({"hooks": {}}, command=command)

        self.assertEqual(installed, len(HOOK_SPECS))
        self.assertEqual(removed, 0)
        for spec in HOOK_SPECS:
            self.assertIn(spec.event, config["hooks"])
            hook = config["hooks"][spec.event][-1]["hooks"][0]
            self.assertEqual(hook["type"], "command")
            self.assertIn(MANAGED_MARKER, hook["command"])

    def test_install_preserves_existing_user_hooks(self):
        existing = {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "echo user-hook",
                            }
                        ]
                    }
                ]
            },
            "other": "preserved",
        }
        command = build_hook_command(python="/usr/bin/python3", source_dir=Path("/tool/src"))

        config, _, _ = install_user_hooks(existing, command=command)

        commands = [hook["command"] for group in config["hooks"]["UserPromptSubmit"] for hook in group["hooks"]]
        self.assertIn("echo user-hook", commands)
        self.assertIn(command, commands)
        self.assertEqual(config["other"], "preserved")

    def test_install_is_idempotent(self):
        command = build_hook_command(python="/usr/bin/python3", source_dir=Path("/tool/src"))
        first, _, _ = install_user_hooks({"hooks": {}}, command=command)
        second, installed, removed = install_user_hooks(first, command=command)

        self.assertEqual(second, first)
        self.assertEqual(installed, len(HOOK_SPECS))
        self.assertEqual(removed, len(HOOK_SPECS))

    def test_install_removes_legacy_tool_lifecycle_hooks(self):
        command = build_hook_command(python="/usr/bin/python3", source_dir=Path("/tool/src"))
        legacy = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": command}],
                    }
                ],
                "PostToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": command}],
                    }
                ],
            }
        }

        config, installed, removed = install_user_hooks(legacy, command=command)

        self.assertEqual(installed, len(HOOK_SPECS))
        self.assertEqual(removed, 2)
        self.assertNotIn("PreToolUse", config["hooks"])
        self.assertNotIn("PostToolUse", config["hooks"])

    def test_uninstall_removes_only_managed_hooks(self):
        command = build_hook_command(python="/usr/bin/python3", source_dir=Path("/tool/src"))
        installed, _, _ = install_user_hooks(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {"type": "command", "command": "echo keep-me"},
                            ],
                        }
                    ]
                }
            },
            command=command,
        )

        config, removed = remove_user_hooks(installed)

        self.assertEqual(removed, len(HOOK_SPECS))
        self.assertEqual(config["hooks"]["PreToolUse"][0]["hooks"][0]["command"], "echo keep-me")
        self.assertNotIn("UserPromptSubmit", config["hooks"])

    def test_apply_uses_config_path_without_touching_real_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / ".codex" / "hooks.json"

            result = apply_user_hooks(
                "install",
                config_path=config_path,
                python="/usr/bin/python3",
                source_dir=Path("/tool/src"),
            )

            self.assertTrue(result.changed)
            self.assertTrue(config_path.exists())
            body = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(set(body["hooks"]), {spec.event for spec in HOOK_SPECS})

    def test_dry_run_does_not_write_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / ".codex" / "hooks.json"

            result = apply_user_hooks(
                "install",
                config_path=config_path,
                python="/usr/bin/python3",
                source_dir=Path("/tool/src"),
                dry_run=True,
            )

            self.assertTrue(result.changed)
            self.assertFalse(config_path.exists())

    def test_invalid_top_level_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "hooks.json"
            config_path.write_text("[]", encoding="utf-8")

            with self.assertRaises(HookConfigError):
                apply_user_hooks("install", config_path=config_path)


if __name__ == "__main__":
    unittest.main()
